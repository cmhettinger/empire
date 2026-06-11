"""Run orchestration hooks for stonks securities acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Iterable

from empire_core import ObjectStore, RunContext, RunService

from empire_stonks_securities.acquisition import (
    DEFAULT_STORAGE_ROOT,
    SecDownloadResult,
    SecDownloader,
    build_configured_source_targets,
    default_storage_key,
)
from empire_stonks_securities.config import StonksSecuritiesConfig


DEFAULT_DOMAIN = "stonks"
DEFAULT_DAILY_JOB_NAME = "stonks_securities_daily_scrape"
DEFAULT_DAILY_SUBJECT_KEY = "sec_daily_sources"
DEFAULT_DAILY_SOURCE_KEYS = (
    "sec_company_tickers_exchange",
    "sec_company_tickers",
)


@dataclass(frozen=True)
class StonksSecuritiesAcquisitionRunResult:
    """Result of one stonks securities acquisition run."""

    run_context: RunContext
    results: list[SecDownloadResult]

    @property
    def downloaded_count(self) -> int:
        return sum(1 for result in self.results if result.status == "downloaded")

    @property
    def skipped_count(self) -> int:
        return sum(1 for result in self.results if result.skipped)


def run_stonks_securities_daily_to_object_store(
    *,
    config: StonksSecuritiesConfig,
    downloader: SecDownloader,
    run_service: RunService,
    object_store: ObjectStore,
    run_type: str,
    runner: str,
    runner_ref: dict | None = None,
    source_keys: Iterable[str] = DEFAULT_DAILY_SOURCE_KEYS,
    effective_date: date | None = None,
    generated_at: datetime | None = None,
    storage_root: str | None = None,
    storage_key_prefix: str | None = None,
    force: bool = False,
    temp_dir: str | None = None,
) -> StonksSecuritiesAcquisitionRunResult:
    """Download the daily SEC security-master source files into object storage."""

    generated_at = generated_at or datetime.now(UTC)
    effective_date = effective_date or generated_at.date()
    resolved_source_keys = tuple(source_keys)
    resolved_storage_root = storage_root or DEFAULT_STORAGE_ROOT
    resolved_storage_key = storage_key_prefix or default_storage_key()

    ctx = run_service.start_run(
        domain=DEFAULT_DOMAIN,
        job_name=DEFAULT_DAILY_JOB_NAME,
        subject_key=DEFAULT_DAILY_SUBJECT_KEY,
        effective_date=effective_date,
        run_type=run_type,
        runner=runner,
        runner_ref=runner_ref or {},
        params={
            "config_name": config.name,
            "config_version": config.version,
            "source_keys": list(resolved_source_keys),
            "storage_root": resolved_storage_root,
            "storage_key_prefix": resolved_storage_key,
            "force": force,
        },
    )

    try:
        targets = build_configured_source_targets(
            config=config,
            storage_key=resolved_storage_key,
            acquisition_date=effective_date,
            acquisition_id=str(ctx.run_id),
            source_keys=resolved_source_keys,
        )
        results = [
            downloader.download_target(
                target=target,
                object_store=object_store,
                storage_root=resolved_storage_root,
                run_context=ctx,
                force=force,
                temp_dir=temp_dir,
            )
            for target in targets
        ]
        run_result = StonksSecuritiesAcquisitionRunResult(
            run_context=ctx,
            results=results,
        )
        run_service.complete_run(
            ctx.run_id,
            summary={
                "downloaded_count": run_result.downloaded_count,
                "skipped_count": run_result.skipped_count,
                "source_count": len(results),
            },
        )
        return run_result
    except Exception as exc:
        run_service.fail_run(ctx.run_id, str(exc))
        raise


run_stonks_security_daily_to_object_store = run_stonks_securities_daily_to_object_store
