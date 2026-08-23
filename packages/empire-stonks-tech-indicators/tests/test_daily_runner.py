from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from empire_stonks_tech_indicators import ReportOutcome
from empire_stonks_tech_indicators.affected_ranges import AffectedRangeReason
from empire_stonks_tech_indicators.daily_runner import (
    TechIndicatorsDailyRunResult,
    _publication_kind,
)
from empire_stonks_tech_indicators.writer_lock import (
    TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
)


RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
PUBLICATION_ID = UUID("22222222-2222-4222-8222-222222222222")
JSON_ID = UUID("33333333-3333-4333-8333-333333333333")
PDF_ID = UUID("44444444-4444-4444-8444-444444444444")
EFFECTIVE_DATE = date(2026, 8, 21)


class Range:
    def __init__(self, reasons: tuple[AffectedRangeReason, ...]) -> None:
        self.reasons = reasons


def test_daily_result_exposes_only_compact_success_identity() -> None:
    result = TechIndicatorsDailyRunResult(
        status="succeeded",
        effective_date=EFFECTIVE_DATE,
        run_id=RUN_ID,
        publication_id=PUBLICATION_ID,
        json_report_object_id=JSON_ID,
        pdf_report_object_id=PDF_ID,
        outcome=ReportOutcome.PASS,
    )

    assert result.to_dict() == {
        "status": "succeeded",
        "effective_date": "2026-08-21",
        "run_id": str(RUN_ID),
        "publication_id": str(PUBLICATION_ID),
        "json_report_object_id": str(JSON_ID),
        "pdf_report_object_id": str(PDF_ID),
        "outcome": "PASS",
        "message": None,
    }


def test_contended_result_cannot_claim_workflow_state() -> None:
    result = TechIndicatorsDailyRunResult(
        status="contended",
        effective_date=EFFECTIVE_DATE,
        message=TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
    )
    assert result.run_id is None

    with pytest.raises(ValueError, match="must not contain workflow state"):
        TechIndicatorsDailyRunResult(
            status="contended",
            effective_date=EFFECTIVE_DATE,
            run_id=RUN_ID,
            message=TECH_INDICATORS_LOCK_CONTENDED_MESSAGE,
        )


@pytest.mark.parametrize(
    ("reasons", "kind"),
    (
        ((AffectedRangeReason.TAIL_APPEND,), "DAILY"),
        ((AffectedRangeReason.SOURCE_COPY_DRIFT,), "CORRECTION"),
        (
            (
                AffectedRangeReason.TAIL_APPEND,
                AffectedRangeReason.BENCHMARK_DRIFT,
            ),
            "CORRECTION",
        ),
    ),
)
def test_publication_kind_distinguishes_append_from_correction(
    reasons: tuple[AffectedRangeReason, ...],
    kind: str,
) -> None:
    assert _publication_kind((Range(reasons),)) == kind
