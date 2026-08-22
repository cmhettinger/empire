from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from pypdf import PdfReader

from empire_stonks_tech_indicators.report_pdf import (
    PDF_DIAGNOSTIC_SAMPLE_LIMIT,
    PDF_MAXIMUM_BYTES,
    PDF_MAXIMUM_PAGES,
    TECH_INDICATORS_PDF_FEATURE_FAMILIES,
    _bounded_diagnostic_samples,
    render_tech_indicators_report_pdf,
    roll_up_pdf_feature_coverage,
)
from empire_stonks_tech_indicators.reporting_queries import REPORT_FEATURE_FIELDS
from empire_stonks_tech_indicators.reports import (
    REPORT_DIAGNOSTIC_MESSAGE_CATALOG,
    ReportDiagnosticSample,
    ReportIssueAggregate,
    ReportOutcome,
)
from test_reports import _daily_pass, _failure, _no_op, _partial


def _pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def test_feature_family_rollup_covers_v1_once_and_reconciles() -> None:
    report = _daily_pass()
    summaries = roll_up_pdf_feature_coverage(report.coverage.features)
    fields = tuple(
        field
        for _family, family_fields in TECH_INDICATORS_PDF_FEATURE_FAMILIES
        for field in family_fields
    )

    assert len(summaries) == 10
    assert len(fields) == len(set(fields)) == 76
    assert set(fields) == set(REPORT_FEATURE_FIELDS)
    assert sum(item.field_count for item in summaries) == 76
    assert sum(item.eligible for item in summaries) == 76 * 2
    assert all(item.populated + item.null_count == item.eligible for item in summaries)


def test_daily_pdf_renders_contract_sections_and_bounds(tmp_path: Path) -> None:
    report = _daily_pass()
    before = report.to_dict()

    result = render_tech_indicators_report_pdf(report, output_dir=tmp_path)

    artifact = result.primary_artifact.resolved_path()
    reader = PdfReader(artifact)
    text = _pdf_text(artifact)
    assert report.to_dict() == before
    assert result.report.report_id == report.report_id
    assert artifact.name == "report.pdf"
    assert artifact.stat().st_size <= PDF_MAXIMUM_BYTES
    assert 8 <= len(reader.pages) <= PDF_MAXIMUM_PAGES
    for required in (
        "Daily Technical Indicators Operational Report",
        "Operational evidence only; not investment advice",
        "Executive Status",
        "Scope And Readiness",
        "Coverage And Writes",
        "Feature Quality",
        "Benchmark Health",
        "Performance",
        "Warnings And Failures",
        "Methodology And Disclosures",
        "TECH_INDICATORS_V1",
        "NumPy",
        "TA-Lib Python",
        "YAHOO / XIDX / SPX",
        "EODData does not specify the adjustment basis",
    ):
        assert required in text
    assert "PROPRIETARY / INTERNAL USE ONLY" in text
    assert "Page 1" in text


@pytest.mark.parametrize(
    ("report", "label"),
    (
        (_daily_pass(), "PASS"),
        (
            replace(
                _daily_pass(),
                outcome=ReportOutcome.WARN,
                warnings=(
                    ReportIssueAggregate("SOURCE_COVERAGE_WARNING", 1),
                ),
            ),
            "WARN",
        ),
        (_no_op(), "NO OP"),
        (_partial(), "PARTIAL - UNPUBLISHED"),
        (_failure(), "FAIL - UNPUBLISHED"),
    ),
)
def test_all_outcome_labels_render(
    report: object,
    label: str,
    tmp_path: Path,
) -> None:
    result = render_tech_indicators_report_pdf(
        report,  # type: ignore[arg-type]
        output_dir=tmp_path,
        filename=f"{label.lower().replace(' ', '-')}.pdf",
    )

    assert label in _pdf_text(result.primary_artifact.resolved_path())


def test_diagnostic_compaction_is_stable_and_bounded() -> None:
    message = REPORT_DIAGNOSTIC_MESSAGE_CATALOG["CALCULATION_FAILED"]
    samples = tuple(
        ReportDiagnosticSample(
            sample_id=f"S{index:03d}",
            code="CALCULATION_FAILED",
            message=message,
            ticker=f"T{index:03d}",
        )
        for index in range(1, 21)
    )
    report = replace(
        _failure(),
        failures=(
            ReportIssueAggregate(
                "CALCULATION_FAILED",
                len(samples),
                tuple(sample.sample_id for sample in samples),
            ),
        ),
        diagnostic_samples=samples,
    )

    first = _bounded_diagnostic_samples(report)
    second = _bounded_diagnostic_samples(report)

    assert first == second
    shown, omitted = first
    assert len(shown["Failure"]) == PDF_DIAGNOSTIC_SAMPLE_LIMIT
    assert tuple(item.sample_id for item in shown["Failure"]) == tuple(
        f"S{index:03d}" for index in range(1, 11)
    )
    assert omitted["Failure"] == 10


def test_pdf_renderer_rejects_invalid_input_and_filename(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="TechIndicatorsReport"):
        render_tech_indicators_report_pdf(
            {},  # type: ignore[arg-type]
            output_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="local .pdf filename"):
        render_tech_indicators_report_pdf(
            _daily_pass(),
            output_dir=tmp_path,
            filename="../report.pdf",
        )
    assert not tuple(tmp_path.iterdir())
