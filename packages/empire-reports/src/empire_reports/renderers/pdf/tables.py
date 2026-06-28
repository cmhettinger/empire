from __future__ import annotations

from collections.abc import Sequence

from reportlab.platypus import Table, TableStyle

from empire_reports.branding import ReportTheme


def simple_table(
    rows: Sequence[Sequence[object]],
    *,
    theme: ReportTheme,
    repeat_header: bool = True,
) -> Table:
    table = Table([[str(cell) for cell in row] for row in rows], repeatRows=1 if repeat_header else 0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), theme.primary),
                ("TEXTCOLOR", (0, 0), (-1, 0), theme.white),
                ("FONTNAME", (0, 0), (-1, 0), theme.body_semibold_font),
                ("FONTNAME", (0, 1), (-1, -1), theme.body_font),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.25, theme.light_grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [theme.white, "#F7F7F7"]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table
