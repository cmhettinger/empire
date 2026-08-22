# Tech-Indicators PDF Visual Evidence R8.7

Status: accepted visual verification evidence as of 2026-08-22.

R8.7 rendered the frozen R8.6 PDF implementation from six immutable report
fixtures and inspected every page after Poppler rasterization at 144 DPI. The
artifacts were disposable local verification output under `tmp/pdfs/` and were
removed after acceptance; they are not durable reports or canonical source.

## Render Matrix

| Variant | Outcome label | Pages | Bytes | Bounded diagnostics |
|---|---|---:|---:|---:|
| Daily success | `PASS` | 11 | 174,224 | 0 |
| Daily warning | `WARN` | 11 | 174,285 | 0 |
| Daily no-op | `NO OP` | 11 | 174,207 | 0 |
| Daily failure | `FAIL - UNPUBLISHED` | 11 | 174,257 | 0 |
| Resumed partial backfill | `PARTIAL - UNPUBLISHED` | 12 | 175,387 | 0 |
| Largest bounded samples | `FAIL - UNPUBLISHED` | 12 | 177,374 | 100 |

All six PDFs were US Letter (`612 x 792` points), below the frozen 25-page and
5-MiB bounds. Across 68 inspected pages, all 56 body pages carried the Empire
header, classification footer, effective-date or backfill-range scope, and
continuous body-page numbering.

The largest bounded fixture retained 100 failure diagnostics and 100 referenced
sample IDs. The PDF displayed the first 10 diagnostic rows, reported 90 omitted
rows, wrapped full UUIDs and messages, and repeated the table header when the
diagnostic table continued onto the next page.

## Inspection Result

Every page was checked for clipping, overflow, table wrapping, repeated headers,
orphan headings, excessive sparse layout, legibility, chart/table agreement,
status language, and Empire branding. No acceptance defect was found.

- Covers, disclaimer pages, status banners, titles, range/effective-date labels,
  logos, and internal-use classification were complete and unobstructed.
- The ten family chart labels and values agreed with the adjacent feature-
  observation table, and hue was not required to interpret any result.
- Success, warning, no-op, failure, and partial states were textually distinct.
  Partial backfill showed both resume cursors and repeated `UNPUBLISHED`.
- Long hashes, UUIDs, issue codes, fixed messages, disclosure codes, and the
  maximum sample-ID aggregate wrapped within their cells without overlap.
- Flowing tables repeated headers after page breaks; no section heading or
  table row was stranded or clipped. Deliberately short empty-state and
  warnings pages remained clear rather than appearing incomplete.

Programmatic checks with `pypdf` also verified fixed section order, outcome
labels, page dimensions, artifact bounds, backfill range/resume text, and the
header/footer/page-number contract on every body page. `pdfinfo` independently
reported the same page counts, dimensions, and byte sizes.
