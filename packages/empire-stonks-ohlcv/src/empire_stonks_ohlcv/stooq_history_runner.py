"""Package-owned Core run lifecycle for manual Stooq historical backfills."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from empire_core import ObjectStore, RunContext, RunService, StoredObject

from empire_stonks_ohlcv.config import OHLCVConfig
from empire_stonks_ohlcv.exceptions import OHLCVConfigError, OHLCVWorkflowError
from empire_stonks_ohlcv.object_store import store_raw_file
from empire_stonks_ohlcv.results import AcquiredObject
from empire_stonks_ohlcv.runner import DEFAULT_DOMAIN, SAFE_FAILURE_MESSAGE
from empire_stonks_ohlcv.source_conventions import STOOQ_HISTORY_SOURCE
from empire_stonks_ohlcv.source_snapshots import (
    SourceSnapshotRegistration,
    upsert_provider_source_snapshot,
)
from empire_stonks_ohlcv.stooq_history import (
    STOOQ_HISTORY_ARCHIVE_NAME,
    STOOQ_HISTORY_PROVIDER_CODE,
    StooqHistoryParseProgress,
    StooqHistoryParseSummary,
    StooqHistoryParser,
    StooqHistoryScope,
)
from empire_stonks_ohlcv.stooq_history_writer import (
    StooqHistoryChunkWriter,
    StooqHistoryWriteSummary,
)
from empire_stonks_ohlcv.stooq_history_reporting import (
    build_stooq_history_report,
    store_stooq_history_report,
)


STOOQ_HISTORY_JOB_NAME = "stonks_ohlcv_stooq_backfill"
STOOQ_HISTORY_SUBJECT_KEY = "us_stocks"
STOOQ_HISTORY_HEARTBEAT_TIMEOUT_SECONDS = 900

ProgressSink = Callable[[dict[str, Any]], None]
MonotonicClock = Callable[[], float]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StooqHistoryRunResult:
    """Compact successful result for one tracked historical backfill."""

    run_id: UUID
    status: str
    scope: StooqHistoryScope
    chunk_size: int
    acquired_object: AcquiredObject
    source_snapshot: SourceSnapshotRegistration
    parse_summary: StooqHistoryParseSummary
    write_summary: StooqHistoryWriteSummary
    report_object_id: UUID
    report_outcome: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, UUID):
            raise TypeError("run_id must be a UUID.")
        if self.status != "succeeded":
            raise ValueError("status must be succeeded.")
        if not isinstance(self.scope, StooqHistoryScope):
            raise TypeError("scope must be a StooqHistoryScope.")
        _positive_int("chunk_size", self.chunk_size)
        if not isinstance(self.acquired_object, AcquiredObject):
            raise TypeError("acquired_object must be an AcquiredObject.")
        if not isinstance(self.source_snapshot, SourceSnapshotRegistration):
            raise TypeError(
                "source_snapshot must be a SourceSnapshotRegistration."
            )
        if not isinstance(self.parse_summary, StooqHistoryParseSummary):
            raise TypeError("parse_summary must be a StooqHistoryParseSummary.")
        if not isinstance(self.write_summary, StooqHistoryWriteSummary):
            raise TypeError("write_summary must be a StooqHistoryWriteSummary.")
        if not isinstance(self.report_object_id, UUID):
            raise TypeError("report_object_id must be a UUID.")
        if self.report_outcome not in {"PASS", "WARN"}:
            raise ValueError("report_outcome must be PASS or WARN.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
            "source_code": STOOQ_HISTORY_SOURCE.source_code,
            "scope": self.scope.to_dict(),
            "chunk_size": self.chunk_size,
            "acquired_object": self.acquired_object.to_dict(),
            "source_snapshot": self.source_snapshot.to_dict(),
            "parse_summary": self.parse_summary.to_dict(),
            "write_summary": self.write_summary.to_dict(),
            "report_object_id": str(self.report_object_id),
            "report_outcome": self.report_outcome,
        }


def run_stooq_history_backfill(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    input_path: str | Path,
    scope: StooqHistoryScope,
    chunk_size: int,
    run_type: str,
    runner: str,
    runner_ref: dict[str, Any] | None = None,
    progress_sink: ProgressSink | None = None,
    monotonic: MonotonicClock = time.monotonic,
) -> StooqHistoryRunResult:
    """Copy, register, stream, and track one manual Stooq archive import."""

    path = _validate_inputs(
        run_service=run_service,
        connection=connection,
        object_store=object_store,
        config=config,
        input_path=input_path,
        scope=scope,
        chunk_size=chunk_size,
        runner=runner,
        progress_sink=progress_sink,
        monotonic=monotonic,
    )
    started_at = monotonic()
    run_context = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=STOOQ_HISTORY_JOB_NAME,
        subject_key=STOOQ_HISTORY_SUBJECT_KEY,
        effective_date=scope.effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params=_run_params(config=config, scope=scope, chunk_size=chunk_size),
        heartbeat_timeout_seconds=STOOQ_HISTORY_HEARTBEAT_TIMEOUT_SECONDS,
    )

    acquired: AcquiredObject | None = None
    registration: SourceSnapshotRegistration | None = None
    parser: StooqHistoryParser | None = None
    report_object: StoredObject | None = None
    writer = StooqHistoryChunkWriter(connection)
    try:
        acquired = _store_archive(
            object_store=object_store,
            run_context=run_context,
            config=config,
            input_path=path,
        )
        stored_path = object_store.get_path(acquired.object_id)
        _emit_progress(
            run_service=run_service,
            run_id=run_context.run_id,
            stage="acquisition",
            elapsed_seconds=monotonic() - started_at,
            parse_progress=None,
            write_summary=writer.summary,
            progress_sink=progress_sink,
        )

        def parser_progress(progress: StooqHistoryParseProgress) -> None:
            _emit_progress(
                run_service=run_service,
                run_id=run_context.run_id,
                stage="parsing",
                elapsed_seconds=monotonic() - started_at,
                parse_progress=progress,
                write_summary=writer.summary,
                progress_sink=progress_sink,
            )

        parser = _create_parser(
            archive_path=stored_path,
            scope=scope,
            chunk_size=chunk_size,
            progress_callback=parser_progress,
        )
        _emit_progress(
            run_service=run_service,
            run_id=run_context.run_id,
            stage="parsing",
            elapsed_seconds=monotonic() - started_at,
            parse_progress=parser.progress,
            write_summary=writer.summary,
            progress_sink=progress_sink,
        )
        registration = _register_source_snapshot(
            connection=connection,
            acquired_object=acquired,
        )

        iterator = iter(parser)
        while True:
            try:
                chunk = next(iterator)
            except StopIteration:
                break
            except OHLCVWorkflowError:
                raise
            except Exception as exc:
                raise OHLCVWorkflowError(
                    "parsing",
                    source_code=STOOQ_HISTORY_SOURCE.source_code,
                ) from exc

            writer.write(chunk)
            _emit_progress(
                run_service=run_service,
                run_id=run_context.run_id,
                stage="persistence",
                elapsed_seconds=monotonic() - started_at,
                parse_progress=parser.progress,
                write_summary=writer.summary,
                progress_sink=progress_sink,
            )

        parse_summary = parser.summary
        report, report_object = _build_and_store_report(
            connection=connection,
            object_store=object_store,
            run_context=run_context,
            config=config,
            scope=scope,
            chunk_size=chunk_size,
            acquired_object=acquired,
            source_snapshot=registration,
            parse_summary=parse_summary,
            parse_progress=parser.progress,
            write_summary=writer.summary,
            run_status="complete",
            failed_stage=None,
            elapsed_seconds=monotonic() - started_at,
        )
        summary = _run_summary(
            scope=scope,
            chunk_size=chunk_size,
            acquired_object=acquired,
            source_snapshot=registration,
            parse_summary=parse_summary,
            write_summary=writer.summary,
            elapsed_seconds=monotonic() - started_at,
            report_object=report_object,
            report_outcome=report["outcome"],
        )
        completed = run_service.complete_run(run_context.run_id, summary=summary)
        return StooqHistoryRunResult(
            run_id=completed.run_id,
            status=completed.status,
            scope=scope,
            chunk_size=chunk_size,
            acquired_object=acquired,
            source_snapshot=registration,
            parse_summary=parse_summary,
            write_summary=writer.summary,
            report_object_id=report_object.object_id,
            report_outcome=report["outcome"],
        )
    except Exception as exc:
        _rollback_quietly(connection)
        failed_stage = (
            exc.stage if isinstance(exc, OHLCVWorkflowError) else "reporting"
        )
        if acquired is not None and failed_stage != "reporting":
            report_object = _try_store_partial_report(
                connection=connection,
                object_store=object_store,
                run_context=run_context,
                config=config,
                scope=scope,
                chunk_size=chunk_size,
                acquired_object=acquired,
                source_snapshot=registration,
                parse_summary=None,
                parse_progress=(
                    parser.progress
                    if parser is not None
                    else StooqHistoryParseProgress(files_discovered=0)
                ),
                write_summary=writer.summary,
                failed_stage=failed_stage,
                elapsed_seconds=monotonic() - started_at,
            )
        run_service.fail_run(
            run_context.run_id,
            SAFE_FAILURE_MESSAGE,
            summary=_failure_summary(
                scope=scope,
                chunk_size=chunk_size,
                acquired_object=acquired,
                source_snapshot=registration,
                parse_progress=parser.progress if parser is not None else None,
                write_summary=writer.summary,
                failed_stage=failed_stage,
                elapsed_seconds=monotonic() - started_at,
                report_object=report_object,
            ),
        )
        raise


def _store_archive(
    *,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    input_path: Path,
) -> AcquiredObject:
    try:
        acquired = store_raw_file(
            object_store=object_store,
            run_context=run_context,
            config=config,
            provider_code=STOOQ_HISTORY_PROVIDER_CODE,
            source_code=STOOQ_HISTORY_SOURCE.source_code,
            format_suffix="zip",
            source_path=input_path,
            content_type="application/zip",
            parser_version=STOOQ_HISTORY_SOURCE.parser_version,
            provider_metadata={"request_scope": STOOQ_HISTORY_SUBJECT_KEY},
            move=False,
        )
        if not isinstance(acquired, AcquiredObject):
            raise TypeError("archive storage must return an AcquiredObject.")
        return acquired
    except Exception as exc:
        raise OHLCVWorkflowError(
            "acquisition",
            source_code=STOOQ_HISTORY_SOURCE.source_code,
        ) from exc


def _register_source_snapshot(
    *,
    connection: Any,
    acquired_object: AcquiredObject,
) -> SourceSnapshotRegistration:
    try:
        with connection.cursor() as cursor:
            registration = upsert_provider_source_snapshot(
                cursor=cursor,
                provider_code=STOOQ_HISTORY_PROVIDER_CODE,
                acquired_object=acquired_object,
                parser_version=STOOQ_HISTORY_SOURCE.parser_version,
            )
            if not isinstance(registration, SourceSnapshotRegistration):
                raise TypeError(
                    "snapshot writer must return SourceSnapshotRegistration."
                )
        connection.commit()
        return registration
    except Exception as exc:
        connection.rollback()
        raise OHLCVWorkflowError(
            "persistence",
            source_code=STOOQ_HISTORY_SOURCE.source_code,
        ) from exc


def _create_parser(
    *,
    archive_path: Path,
    scope: StooqHistoryScope,
    chunk_size: int,
    progress_callback: Callable[[StooqHistoryParseProgress], None],
) -> StooqHistoryParser:
    try:
        return StooqHistoryParser(
            archive_path,
            scope=scope,
            chunk_size=chunk_size,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        raise OHLCVWorkflowError(
            "parsing",
            source_code=STOOQ_HISTORY_SOURCE.source_code,
        ) from exc


def _emit_progress(
    *,
    run_service: RunService,
    run_id: UUID,
    stage: str,
    elapsed_seconds: float,
    parse_progress: StooqHistoryParseProgress | None,
    write_summary: StooqHistoryWriteSummary,
    progress_sink: ProgressSink | None,
) -> None:
    run_service.heartbeat(run_id)
    if progress_sink is None:
        return
    progress = {
        "run_id": str(run_id),
        "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
        "source_code": STOOQ_HISTORY_SOURCE.source_code,
        "stage": stage,
        "elapsed_seconds": max(0.0, elapsed_seconds),
        "parse_progress": (
            parse_progress.to_dict() if parse_progress is not None else None
        ),
        "write_summary": write_summary.to_dict(),
    }
    try:
        progress_sink(progress)
    except Exception:
        logger.warning("Stooq history progress sink failed; continuing run.")


def _run_params(
    *,
    config: OHLCVConfig,
    scope: StooqHistoryScope,
    chunk_size: int,
) -> dict[str, Any]:
    return {
        "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
        "source_code": STOOQ_HISTORY_SOURCE.source_code,
        "parser_version": STOOQ_HISTORY_SOURCE.parser_version,
        "input_mode": "operator_supplied_file",
        "input_filename": STOOQ_HISTORY_ARCHIVE_NAME,
        "request_scope": STOOQ_HISTORY_SUBJECT_KEY,
        "scope": scope.to_dict(),
        "chunk_size": chunk_size,
        "raw_retention_days": config.raw_retention_days,
        "storage_key": config.storage_key,
    }


def _run_summary(
    *,
    scope: StooqHistoryScope,
    chunk_size: int,
    acquired_object: AcquiredObject,
    source_snapshot: SourceSnapshotRegistration,
    parse_summary: StooqHistoryParseSummary,
    write_summary: StooqHistoryWriteSummary,
    elapsed_seconds: float,
    report_object: StoredObject,
    report_outcome: str,
) -> dict[str, Any]:
    return {
        "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
        "source_code": STOOQ_HISTORY_SOURCE.source_code,
        "outcome": "succeeded",
        "scope": scope.to_dict(),
        "chunk_size": chunk_size,
        "elapsed_seconds": max(0.0, elapsed_seconds),
        "acquired_object": acquired_object.to_dict(),
        "source_snapshot": source_snapshot.to_dict(),
        "parse_summary": parse_summary.to_dict(),
        "write_summary": write_summary.to_dict(),
        "report_object_id": str(report_object.object_id),
        "report_outcome": report_outcome,
    }


def _failure_summary(
    *,
    scope: StooqHistoryScope,
    chunk_size: int,
    acquired_object: AcquiredObject | None,
    source_snapshot: SourceSnapshotRegistration | None,
    parse_progress: StooqHistoryParseProgress | None,
    write_summary: StooqHistoryWriteSummary,
    failed_stage: str | None,
    elapsed_seconds: float,
    report_object: StoredObject | None,
) -> dict[str, Any]:
    return {
        "provider_code": STOOQ_HISTORY_PROVIDER_CODE,
        "source_code": STOOQ_HISTORY_SOURCE.source_code,
        "outcome": "failed",
        "failed_stage": failed_stage,
        "scope": scope.to_dict(),
        "chunk_size": chunk_size,
        "elapsed_seconds": max(0.0, elapsed_seconds),
        "acquired_object": (
            acquired_object.to_dict() if acquired_object is not None else None
        ),
        "source_snapshot": (
            source_snapshot.to_dict() if source_snapshot is not None else None
        ),
        "parse_progress": (
            parse_progress.to_dict() if parse_progress is not None else None
        ),
        "write_summary": write_summary.to_dict(),
        "report_object_id": (
            str(report_object.object_id) if report_object is not None else None
        ),
        "report_outcome": "FAIL" if report_object is not None else None,
    }


def _build_and_store_report(
    *,
    connection: Any,
    object_store: ObjectStore,
    run_context: RunContext,
    config: OHLCVConfig,
    scope: StooqHistoryScope,
    chunk_size: int,
    acquired_object: AcquiredObject | None,
    source_snapshot: SourceSnapshotRegistration | None,
    parse_summary: StooqHistoryParseSummary | None,
    parse_progress: StooqHistoryParseProgress,
    write_summary: StooqHistoryWriteSummary,
    run_status: str,
    failed_stage: str | None,
    elapsed_seconds: float,
) -> tuple[dict[str, Any], StoredObject]:
    try:
        with connection.cursor() as cursor:
            report = build_stooq_history_report(
                cursor=cursor,
                scope=scope,
                chunk_size=chunk_size,
                acquired_object=acquired_object,
                source_snapshot=source_snapshot,
                parse_summary=parse_summary,
                parse_progress=parse_progress,
                write_summary=write_summary,
                run_status=run_status,  # type: ignore[arg-type]
                failed_stage=failed_stage,
                elapsed_seconds=elapsed_seconds,
            )
        stored = store_stooq_history_report(
            object_store=object_store,
            run_context=run_context,
            config=config,
            report=report,
        )
        if not isinstance(stored, StoredObject) or stored.run_id != run_context.run_id:
            raise TypeError("report storage returned an invalid Core object.")
        return report, stored
    except Exception as exc:
        raise OHLCVWorkflowError(
            "reporting",
            source_code=STOOQ_HISTORY_SOURCE.source_code,
        ) from exc


def _try_store_partial_report(
    **values: Any,
) -> StoredObject | None:
    try:
        _report, stored = _build_and_store_report(
            run_status="partial",
            **values,
        )
        return stored
    except Exception:
        logger.warning("Stooq partial report could not be stored.")
        return None


def _validate_inputs(
    *,
    run_service: RunService,
    connection: Any,
    object_store: ObjectStore,
    config: OHLCVConfig,
    input_path: str | Path,
    scope: StooqHistoryScope,
    chunk_size: int,
    runner: str,
    progress_sink: ProgressSink | None,
    monotonic: MonotonicClock,
) -> Path:
    if not isinstance(run_service, RunService):
        raise TypeError("run_service must be a Core RunService.")
    if not isinstance(object_store, ObjectStore):
        raise TypeError("object_store must be a Core ObjectStore.")
    if not isinstance(config, OHLCVConfig):
        raise OHLCVConfigError("config must be an OHLCVConfig.")
    if not isinstance(scope, StooqHistoryScope):
        raise TypeError("scope must be a StooqHistoryScope.")
    _positive_int("chunk_size", chunk_size)
    if not isinstance(runner, str) or not runner.strip() or runner != runner.strip():
        raise OHLCVConfigError("runner must be non-blank and trimmed.")
    if progress_sink is not None and not callable(progress_sink):
        raise TypeError("progress_sink must be callable or None.")
    if not callable(monotonic):
        raise TypeError("monotonic must be callable.")
    for method_name in ("cursor", "commit", "rollback"):
        if not callable(getattr(connection, method_name, None)):
            raise TypeError(
                "connection must provide cursor, commit, and rollback methods."
            )

    if not isinstance(input_path, (str, Path)):
        raise TypeError("input_path must be a string or Path.")
    path = Path(input_path).expanduser().resolve()
    if path.name != STOOQ_HISTORY_ARCHIVE_NAME:
        raise OHLCVConfigError(
            f"input_path filename must be {STOOQ_HISTORY_ARCHIVE_NAME}."
        )
    if not path.is_file():
        raise OHLCVConfigError("input_path must be an existing regular file.")
    return path


def _positive_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
