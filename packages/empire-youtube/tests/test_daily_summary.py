from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from empire_youtube.daily_summary import build_youtube_daily_summary_report
from empire_youtube.reports.daily_summary.pdf.render import (
    render_youtube_daily_summary_pdf,
)


GENERATED_AT = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_daily_summary_includes_download_outcomes_and_threshold():
    report = _report()

    assert report["status"] == "WARN"
    assert report["summary"] == {
        "scraped_video_count": 7,
        "source_video_count": 7,
        "planned_download_count": 5,
        "sidecar_object_count": 12,
        "skipped_sidecar_count": 3,
        "download_total_count": 5,
        "successful_download_count": 3,
        "failed_download_count": 2,
        "downloaded_count": 2,
        "skipped_download_count": 1,
        "success_rate": 0.6,
        "minimum_success_rate": 0.6,
    }
    assert report["failed_downloads"] == [
        {"video_id": "four", "status": "failed", "error_message": "HTTP Error 403"},
        {"video_id": "five", "status": "failed", "error_message": "HTTP Error 403"},
    ]
    assert report["video_outcomes"] == [
        {
            "video_id": "one",
            "title": "Channel video",
            "length": "1:30",
            "status": "downloaded",
            "selection_reason": "Followed channel: Empire Channel",
            "deno": "available",
            "po_token": "used",
        },
        {
            "video_id": "two",
            "title": "Topic video",
            "length": "1:05:02",
            "status": "downloaded",
            "selection_reason": "Topic section: Markets",
            "deno": "not observed",
            "po_token": "not observed",
        },
        {
            "video_id": "three",
            "title": "Both sources video",
            "length": "Unknown",
            "status": "skipped",
            "selection_reason": "Followed channel: Empire Channel; Topic section: Markets",
            "deno": "not observed",
            "po_token": "not observed",
        },
        {
            "video_id": "four",
            "title": "four",
            "length": "Unknown",
            "status": "failed",
            "selection_reason": "Scraper discovery",
            "deno": "not observed",
            "po_token": "not observed",
        },
        {
            "video_id": "five",
            "title": "five",
            "length": "Unknown",
            "status": "failed",
            "selection_reason": "Scraper discovery",
            "deno": "not observed",
            "po_token": "not observed",
        },
    ]


def test_daily_summary_fails_below_threshold():
    report = build_youtube_daily_summary_report(
        scrape_result={"run_id": "scrape", "video_count": 2},
        plan_result={"run_id": "plan", "source_video_count": 2, "plan_entry_count": 2},
        download_results=[
            {"video_id": "one", "status": "downloaded"},
            {"video_id": "two", "status": "failed", "error_message": "403"},
        ],
        dag_id="youtube_daily_scrape",
        dag_run_id="manual__test",
        minimum_success_rate=0.6,
        generated_at=GENERATED_AT,
    )

    assert report["status"] == "FAIL"
    assert report["healthy"] is False


def test_daily_summary_pdf_smoke_render(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("EMPIRE_BRANDING_ROOT", str(repo_root / "resources" / "branding"))

    result = render_youtube_daily_summary_pdf(
        report=_report(),
        output_dir=tmp_path,
        generated_at=GENERATED_AT,
    )

    artifact = result.primary_artifact
    assert artifact.path.is_file()
    assert artifact.path.suffix == ".pdf"
    assert artifact.path.stat().st_size > 1_000


def _report():
    return build_youtube_daily_summary_report(
        scrape_result={"run_id": "scrape-run", "video_count": 7},
        plan_result={
            "run_id": "plan-run",
            "source_video_count": 7,
            "plan_entry_count": 5,
            "sidecar_object_count": 12,
            "skipped_sidecar_count": 3,
        },
        download_results=[
            {"video_id": "one", "status": "downloaded", "access_diagnostics": {"deno": "available", "po_token": "used"}},
            {"video_id": "two", "status": "downloaded"},
            {"video_id": "three", "status": "skipped"},
            {"video_id": "four", "status": "failed", "error_message": "HTTP Error 403"},
            {"video_id": "five", "status": "failed", "error_message": "HTTP Error 403"},
        ],
        dag_id="youtube_daily_scrape",
        dag_run_id="manual__test",
        minimum_success_rate=0.6,
        scrape_payload={
            "config": {"topic_section_names": {"markets": "Markets"}},
            "videos": [
                {
                    "video_id": "one",
                    "title": "Channel video",
                    "content": {"duration_seconds": 90},
                    "discovery_sources": ["channel_watch"],
                    "matched_channels": [{"channel_name": "Empire Channel"}],
                },
                {
                    "video_id": "two",
                    "title": "Topic video",
                    "content": {"duration_seconds": 3902},
                    "discovery_sources": ["topic_search"],
                    "matched_sections": ["markets"],
                },
                {
                    "video_id": "three",
                    "title": "Both sources video",
                    "discovery_sources": ["channel_watch", "topic_search"],
                    "matched_channels": [{"channel_name": "Empire Channel"}],
                    "matched_sections": ["markets"],
                },
            ],
        },
        generated_at=GENERATED_AT,
    )
