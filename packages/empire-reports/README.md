# empire-reports

Reusable report rendering primitives for Empire.

This package owns how reports are rendered and published. Domain packages own what a report says: data loading, section selection, domain language, and final report composition.

## Package Boundary

Belongs in `empire-reports`:

- Shared render contracts and artifact models
- Output path helpers
- Empire branding and ReportLab font registration
- Common PDF document, page template, header/footer, style, table, image, and chart helpers
- Small generic writers such as JSON output
- Placeholders for future renderer families

Belongs in domain packages:

- Report-specific queries and data models
- Report-specific sections and narrative
- Domain-specific PDF/audio/video/JSON/XLSX render functions
- Object store keys and publishing policy that are tied to a domain workflow

## Expected Domain Layout

```text
packages/<domain-package>/<domain_module>/reports/<report_name>/data.py
packages/<domain-package>/<domain_module>/reports/<report_name>/pdf/render.py
packages/<domain-package>/<domain_module>/reports/<report_name>/audio/render.py
packages/<domain-package>/<domain_module>/reports/<report_name>/video/render.py
packages/<domain-package>/<domain_module>/reports/<report_name>/json/render.py
packages/<domain-package>/<domain_module>/reports/<report_name>/xlsx/render.py
```

The report root should stay thin. Shared report-local data loading can live in `data.py`; target-specific layout and rendering should live under the target directory.

## PDF Example

```python
from datetime import date
from pathlib import Path

from reportlab.platypus import Paragraph, Spacer

from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf import (
    HeaderFooterSpec,
    PdfRenderer,
    section_heading,
)

metadata = ReportMetadata(
    report_id="example.report",
    title="Example Report",
    as_of=date(2026, 6, 28),
)
context = RenderContext(output_dir=Path("tmp/reports"))

renderer = PdfRenderer(metadata=metadata, context=context)
styles = renderer.styles
story = [
    section_heading("Overview", styles=styles),
    Paragraph("Domain packages provide the content.", styles.body),
    Spacer(1, 12),
]

result = renderer.render(
    story,
    header_footer=HeaderFooterSpec(header_center_text="INTERNAL USE ONLY"),
)
```

## Branding

By default, `BrandingConfig.discover()` looks for the repository root and uses `resources/branding`. Runtimes can set `EMPIRE_BRANDING_ROOT` to point at a different branding bundle. The package registers the Source Sans 3, Cinzel, and Source Code Pro fonts when the files are available, while falling back to ReportLab built-in fonts when they are not.

## Future Render Targets

The package exposes a stable `OutputFormat` enum and renderer contract for PDF, audio, video, JSON, XLSX, HTML, and email. Only PDF and a minimal JSON writer are implemented in this first version. Audio, video, and XLSX directories exist so future domain reports can adopt the same target-specific layout without changing the common contracts.

## Architecture Primer For Future Report Work

Use this section as context when asking Codex or ChatGPT to build a new Empire report.

`empire-reports` is a reusable rendering toolkit. It should remain domain-agnostic. Its job is to provide contracts, output artifacts, path helpers, branding, PDF layout primitives, reusable PDF components, and small generic writers. It should not know about securities, weather, YouTube, finance, mail, Airflow DAGs, SQL tables, object-store keys, or report-specific business meaning.

The main package concepts are:

- `ReportMetadata`: stable identity and descriptive metadata for a report.
- `RenderContext`: runtime context for rendering, including the local output directory and optional run/object metadata.
- `ReportArtifact`: a rendered file plus structured metadata such as format, media type, logical name, and optional object key.
- `RenderResult`: the report metadata, generated artifacts, and generation timestamp.
- `OutputFormat`: shared format vocabulary for `pdf`, `audio`, `video`, `json`, `xlsx`, `html`, and `email`.
- `BrandingConfig`: discovers Empire branding assets from `resources/branding` or `EMPIRE_BRANDING_ROOT`.
- `ReportTheme`: centralizes brand colors and ReportLab font names.
- `PdfRenderer`: builds PDF artifacts from ReportLab flowables.

PDF support is intentionally practical and explicit. Domain PDF renderers should compose ReportLab stories from `empire_reports.renderers.pdf` helpers rather than reimplementing document setup, font registration, page templates, headers/footers, or common title-page behavior. The reusable professional title page is available as `professional_letter_title_page(...)`; domain reports can use it as-is or build their own title page under the domain package when they need special layout.

Publishing is intentionally outside this package. `empire-reports` renders local artifacts and returns metadata. A domain package or orchestration wrapper decides whether an artifact is run-scoped, durable, promoted to a "latest" location, emailed, attached to an object-store run, or retained under a domain-specific key layout.

When changing `empire-reports`, prefer boring, explicit primitives over discovery-heavy frameworks. Add common helpers only when at least one real report needs them and they are clearly domain-neutral. Keep target-specific code under the relevant renderer family: PDF layout under `renderers/pdf`, audio scripts or helpers under `renderers/audio`, video helpers under `renderers/video`, JSON writers under `renderers/json`, and workbook helpers under `renderers/xlsx`.

## Domain Report Implementation Guide

Domain packages own the content and workflow of reports. A good domain report is thin at the root, target-specific under each render directory, and explicit about where data comes from.

Recommended structure:

```text
packages/<domain-package>/src/<domain_module>/reports/<report_name>/
  __init__.py
  data.py
  models.py                 # optional report-local typed view models
  pdf/
    __init__.py
    render.py
    sections.py             # optional PDF-only section builders
    components.py           # optional domain-specific PDF components
  json/
    __init__.py
    render.py
  audio/
    __init__.py
    render.py               # future, when needed
  video/
    __init__.py
    render.py               # future, when needed
  xlsx/
    __init__.py
    render.py               # future, when needed
```

