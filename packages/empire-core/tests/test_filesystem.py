import pytest

from empire_core.exceptions import ValidationError
from empire_core.filesystem import remove_file_and_prune_empty_parents


def test_remove_file_prunes_empty_parents_but_preserves_boundary(tmp_path):
    temp_root = tmp_path / "tmp"
    report = (
        temp_root
        / "utils"
        / "objectstore-clean"
        / "runs"
        / "2026"
        / "07"
        / "28"
        / "run-reports"
        / "summary"
        / "report.pdf"
    )
    report.parent.mkdir(parents=True)
    report.write_bytes(b"pdf")

    remove_file_and_prune_empty_parents(report, stop_at=temp_root)

    assert temp_root.is_dir()
    assert not (temp_root / "utils").exists()


def test_remove_file_stops_pruning_at_first_nonempty_parent(tmp_path):
    temp_root = tmp_path / "tmp"
    report_dir = temp_root / "utils" / "objectstore-clean" / "reports"
    report_dir.mkdir(parents=True)
    report = report_dir / "report.pdf"
    report.write_bytes(b"pdf")
    sibling = report_dir / "keep.txt"
    sibling.write_text("keep")

    remove_file_and_prune_empty_parents(report, stop_at=temp_root)

    assert not report.exists()
    assert sibling.read_text() == "keep"
    assert report_dir.is_dir()


def test_remove_file_rejects_path_outside_boundary(tmp_path):
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    report = tmp_path / "report.pdf"
    report.write_bytes(b"pdf")

    with pytest.raises(ValidationError, match="file_path must be beneath stop_at"):
        remove_file_and_prune_empty_parents(report, stop_at=temp_root)

    assert report.exists()
