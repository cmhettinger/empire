"""Professional PDF rendering for immutable technical-indicator report facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from empire_reports.contracts import RenderContext, RenderResult, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    paragraph,
    professional_letter_disclaimer_page,
    professional_letter_title_page,
    section_heading,
    spacer,
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    NextPageTemplate,
    PageBreak,
    Paragraph,
    Table,
    TableStyle,
)

from empire_stonks_tech_indicators.reporting_queries import (
    REPORT_FEATURE_FIELDS,
    ReportFeatureCoverage,
)
from empire_stonks_tech_indicators.reports import (
    NATIVE_VALUE_NOTE_MESSAGES,
    ReportCursor,
    ReportDiagnosticSample,
    ReportDimensionCount,
    ReportIssueAggregate,
    ReportOutcome,
    TechIndicatorsReport,
    WorkflowKind,
)


PDF_MAXIMUM_BYTES = 5 * 1024 * 1024
PDF_MAXIMUM_PAGES = 25
PDF_DIAGNOSTIC_SAMPLE_LIMIT = 10
PDF_LISTING_SAMPLE_LIMIT = 18
PDF_FEATURE_EXCEPTION_LIMIT = 18

HEADER_TEXT = "EMPIRE RESEARCH DIVISION"
FOOTER_TEXT = "PROPRIETARY / INTERNAL USE ONLY"
SUBTITLE = "Provider-Native Calculation and Publication Evidence"
DISCLAIMER_WARNING = (
    "Operational evidence only; not investment advice or a trading "
    "recommendation."
)
USE_LIMITATION = (
    "Operational calculation and publication evidence only. This report "
    "contains no investment advice, target, ranking, strategy, or trading "
    "recommendation. Values remain provider-native and may not be comparable "
    "across providers."
)

DAILY_TITLE = "Daily Technical Indicators Operational Report"
BACKFILL_TITLE = "Backfill Technical Indicators Operational Report"


TECH_INDICATORS_PDF_FEATURE_FAMILIES = (
    (
        "Returns",
        (
            "return_1d_pct",
            "return_2d_pct",
            "return_3d_pct",
            "return_5d_pct",
            "return_10d_pct",
            "return_20d_pct",
            "return_63d_pct",
            "return_126d_pct",
            "return_252d_pct",
        ),
    ),
    (
        "Bar structure and streaks",
        (
            "gap_1d_pct",
            "consecutive_up_days",
            "consecutive_down_days",
            "intraday_return_1d_pct",
            "daily_range_pct",
            "close_location_1d",
        ),
    ),
    (
        "Trend",
        (
            "sma_20",
            "sma_50",
            "sma_200",
            "ema_12",
            "ema_20",
            "ema_26",
            "ema_50",
            "sma_50_change_20d_pct",
            "sma_200_change_20d_pct",
            "pct_sma_20",
            "pct_sma_50",
            "pct_sma_200",
            "pct_ema_20",
            "pct_ema_50",
            "pct_sma_20_vs_50",
            "pct_sma_20_vs_200",
            "pct_sma_50_vs_200",
        ),
    ),
    (
        "Range",
        (
            "hh_20",
            "hh_50",
            "hh_252",
            "ll_20",
            "ll_50",
            "pct_hh_20",
            "pct_hh_50",
            "pct_hh_252",
            "pct_ll_20",
            "pct_ll_50",
        ),
    ),
    (
        "Momentum and volatility",
        (
            "rsi_14",
            "atr_14",
            "return_volatility_20d_pct",
            "return_volatility_60d_pct",
            "return_1d_zscore_20d",
            "return_3d_zscore_20d",
            "atr_pct_14",
        ),
    ),
    (
        "Bollinger",
        (
            "price_stddev_20",
            "bollinger_percent_b_20_2",
            "bollinger_bandwidth_20_2",
        ),
    ),
    (
        "Directional movement",
        ("plus_di_14", "minus_di_14", "adx_14"),
    ),
    (
        "MACD",
        (
            "macd_12_26",
            "macd_signal_12_26_9",
            "macd_histogram_12_26_9",
            "macd_12_26_pct",
            "macd_histogram_12_26_9_pct",
        ),
    ),
    (
        "Volume",
        (
            "volume_avg_20",
            "volume_avg_60",
            "dollar_volume_avg_20",
            "dollar_volume",
            "volume_ratio_20",
        ),
    ),
    (
        "SPX relative",
        (
            "rel_spx",
            "pct_rel_spx_20",
            "pct_rel_spx_50",
            "relative_return_spx_20d_pct",
            "relative_return_spx_63d_pct",
            "relative_return_spx_126d_pct",
            "relative_return_spx_252d_pct",
            "spx_beta_60d",
            "spx_beta_252d",
            "spx_correlation_60d",
            "spx_correlation_252d",
        ),
    ),
)


def _validate_feature_families() -> None:
    fields = tuple(
        field
        for _family, family_fields in TECH_INDICATORS_PDF_FEATURE_FAMILIES
        for field in family_fields
    )
    if len(fields) != len(set(fields)):
        raise RuntimeError("PDF feature families contain a duplicate field.")
    if set(fields) != set(REPORT_FEATURE_FIELDS):
        raise RuntimeError("PDF feature families do not cover the V1 inventory.")


_validate_feature_families()


@dataclass(frozen=True, slots=True)
class PdfFeatureFamilyCoverage:
    name: str
    field_count: int
    eligible: int
    populated: int
    warmup: int
    dependency: int
    unsupported: int
    unexpected: int

    @property
    def null_count(self) -> int:
        return self.warmup + self.dependency + self.unsupported + self.unexpected


def roll_up_pdf_feature_coverage(
    features: tuple[ReportFeatureCoverage, ...],
) -> tuple[PdfFeatureFamilyCoverage, ...]:
    """Aggregate immutable field counts into the frozen PDF family grains."""

    if tuple(item.feature_name for item in features) != REPORT_FEATURE_FIELDS:
        raise ValueError("features must contain the ordered V1 report inventory.")
    by_name = {item.feature_name: item for item in features}
    result: list[PdfFeatureFamilyCoverage] = []
    for name, field_names in TECH_INDICATORS_PDF_FEATURE_FAMILIES:
        rows = tuple(by_name[field_name] for field_name in field_names)
        result.append(
            PdfFeatureFamilyCoverage(
                name=name,
                field_count=len(rows),
                eligible=sum(item.eligible_row_count for item in rows),
                populated=sum(item.populated_count for item in rows),
                warmup=sum(item.warmup_null_count for item in rows),
                dependency=sum(item.dependency_null_count for item in rows),
                unsupported=sum(item.unsupported_null_count for item in rows),
                unexpected=sum(item.unexpected_null_count for item in rows),
            )
        )
    return tuple(result)


def render_tech_indicators_report_pdf(
    report: TechIndicatorsReport,
    *,
    output_dir: str | Path,
    filename: str = "report.pdf",
) -> RenderResult:
    """Render one immutable schema-V1 report as a bounded Empire PDF."""

    if not isinstance(report, TechIndicatorsReport):
        raise TypeError("report must be a TechIndicatorsReport.")
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".pdf":
        raise ValueError("filename must be a local .pdf filename.")

    title = (
        DAILY_TITLE
        if report.workflow_kind is WorkflowKind.DAILY
        else BACKFILL_TITLE
    )
    metadata = ReportMetadata(
        report_id=report.report_id,
        title=title,
        subtitle=SUBTITLE,
        as_of=report.identity.effective_date,
        generated_at=report.generated_at,
        description=(
            "Provider-native technical-indicator calculation and publication "
            "evidence."
        ),
        tags=("stonks", "technical-indicators", report.workflow_kind.value.lower()),
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(
            output_dir=Path(output_dir),
            run_id=report.identity.run_id,
        ),
    )
    story = [
        *professional_letter_title_page(
            title=title,
            subtitle=SUBTITLE,
            report_date=report.identity.effective_date,
            header_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
            classification_text=FOOTER_TEXT,
            date_label="EFFECTIVE DATE",
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        NextPageTemplate("letter_title"),
        PageBreak(),
        *professional_letter_disclaimer_page(
            header_text=HEADER_TEXT,
            footer_text=FOOTER_TEXT,
            warning_text=DISCLAIMER_WARNING,
            assets=renderer.assets,
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        NextPageTemplate("letter_body"),
        PageBreak(),
        *_body_story(report, renderer=renderer),
    ]
    header_footer = HeaderFooterSpec(
        header_center_text=HEADER_TEXT,
        header_right_text=_scope_header(report),
        footer_text=FOOTER_TEXT,
        page_number_offset=2,
    )
    templates = renderer.default_templates(header_footer)
    templates.get("letter_title").autoNextPageTemplate = "letter_title"
    templates.get("letter_body").autoNextPageTemplate = "letter_body"
    return renderer.render(
        story,
        out_path=Path(output_dir) / filename,
        templates=templates,
        maximum_pages=PDF_MAXIMUM_PAGES,
        maximum_bytes=PDF_MAXIMUM_BYTES,
    )


def _body_story(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    return [
        *_executive_section(report, renderer=renderer),
        spacer(12),
        *_scope_section(report, renderer=renderer),
        spacer(12),
        *_coverage_section(report, renderer=renderer),
        PageBreak(),
        *_feature_quality_section(report, renderer=renderer),
        PageBreak(),
        *_benchmark_section(report, renderer=renderer),
        PageBreak(),
        *_performance_section(report, renderer=renderer),
        PageBreak(),
        *_issues_section(report, renderer=renderer),
        PageBreak(),
        *_methodology_section(report, renderer=renderer),
    ]


def _executive_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    publication_label = (
        f"{report.publication.report_phase.value} / "
        f"{report.publication.readiness_at_report.value}"
    )
    return [
        _heading("Executive Status", renderer=renderer),
        _status_banner(report, renderer=renderer),
        spacer(8),
        paragraph(_outcome_sentence(report.outcome), styles=renderer.styles),
        _callout(USE_LIMITATION, renderer=renderer),
        spacer(8),
        _table(
            [
                ["Run Fact", "Value"],
                ["Workflow", report.workflow_kind.value],
                ["Report ID", _code_cell(report.report_id, renderer=renderer)],
                ["Schema version", report.schema_version],
                ["Run ID", _code_cell(report.identity.run_id, renderer=renderer)],
                ["Core subject", report.identity.core_subject_key],
                ["Effective date", report.identity.effective_date],
                ["Generated at", _format_datetime(report.generated_at)],
                [
                    "Publication ID",
                    _code_cell(report.identity.publication_id, renderer=renderer),
                ],
                [
                    "Existing readiness token",
                    _code_cell(
                        report.identity.existing_readiness_token,
                        renderer=renderer,
                    ),
                ],
                ["Publication snapshot", publication_label],
            ],
            renderer=renderer,
            col_widths=(160, 344),
        ),
        spacer(8),
        _table(
            [
                ["Operational Count", "Value"],
                ["Selected listings", _fmt_int(report.counts.selected_listing_count)],
                ["Source rows", _fmt_int(report.counts.source_row_count)],
                ["Evaluated rows", _fmt_int(report.counts.evaluated_row_count)],
                ["Payload rows", _fmt_int(report.counts.payload_row_count)],
                ["Published rows", _fmt_int(report.counts.published_row_count)],
                [
                    "Persisted (inserted + updated)",
                    _fmt_int(report.writes.persisted_rows),
                ],
                ["Warning events", _fmt_int(_issue_count(report.warnings))],
                ["Failure events", _fmt_int(_issue_count(report.failures))],
            ],
            renderer=renderer,
            col_widths=(300, 204),
            numeric_columns=(1,),
        ),
    ]


def _scope_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    scope = report.scope
    content: list[object] = [
        _heading("Scope And Readiness", renderer=renderer),
        _subheading("Resolved Scope", renderer=renderer),
        _table(
            [
                ["Scope Fact", "Value"],
                ["Scope schema", scope.scope_schema_version],
                ["Scope hash", _code_cell(scope.scope_hash, renderer=renderer)],
                ["Effective date", _display(scope.effective_date)],
                ["Start date", _display(scope.start_date)],
                ["End date", _display(scope.end_date)],
                ["Providers", _selectors(scope.provider_codes)],
                ["Markets", _selectors(scope.markets)],
                ["Instrument types", _selectors(scope.instrument_type_codes)],
                ["Requested listings", _fmt_int(scope.requested_listing_count)],
                ["Resolved listings", _fmt_int(scope.resolved_listing_count)],
                ["Include inactive", _yes_no(scope.include_inactive)],
                ["Dry run", _yes_no(scope.dry_run)],
                ["Force", _yes_no(scope.force)],
                ["Rebuild", _yes_no(scope.rebuild)],
            ],
            renderer=renderer,
            col_widths=(160, 344),
        ),
        spacer(8),
        _subheading("Writer Lock", renderer=renderer),
        _table(
            [
                ["Lock Fact", "Value"],
                ["Name", _code_cell(report.lock.name, renderer=renderer)],
                ["Key", _code_cell(report.lock.key, renderer=renderer)],
                ["Outcome", report.lock.outcome.value],
                ["Heartbeats", _fmt_int(report.lock.heartbeat_count)],
                [
                    "Heartbeat failures",
                    _fmt_int(report.lock.heartbeat_failure_count),
                ],
                ["Held through report", _yes_no(report.lock.held_through_report)],
            ],
            renderer=renderer,
            col_widths=(160, 344),
        ),
        spacer(8),
        _subheading("Source Readiness", renderer=renderer),
        _table(
            [
                ["Decision", "Date / Range", "Reason Events"],
                [
                    report.source_readiness.decision.value,
                    _source_readiness_date(report),
                    _fmt_int(
                        sum(
                            item.count
                            for item in report.source_readiness.reason_counts
                        )
                    ),
                ],
            ],
            renderer=renderer,
            col_widths=(150, 230, 124),
            numeric_columns=(2,),
        ),
        _reason_table(
            report.source_readiness.reason_counts,
            empty_text="No source-readiness reasons.",
            renderer=renderer,
        ),
        _provider_evidence_table(report, renderer=renderer),
        _source_benchmark_table(report, renderer=renderer),
        spacer(8),
        _subheading("Publication", renderer=renderer),
        _publication_table(report, renderer=renderer),
        _reason_table(
            report.publication.readiness_reason_counts,
            empty_text="No publication-readiness reasons.",
            renderer=renderer,
        ),
    ]
    if report.backfill.applicable:
        content.extend(
            [
                spacer(8),
                _subheading("Backfill Progress", renderer=renderer),
                _backfill_table(report, renderer=renderer),
            ]
        )
    else:
        content.append(
            paragraph(
                "Backfill progress: Not applicable.",
                styles=renderer.styles,
            )
        )
    return content


def _coverage_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    counts = report.counts
    dates = report.coverage.date
    content: list[object] = [
        _heading("Coverage And Writes", renderer=renderer),
        paragraph(
            "Counts retain their declared listing and row grains. Provider, "
            "market, and instrument-type dimensions are not added together.",
            styles=renderer.styles,
        ),
        _table(
            [
                ["Coverage Fact", "Value"],
                ["Eligible listings", _fmt_int(counts.eligible_listing_count)],
                ["Selected listings", _fmt_int(counts.selected_listing_count)],
                ["Source listings", _fmt_int(counts.source_listing_count)],
                ["Source rows", _fmt_int(counts.source_row_count)],
                ["Evaluated rows", _fmt_int(counts.evaluated_row_count)],
                ["Payload rows", _fmt_int(counts.payload_row_count)],
                ["Published listings", _fmt_int(counts.published_listing_count)],
                ["Published rows", _fmt_int(counts.published_row_count)],
            ],
            renderer=renderer,
            col_widths=(300, 204),
            numeric_columns=(1,),
        ),
    ]
    for title, values in (
        ("Provider Coverage", counts.providers),
        ("Market Coverage", counts.markets),
        ("Instrument-Type Coverage", counts.instrument_types),
    ):
        content.extend(
            [
                spacer(8),
                _subheading(title, renderer=renderer),
                _dimension_table(values, renderer=renderer),
            ]
        )
    content.extend(
        [
            spacer(8),
            _subheading("Date Coverage", renderer=renderer),
            _table(
                [
                    ["Date Fact", "Value"],
                    ["Source first date", _display_date(dates.source_first_date)],
                    ["Source last date", _display_date(dates.source_last_date)],
                    ["Payload first date", _display_date(dates.payload_first_date)],
                    ["Payload last date", _display_date(dates.payload_last_date)],
                    [
                        "Effective-date source rows",
                        _fmt_int(dates.effective_date_source_rows),
                    ],
                    [
                        "Effective-date payload rows",
                        _fmt_int(dates.effective_date_payload_rows),
                    ],
                    [
                        "Effective-date published rows",
                        _fmt_int(dates.effective_date_published_rows),
                    ],
                ],
                renderer=renderer,
                col_widths=(300, 204),
                numeric_columns=(1,),
            ),
            spacer(8),
            _subheading("Calculation-Version Coverage", renderer=renderer),
            _version_table(report, renderer=renderer),
            spacer(8),
            _subheading("Write Outcomes", renderer=renderer),
            _write_table(report, renderer=renderer),
        ]
    )
    return content


def _feature_quality_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    summaries = roll_up_pdf_feature_coverage(report.coverage.features)
    unexpected = tuple(
        item
        for item in report.coverage.features
        if item.unexpected_null_count
    )
    other = tuple(
        item
        for item in report.coverage.features
        if not item.unexpected_null_count
        and (item.dependency_null_count or item.unsupported_null_count)
    )
    shown = unexpected + other[:PDF_FEATURE_EXCEPTION_LIMIT]
    total_exceptions = len(unexpected) + len(other)
    content: list[object] = [
        _heading("Feature Quality", renderer=renderer),
        paragraph(
            "Family totals count feature-observations, not source rows or "
            "listings. The adjacent table is authoritative for chart values.",
            styles=renderer.styles,
        ),
        _feature_chart(summaries, renderer=renderer),
        spacer(6),
        _feature_family_table(summaries, renderer=renderer),
        spacer(10),
        _subheading("Feature Exceptions", renderer=renderer),
        paragraph(
            f"Showing {len(shown):,} of {total_exceptions:,} feature "
            "exceptions. Every unexpected-null feature is retained; up to "
            f"{PDF_FEATURE_EXCEPTION_LIMIT:,} additional dependency or "
            "unsupported exceptions follow in profile order. Complete "
            "per-feature counts remain in report.json.",
            styles=renderer.styles,
        ),
        _feature_exception_table(shown, renderer=renderer),
    ]
    return content


def _benchmark_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    source = report.source_readiness.benchmark
    coverage = report.coverage.benchmark
    return [
        _heading("Benchmark Health", renderer=renderer),
        paragraph(
            "Reviewed benchmark: YAHOO / XIDX / SPX. Exact-date alignment; "
            "no forward fill. Window counts below are rows, not listings.",
            styles=renderer.styles,
        ),
        _table(
            [
                ["Benchmark Fact", "Value"],
                ["Required", _yes_no(source.required)],
                ["Ready", _yes_no(source.ready)],
                [
                    "Provider listing ID",
                    _code_cell(source.provider_listing_id, renderer=renderer),
                ],
                [
                    "Effective-date bar present",
                    _yes_no(source.effective_date_bar_present),
                ],
                [
                    "Publication benchmark ID",
                    _code_cell(
                        report.publication.benchmark_provider_listing_id,
                        renderer=renderer,
                    ),
                ],
                [
                    "Benchmark contract",
                    _display(report.publication.benchmark_contract_version),
                ],
                ["Alignment", "EXACT_DATE_NO_FILL"],
            ],
            renderer=renderer,
            col_widths=(190, 314),
        ),
        spacer(10),
        _table(
            [
                ["Coverage Fact", "Rows / Listings"],
                ["Supported listings", _fmt_int(coverage.supported_listing_count)],
                [
                    "Unsupported listings",
                    _fmt_int(coverage.unsupported_listing_count),
                ],
                [
                    "Benchmark-linked rows",
                    _fmt_int(coverage.benchmark_linked_row_count),
                ],
                [
                    "Benchmark-unlinked rows",
                    _fmt_int(coverage.benchmark_unlinked_row_count),
                ],
                ["Aligned rows", _fmt_int(coverage.aligned_row_count)],
                [
                    "Effective-date aligned rows",
                    _fmt_int(coverage.effective_date_aligned_count),
                ],
                ["Complete 20-observation rows", _fmt_int(coverage.complete_20_count)],
                ["Complete 50-observation rows", _fmt_int(coverage.complete_50_count)],
                ["Complete 60-observation rows", _fmt_int(coverage.complete_60_count)],
                ["Complete 63-observation rows", _fmt_int(coverage.complete_63_count)],
                [
                    "Complete 126-observation rows",
                    _fmt_int(coverage.complete_126_count),
                ],
                [
                    "Complete 252-observation rows",
                    _fmt_int(coverage.complete_252_count),
                ],
            ],
            renderer=renderer,
            col_widths=(300, 204),
            numeric_columns=(1,),
        ),
        spacer(10),
        _callout(
            "SPX-relative output is provider-native operational evidence. It "
            "is not total-return alpha and does not establish adjustment or "
            "currency comparability.",
            renderer=renderer,
        ),
    ]


def _performance_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    performance = report.performance
    throughput = performance.throughput
    database = performance.database
    content: list[object] = [
        _heading("Performance", renderer=renderer),
        paragraph(
            "These are measured workflow facts, not a release-readiness or "
            "performance recommendation.",
            styles=renderer.styles,
        ),
        _table(
            [
                ["Performance Fact", "Value"],
                ["Started at", _format_datetime(performance.started_at)],
                ["Finished at", _format_datetime(performance.finished_at)],
                ["Wall elapsed", _fmt_seconds(performance.elapsed_seconds)],
                ["Peak RSS", _fmt_bytes(performance.peak_rss_bytes)],
                ["Evaluated rows", _fmt_int(throughput.evaluated_rows)],
                ["Persisted rows", _fmt_int(throughput.persisted_rows)],
                ["Throughput elapsed", _fmt_seconds(throughput.elapsed_seconds)],
                [
                    "Evaluated rows / second",
                    _fmt_rate(throughput.evaluated_rows_per_second),
                ],
                [
                    "Persisted rows / second",
                    _fmt_rate(throughput.persisted_rows_per_second),
                ],
                ["Read pages", _fmt_int(database.read_page_count)],
                ["Write batches", _fmt_int(database.write_batch_count)],
                ["Largest read page rows", _fmt_int(database.largest_read_page_rows)],
                [
                    "Largest write batch rows",
                    _fmt_int(database.largest_write_batch_rows),
                ],
                [
                    "Longest write transaction",
                    _fmt_optional_seconds(
                        database.longest_write_transaction_seconds
                    ),
                ],
            ],
            renderer=renderer,
            col_widths=(270, 234),
        ),
        spacer(10),
        _subheading("Recorded Phase Durations", renderer=renderer),
        paragraph(
            "Recorded phases are non-overlapping and may sum to less than wall "
            "time.",
            styles=renderer.styles,
        ),
    ]
    phase_rows: list[list[object]] = [["Phase", "Elapsed Seconds"]]
    phase_rows.extend(
        [item.phase, f"{item.elapsed_seconds:,.3f}"]
        for item in performance.phases
    )
    if not performance.phases:
        phase_rows.append(["No recorded phases", "-"])
    content.append(
        _table(
            phase_rows,
            renderer=renderer,
            col_widths=(354, 150),
            numeric_columns=(1,),
        )
    )
    return content


def _issues_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    categorized, omitted = _bounded_diagnostic_samples(report)
    content: list[object] = [
        _heading("Warnings And Failures", renderer=renderer),
        paragraph(
            "Aggregate event counts are complete. Diagnostic rows are bounded; "
            "report.json remains authoritative for every retained sample.",
            styles=renderer.styles,
        ),
        _subheading("Failures", renderer=renderer),
        _issue_aggregate_table(
            report.failures,
            empty_text="No retained failures.",
            renderer=renderer,
        ),
        spacer(8),
        _subheading("Warnings", renderer=renderer),
        _issue_aggregate_table(
            report.warnings,
            empty_text="No retained warnings.",
            renderer=renderer,
        ),
    ]
    if not report.diagnostic_samples:
        content.extend(
            [
                spacer(8),
                paragraph(
                    "No bounded diagnostic samples were retained.",
                    styles=renderer.styles,
                ),
            ]
        )
        return content

    for category in ("Failure", "Warning", "Readiness", "Coverage"):
        samples = categorized[category]
        category_omitted = omitted[category]
        content.extend(
            [
                spacer(8),
                _subheading(f"{category} Diagnostics", renderer=renderer),
                paragraph(
                    f"Showing {len(samples):,} rows; {category_omitted:,} "
                    "additional rows were omitted by the fixed PDF sample or "
                    "listing ceiling.",
                    styles=renderer.styles,
                ),
                _diagnostic_table(samples, renderer=renderer),
            ]
        )
    return content


def _methodology_section(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> list[object]:
    versions = report.versions
    content: list[object] = [
        _heading("Methodology And Disclosures", renderer=renderer),
        _subheading("Versioned Calculation Profile", renderer=renderer),
        _table(
            [
                ["Version Fact", "Value"],
                ["Report schema", report.schema_version],
                ["Package", versions.package_version],
                ["Calculation", versions.calculation_version],
                ["Benchmark contract", versions.benchmark_contract_version],
                ["Python", versions.python_version],
                ["NumPy", versions.numpy_version],
                ["TA-Lib Python", versions.talib_python_version],
                ["TA-Lib C", versions.talib_c_version],
                ["PostgreSQL", _display(versions.postgresql_version)],
            ],
            renderer=renderer,
            col_widths=(180, 324),
        ),
        spacer(10),
        _subheading("Calculation Method", renderer=renderer),
        paragraph(
            "The V1 profile contains 76 analytical fields: 53 are computed in "
            "Python and 23 are PostgreSQL stored generated expressions. "
            "Lookbacks use chronological stored observations and complete "
            "windows. Expected warm-up and dependency conditions remain null "
            "rather than sentinel zero. Percentage fields store decimal ratios. "
            "Unexpected post-warm-up null or non-finite output fails validation.",
            styles=renderer.styles,
        ),
        paragraph(
            "The calculator reads provider-native current-state OHLCV and is "
            "sensitive to provider corrections. It does not create canonical "
            "identity, cross-provider normalization, or corporate-action "
            "normalization. SPX uses exact-date alignment without fill. Nominal "
            "dollar volume is provider-native price times volume and is not "
            "asserted to be USD or cross-listing comparable.",
            styles=renderer.styles,
        ),
        spacer(8),
        _subheading("Provider-Native Disclosures", renderer=renderer),
    ]
    if report.native_value_semantics.notes:
        rows: list[list[object]] = [["Disclosure Code", "Reviewed Meaning"]]
        rows.extend(
            [code, NATIVE_VALUE_NOTE_MESSAGES[code]]
            for code in report.native_value_semantics.notes
        )
        content.append(
            _table(
                rows,
                renderer=renderer,
                col_widths=(220, 284),
            )
        )
    else:
        content.append(
            paragraph(
                "No provider-specific disclosure applies to this empty scope.",
                styles=renderer.styles,
            )
        )
    content.extend(
        [
            spacer(10),
            _callout(USE_LIMITATION, renderer=renderer),
        ]
    )
    return content


def _status_banner(report: TechIndicatorsReport, *, renderer: PdfRenderer) -> Table:
    label = {
        ReportOutcome.PASS: "PASS",
        ReportOutcome.WARN: "WARN",
        ReportOutcome.NO_OP: "NO OP",
        ReportOutcome.PARTIAL: "PARTIAL - UNPUBLISHED",
        ReportOutcome.FAIL: "FAIL - UNPUBLISHED",
    }[report.outcome]
    color = {
        ReportOutcome.PASS: HexColor("#1F6B45"),
        ReportOutcome.WARN: HexColor("#A66500"),
        ReportOutcome.NO_OP: HexColor("#40566F"),
        ReportOutcome.PARTIAL: HexColor("#A66500"),
        ReportOutcome.FAIL: renderer.theme.primary,
    }[report.outcome]
    table = Table([[label]], colWidths=[504])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("TEXTCOLOR", (0, 0), (-1, -1), renderer.theme.white),
                ("FONTNAME", (0, 0), (-1, -1), renderer.theme.body_bold_font),
                ("FONTSIZE", (0, 0), (-1, -1), 15),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _callout(text: str, *, renderer: PdfRenderer) -> Table:
    table = Table(
        [[Paragraph(escape(text), renderer.styles.body)]],
        colWidths=[504],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), "#F3F3F3"),
                ("BOX", (0, 0), (-1, -1), 1.0, renderer.theme.primary),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _provider_evidence_table(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [[
        "Provider",
        "Requirement",
        "Evidence",
        "Run Count",
        "Listings",
        "Rows",
        "Date Rows",
    ]]
    for item in report.source_readiness.provider_evidence:
        requirement = "Required" if item.required else "Informational"
        evidence = "Ready" if item.ready else "Not ready"
        rows.append(
            [
                item.provider_code,
                requirement,
                evidence,
                _fmt_int(item.successful_run_count),
                _fmt_int(item.source_listing_count),
                _fmt_int(item.source_row_count),
                _fmt_int(item.effective_date_row_count),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Not evaluated", "-", "0", "0", "0", "0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(74, 80, 66, 64, 66, 78, 76),
        numeric_columns=(3, 4, 5, 6),
    )


def _source_benchmark_table(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    benchmark = report.source_readiness.benchmark
    return _table(
        [
            ["Source Benchmark", "Required", "Ready", "Effective Date", "Listing ID"],
            [
                f"{benchmark.provider_code}/{benchmark.market}/{benchmark.ticker}",
                _yes_no(benchmark.required),
                _yes_no(benchmark.ready),
                _yes_no(benchmark.effective_date_bar_present),
                _code_cell(benchmark.provider_listing_id, renderer=renderer),
            ],
        ],
        renderer=renderer,
        col_widths=(116, 64, 58, 92, 174),
    )


def _publication_table(
    report: TechIndicatorsReport,
    *,
    renderer: PdfRenderer,
) -> Table:
    publication = report.publication
    cursor = publication.resume_cursor
    return _table(
        [
            ["Publication Fact", "Value"],
            ["Method", publication.method.value],
            ["Report phase", publication.report_phase.value],
            ["Candidate status", _display(publication.candidate_status)],
            ["Readiness at report", publication.readiness_at_report.value],
            ["Publication listings", _fmt_int(publication.publication_listing_count)],
            [
                "Publication source rows",
                _fmt_int(publication.publication_source_row_count),
            ],
            [
                "Publication payload rows",
                _fmt_int(publication.publication_payload_row_count),
            ],
            [
                "Benchmark listing ID",
                _code_cell(
                    publication.benchmark_provider_listing_id,
                    renderer=renderer,
                ),
            ],
            ["Benchmark contract", _display(publication.benchmark_contract_version)],
            ["Resume cursor", _cursor_text(cursor)],
        ],
        renderer=renderer,
        col_widths=(190, 314),
    )


def _backfill_table(report: TechIndicatorsReport, *, renderer: PdfRenderer) -> Table:
    backfill = report.backfill
    return _table(
        [
            ["Progress Fact", "Value"],
            ["Batch size", _display_number(backfill.batch_size)],
            ["Planned batches", _display_number(backfill.planned_batch_count)],
            ["Completed batches", _fmt_int(backfill.completed_batch_count)],
            ["Resumed from", _cursor_text(backfill.resumed_from_cursor)],
            ["Last completed", _cursor_text(backfill.last_completed_cursor)],
            ["Remaining listings", _fmt_int(backfill.remaining_listing_count)],
            ["Remaining rows", _fmt_int(backfill.remaining_row_count)],
        ],
        renderer=renderer,
        col_widths=(190, 314),
    )


def _dimension_table(
    values: tuple[ReportDimensionCount, ...],
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [
        ["Code", "Listings", "Source", "Evaluated", "Payload", "Published"]
    ]
    rows.extend(
        [
            item.code,
            _fmt_int(item.listing_count),
            _fmt_int(item.source_row_count),
            _fmt_int(item.evaluated_row_count),
            _fmt_int(item.payload_row_count),
            _fmt_int(item.published_row_count),
        ]
        for item in values
    )
    if len(rows) == 1:
        rows.append(["No rows", "0", "0", "0", "0", "0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(104, 68, 80, 82, 80, 90),
        numeric_columns=(1, 2, 3, 4, 5),
    )


def _version_table(report: TechIndicatorsReport, *, renderer: PdfRenderer) -> Table:
    rows: list[list[object]] = [["Calculation Version", "Listings", "Rows"]]
    rows.extend(
        [
            item.calculation_version,
            _fmt_int(item.listing_count),
            _fmt_int(item.row_count),
        ]
        for item in report.coverage.versions
    )
    if len(rows) == 1:
        rows.append(["No data", "0", "0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(304, 100, 100),
        numeric_columns=(1, 2),
    )


def _write_table(report: TechIndicatorsReport, *, renderer: PdfRenderer) -> Table:
    writes = report.writes
    return _table(
        [
            ["Write Outcome", "Count"],
            ["Inserted", _fmt_int(writes.inserted)],
            ["Updated", _fmt_int(writes.updated)],
            ["Persisted (inserted + updated)", _fmt_int(writes.persisted_rows)],
            ["Deleted", _fmt_int(writes.deleted)],
            ["Equivalent", _fmt_int(writes.equivalent)],
            ["Copied equivalent", _fmt_int(writes.copied_equivalent)],
            ["Unchanged", _fmt_int(writes.unchanged)],
            ["Failed", _fmt_int(writes.failed)],
            ["Batches", _fmt_int(writes.batch_count)],
            ["Committed batches", _fmt_int(writes.committed_batch_count)],
            ["Rolled-back batches", _fmt_int(writes.rolled_back_batch_count)],
        ],
        renderer=renderer,
        col_widths=(354, 150),
        numeric_columns=(1,),
    )


def _feature_family_table(
    values: tuple[PdfFeatureFamilyCoverage, ...],
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [[
        "Family",
        "Fields",
        "Eligible",
        "Populated",
        "Warm-up",
        "Dependency",
        "Unsupported",
        "Unexpected",
    ]]
    rows.extend(
        [
            item.name,
            _fmt_int(item.field_count),
            _fmt_int(item.eligible),
            _fmt_int(item.populated),
            _fmt_int(item.warmup),
            _fmt_int(item.dependency),
            _fmt_int(item.unsupported),
            _fmt_int(item.unexpected),
        ]
        for item in values
    )
    return _table(
        rows,
        renderer=renderer,
        col_widths=(96, 40, 59, 62, 59, 65, 67, 56),
        numeric_columns=(1, 2, 3, 4, 5, 6, 7),
    )


def _feature_exception_table(
    values: tuple[ReportFeatureCoverage, ...],
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [[
        "Feature",
        "Eligible",
        "Populated",
        "Warm-up",
        "Dependency",
        "Unsupported",
        "Unexpected",
    ]]
    rows.extend(
        [
            item.feature_name,
            _fmt_int(item.eligible_row_count),
            _fmt_int(item.populated_count),
            _fmt_int(item.warmup_null_count),
            _fmt_int(item.dependency_null_count),
            _fmt_int(item.unsupported_null_count),
            _fmt_int(item.unexpected_null_count),
        ]
        for item in values
    )
    if len(rows) == 1:
        rows.append(["No feature exceptions", "0", "0", "0", "0", "0", "0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(130, 62, 64, 58, 65, 69, 56),
        numeric_columns=(1, 2, 3, 4, 5, 6),
    )


def _feature_chart(
    values: tuple[PdfFeatureFamilyCoverage, ...],
    *,
    renderer: PdfRenderer,
) -> Drawing:
    drawing = Drawing(504, 190)
    label_x = 0
    bar_x = 145
    bar_width = 245
    value_x = 400
    top = 172
    row_height = 17
    drawing.add(
        String(
            0,
            181,
            "Populated Feature-Observations by Family",
            fontName=renderer.theme.body_semibold_font,
            fontSize=9,
            fillColor=renderer.theme.dark_grey,
        )
    )
    for index, item in enumerate(values):
        y = top - (index * row_height)
        ratio = 0.0 if not item.eligible else item.populated / item.eligible
        drawing.add(
            String(
                label_x,
                y,
                item.name,
                fontName=renderer.theme.body_font,
                fontSize=7.5,
                fillColor=renderer.theme.dark_grey,
            )
        )
        drawing.add(
            Rect(
                bar_x,
                y - 1,
                bar_width,
                8,
                fillColor=renderer.theme.light_grey,
                strokeColor=None,
            )
        )
        drawing.add(
            Rect(
                bar_x,
                y - 1,
                bar_width * ratio,
                8,
                fillColor=HexColor("#1F6B45"),
                strokeColor=None,
            )
        )
        drawing.add(
            String(
                value_x,
                y,
                f"{item.populated:,}/{item.eligible:,} ({ratio:.1%})",
                fontName=renderer.theme.body_font,
                fontSize=7.5,
                fillColor=renderer.theme.dark_grey,
            )
        )
    return drawing


def _issue_aggregate_table(
    values: tuple[ReportIssueAggregate, ...],
    *,
    empty_text: str,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [["Code", "Count", "Sample IDs", "Fixed Message"]]
    rows.extend(
        [
            item.code,
            _fmt_int(item.count),
            _selectors(item.sample_ids, empty="None"),
            item.message,
        ]
        for item in values
    )
    if len(rows) == 1:
        rows.append([empty_text, "0", "None", "-"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(126, 48, 110, 220),
        numeric_columns=(1,),
    )


def _diagnostic_table(
    values: tuple[ReportDiagnosticSample, ...],
    *,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [[
        "ID",
        "Code",
        "Provider / Market / Ticker",
        "Listing UUID",
        "Date",
        "Field",
        "Fixed Message",
    ]]
    rows.extend(
        [
            item.sample_id,
            item.code,
            " / ".join(
                value or "-"
                for value in (item.provider_code, item.market, item.ticker)
            ),
            _display(item.provider_listing_id),
            _display_date(item.trading_date),
            _display(item.field_name),
            item.message,
        ]
        for item in values
    )
    if len(rows) == 1:
        rows.append(["-", "No samples", "-", "-", "-", "-", "-"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(30, 64, 92, 112, 52, 66, 88),
    )


def _reason_table(
    values: tuple[object, ...],
    *,
    empty_text: str,
    renderer: PdfRenderer,
) -> Table:
    rows: list[list[object]] = [["Reason Code", "Count"]]
    rows.extend([item.code, _fmt_int(item.count)] for item in values)
    if len(rows) == 1:
        rows.append([empty_text, "0"])
    return _table(
        rows,
        renderer=renderer,
        col_widths=(354, 150),
        numeric_columns=(1,),
    )


def _bounded_diagnostic_samples(
    report: TechIndicatorsReport,
) -> tuple[
    dict[str, tuple[ReportDiagnosticSample, ...]],
    dict[str, int],
]:
    failure_ids = {
        sample_id for item in report.failures for sample_id in item.sample_ids
    }
    warning_ids = {
        sample_id for item in report.warnings for sample_id in item.sample_ids
    }
    readiness_codes = {
        item.code for item in report.source_readiness.reason_counts
    } | {item.code for item in report.publication.readiness_reason_counts}
    assigned: dict[str, list[ReportDiagnosticSample]] = {
        "Failure": [],
        "Warning": [],
        "Readiness": [],
        "Coverage": [],
    }
    for sample in report.diagnostic_samples:
        if sample.sample_id in failure_ids:
            category = "Failure"
        elif sample.sample_id in warning_ids:
            category = "Warning"
        elif sample.code in readiness_codes:
            category = "Readiness"
        else:
            category = "Coverage"
        assigned[category].append(sample)

    shown: dict[str, tuple[ReportDiagnosticSample, ...]] = {}
    omitted: dict[str, int] = {}
    listing_ids: set[object] = set()
    for category, samples in assigned.items():
        kept: list[ReportDiagnosticSample] = []
        for sample in samples:
            if len(kept) >= PDF_DIAGNOSTIC_SAMPLE_LIMIT:
                continue
            listing_id = sample.provider_listing_id
            if (
                listing_id is not None
                and listing_id not in listing_ids
                and len(listing_ids) >= PDF_LISTING_SAMPLE_LIMIT
            ):
                continue
            kept.append(sample)
            if listing_id is not None:
                listing_ids.add(listing_id)
        shown[category] = tuple(kept)
        omitted[category] = len(samples) - len(kept)
    return shown, omitted


def _table(
    rows: list[list[object]],
    *,
    renderer: PdfRenderer,
    col_widths: tuple[float, ...],
    numeric_columns: tuple[int, ...] = (),
) -> Table:
    if not rows or any(len(row) != len(col_widths) for row in rows):
        raise ValueError("table rows must match the declared column widths.")
    body_style = ParagraphStyle(
        "TechIndicatorsPdfTableBody",
        parent=renderer.styles.small,
        spaceAfter=0,
    )
    header_style = ParagraphStyle(
        "TechIndicatorsPdfTableHeader",
        parent=renderer.styles.small,
        fontName=renderer.theme.body_semibold_font,
        textColor=renderer.theme.white,
        spaceAfter=0,
    )
    data: list[list[object]] = []
    for row_index, row in enumerate(rows):
        if row_index == 0:
            data.append(
                [Paragraph(escape(str(cell)), header_style) for cell in row]
            )
        else:
            data.append(
                [
                    cell
                    if isinstance(cell, Paragraph)
                    else Paragraph(escape(str(cell)), body_style)
                    for cell in row
                ]
            )
    table = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
    commands: list[tuple[object, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), renderer.theme.primary),
        ("TEXTCOLOR", (0, 0), (-1, 0), renderer.theme.white),
        ("FONTNAME", (0, 0), (-1, 0), renderer.theme.body_semibold_font),
        ("FONTNAME", (0, 1), (-1, -1), renderer.theme.body_font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.25, renderer.theme.light_grey),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [renderer.theme.white, "#F7F7F7"],
        ),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    commands.extend(
        ("ALIGN", (column, 1), (column, -1), "RIGHT")
        for column in numeric_columns
    )
    table.setStyle(TableStyle(commands))
    return table


def _heading(text: str, *, renderer: PdfRenderer) -> Paragraph:
    heading = section_heading(text, styles=renderer.styles)
    heading.keepWithNext = 1
    return heading


def _code_cell(value: object | None, *, renderer: PdfRenderer) -> Paragraph:
    style = ParagraphStyle(
        "TechIndicatorsPdfCodeCell",
        parent=renderer.styles.code,
        fontSize=7.2,
        leading=9,
        spaceAfter=0,
    )
    return Paragraph(escape(_display(value)), style)


def _subheading(text: str, *, renderer: PdfRenderer) -> Paragraph:
    heading = Paragraph(escape(text), renderer.styles.subheading)
    heading.keepWithNext = 1
    return heading


def _scope_header(report: TechIndicatorsReport) -> str:
    if report.workflow_kind is WorkflowKind.DAILY:
        return report.identity.effective_date.isoformat()
    return f"{report.scope.start_date} - {report.scope.end_date}"


def _source_readiness_date(report: TechIndicatorsReport) -> str:
    if report.source_readiness.effective_date is not None:
        return report.source_readiness.effective_date.isoformat()
    if report.workflow_kind is WorkflowKind.BACKFILL:
        return f"{report.scope.start_date} - {report.scope.end_date}"
    return "Not evaluated"


def _outcome_sentence(outcome: ReportOutcome) -> str:
    return {
        ReportOutcome.PASS: (
            "The workflow completed with no retained warning or failure."
        ),
        ReportOutcome.WARN: (
            "The workflow completed with retained warnings requiring review."
        ),
        ReportOutcome.NO_OP: (
            "Ready source and publication evidence required no feature mutation."
        ),
        ReportOutcome.PARTIAL: (
            "Backfill progress is safely resumable and remains unpublished."
        ),
        ReportOutcome.FAIL: (
            "The workflow failed and no incomplete candidate became published."
        ),
    }[outcome]


def _cursor_text(cursor: ReportCursor | None) -> str:
    if cursor is None:
        return "Not applicable"
    return (
        f"batch {cursor.batch_number}; listing {cursor.provider_listing_id}; "
        f"date {_display_date(cursor.trading_date)}"
    )


def _issue_count(values: tuple[ReportIssueAggregate, ...]) -> int:
    return sum(item.count for item in values)


def _selectors(values: tuple[str, ...], *, empty: str = "All eligible") -> str:
    return ", ".join(values) if values else empty


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_seconds(value: float) -> str:
    return f"{value:,.3f} seconds"


def _fmt_optional_seconds(value: float | None) -> str:
    return "Not measured" if value is None else _fmt_seconds(value)


def _fmt_rate(value: float | None) -> str:
    return "Not available" if value is None else f"{value:,.3f}"


def _fmt_bytes(value: int | None) -> str:
    if value is None:
        return "Not measured"
    return f"{value:,} bytes ({value / (1024 * 1024):,.2f} MiB)"


def _display(value: object | None) -> str:
    return "-" if value is None else str(value)


def _display_date(value: object | None) -> str:
    return "No data" if value is None else str(value)


def _display_number(value: int | None) -> str:
    return "Not applicable" if value is None else _fmt_int(value)


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


__all__ = [
    "PDF_DIAGNOSTIC_SAMPLE_LIMIT",
    "PDF_FEATURE_EXCEPTION_LIMIT",
    "PDF_LISTING_SAMPLE_LIMIT",
    "PDF_MAXIMUM_BYTES",
    "PDF_MAXIMUM_PAGES",
    "PdfFeatureFamilyCoverage",
    "TECH_INDICATORS_PDF_FEATURE_FAMILIES",
    "render_tech_indicators_report_pdf",
    "roll_up_pdf_feature_coverage",
]