Suggested responsibilities:

- `data.py`: load and shape report data from domain services, repositories, files, or object-store inputs.
- `models.py`: define report-local dataclasses when the rendered view needs a stable typed shape.
- `pdf/render.py`: create `ReportMetadata`, `RenderContext`, `PdfRenderer`, and the final story; return `RenderResult`.
- `pdf/sections.py`: build PDF sections as small functions returning ReportLab flowables.
- `pdf/components.py`: hold reusable domain-specific components, such as securities summary panels or exchange coverage tables.
- `json/render.py`: write structured report payloads through `write_json_report(...)` when useful.

Use `empire-reports` like this:

```python
from empire_reports.contracts import RenderContext, ReportMetadata
from empire_reports.renderers.pdf import PdfRenderer, professional_letter_title_page


def render_pdf(*, output_dir, as_of, data) -> object:
    metadata = ReportMetadata(
        report_id="domain.report-name",
        title="Domain Report Name",
        subtitle="Operational Summary",
        as_of=as_of,
    )
    renderer = PdfRenderer(
        metadata=metadata,
        context=RenderContext(output_dir=output_dir),
    )
    story = [
        *professional_letter_title_page(
            title=metadata.title,
            subtitle=metadata.subtitle or "",
            report_date=metadata.as_of,
            classification_text="INTERNAL USE ONLY",
            branding=renderer.branding,
            theme=renderer.theme,
        ),
        # report-specific sections go here
    ]
    return renderer.render(story)
```

Keep these boundaries:

- Do not put domain SQL, business rules, or report narrative in `empire-reports`.
- Do not put Airflow task logic in domain report renderers; DAGs should call reusable package functions.
- Do not make `empire-reports` decide object-store key conventions. Convert `ReportArtifact` to stored objects in the domain package or orchestration layer.
- Do not bury report data loading inside PDF section builders when the same data may later feed JSON, audio, video, or XLSX.
- Do not build a registry or plugin mechanism until real repeated usage proves it is needed.

Before wiring a report into a pipeline, make the report-specific publishing decision outside `empire-reports`:

- Decide whether each artifact is run-scoped, durable/published, promoted to a stable "latest" location, or some combination.
- Decide the object-store key layout, `object_kind`, `logical_name`, and metadata fields.
- Decide whether the artifact should attach to a run context with `run_id`.
- Decide retention/promotion behavior in the domain package or orchestration layer.
- Keep the renderer focused on local file rendering; let the domain workflow consume `ReportArtifact` and publish it.

For Empire compatibility:

- Keep configuration environment-driven; reusable packages should not load `.env` files.
- Prefer dataclasses and explicit function arguments for report inputs.
- Return `RenderResult` from render functions so orchestration can inspect artifacts without parsing paths.
- Use `ReportArtifact.metadata` for portable facts such as `report_id`, `as_of`, source run IDs, row counts, or data freshness when those facts help downstream publishing.
- Keep local output paths deterministic and boring. Publishing paths can be decided later by the domain workflow.
- Add package-local tests for data shaping, path behavior, JSON output, and at least one PDF smoke render.

The first version of a domain report should normally implement only the targets it needs immediately. For most reports, start with PDF and optional JSON. Add audio, video, XLSX, HTML, or email only when the report has a concrete consumer for that format.

## Starter Prompt For New Domain Reports

Copy this into a new Codex or ChatGPT conversation when creating a report that should use `empire-reports`.

```text
We are building a new domain-specific Empire report.

Please inspect and use:
- packages/empire-reports/README.md
- packages/empire-reports/src/empire_reports/
- the target domain package README, pyproject, tests, and existing package conventions

Use empire-reports as the reusable rendering layer. Do not add domain-specific logic to empire-reports.

Report target:
- Domain package: packages/<domain-package>
- Domain module: <domain_module>
- Report name: <report_name>
- Initial render target: PDF
- Optional later targets: JSON/audio/video/xlsx/html/email

Expected domain layout:
packages/<domain-package>/src/<domain_module>/reports/<report_name>/
  __init__.py
  data.py
  models.py                 # optional, if useful
  pdf/
    __init__.py
    render.py
    sections.py             # optional, if useful
    components.py           # optional domain-specific PDF components
  json/
    __init__.py
    render.py               # optional, if useful now

Implementation rules:
- data.py owns report data loading and shaping.
- pdf/ owns PDF-specific layout, sections, and components.
- Use ReportMetadata, RenderContext, RenderResult, ReportArtifact, and PdfRenderer from empire-reports.
- Use professional_letter_title_page unless there is a report-specific reason not to.
- Keep object-store publishing decisions in the domain package or orchestration layer, not in empire-reports.
- Before wiring into a pipeline, explicitly decide run-scoped vs durable/published object-store behavior.
- Return RenderResult from render functions.
- Add focused tests for data shaping, path behavior, and at least one PDF smoke render.
- Do not build unrelated render targets yet.

Empire architecture constraints:
- Reusable logic belongs in packages/, not Airflow DAG files.
- DAGs should orchestrate only and call reusable package functions.
- Reusable packages should read configuration from os.environ and should not load .env files.
- Keep the report root thin; put target-specific implementation under pdf/, json/, audio/, video/, or xlsx/.
- Keep the first version simple, explicit, and easy to extend.

Task:
Build the first clean version of <report_name> as a reusable domain report. Inspect the existing code first, follow current package conventions, implement the report, run package-local tests, and summarize the design decisions.
```
