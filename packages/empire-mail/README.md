# empire-mail

Reusable SMTP email utilities for Empire.

This package is intentionally small in `0.1.0`: it uses only the Python
standard library for runtime mail delivery and does not include provider SDKs,
OAuth flows, templates, queues, retry orchestration, database logging, async
delivery, or Airflow-specific code.

## Configuration

Empire uses shared environment files under `deploy/env/`. For local Mac
development, the active file is `deploy/env/local.env`.
Reusable packages do not load that file themselves, and `empire-mail` does not
look for package-local `.env` files. The runtime layer that starts the process,
such as Docker Compose, shell scripts, Airflow, or a CLI, is responsible for
loading environment variables before this package is imported or called.

`MailConfig.from_env()` reads only from the process environment:

- `EMPIRE_MAIL_SMTP_HOST`
- `EMPIRE_MAIL_SMTP_PORT` (defaults to `587`)
- `EMPIRE_MAIL_SMTP_STARTTLS` (defaults to `true`)
- `EMPIRE_MAIL_SMTP_SSL` (defaults to `false`)
- `EMPIRE_MAIL_USERNAME`
- `EMPIRE_MAIL_PASSWORD`
- `EMPIRE_MAIL_FROM`
- `EMPIRE_MAIL_TO_DEFAULT`

If `to` is omitted when sending, `EMPIRE_MAIL_TO_DEFAULT` is used.

## Gmail SMTP with an app password

Gmail SMTP works with an app password on accounts where app passwords are
enabled. In Empire local development, place these values in the shared
`deploy/env/local.env` file or export them in your shell before running the
process.

```dotenv
EMPIRE_MAIL_SMTP_HOST=smtp.gmail.com
EMPIRE_MAIL_SMTP_PORT=587
EMPIRE_MAIL_SMTP_STARTTLS=true
EMPIRE_MAIL_SMTP_SSL=false
EMPIRE_MAIL_USERNAME=sender@example.com
EMPIRE_MAIL_PASSWORD=your-gmail-app-password
EMPIRE_MAIL_FROM=sender@example.com
EMPIRE_MAIL_TO_DEFAULT=recipient@example.com
```

```python
from empire_mail import send_text_email

send_text_email(
    subject="Empire check-in",
    text="The report finished successfully.",
)
```

## HTML email

```python
from empire_mail import send_html_email

send_html_email(
    to="recipient@example.com",
    subject="Daily report",
    text="Your mail client does not support HTML.",
    html="<h1>Daily report</h1><p>Everything completed.</p>",
)
```

## Report attachments

```python
from empire_mail import send_report_email

send_report_email(
    subject="Revenue report",
    text="Attached is the latest report.",
    report_path="reports/revenue.csv",
)
```

## Manual smoke tests

These commands send real email. Run them from the repository root after
populating `deploy/env/local.env`.

Load the shared Empire environment into the current shell:

```bash
source bin/env-load
```

Then run commands from the package directory:

```bash
cd packages/empire-mail
```

Test a plain text email to `EMPIRE_MAIL_TO_DEFAULT`:

```bash
poetry run python -c 'from empire_mail import send_text_email; send_text_email(subject="Empire mail test", text="Hello from empire-mail. SMTP config works.")'
```

Test an HTML email to `EMPIRE_MAIL_TO_DEFAULT`:

```bash
poetry run python -c 'from empire_mail import send_html_email; send_html_email(subject="Empire HTML mail test", text="Your mail client does not support HTML.", html="<h1>Empire HTML test</h1><p>If this text is styled as HTML, the SMTP path works.</p><p><strong>Status:</strong> good.</p>")'
```

Test a report attachment email to `EMPIRE_MAIL_TO_DEFAULT`:

```bash
echo "hello,report" > /tmp/empire-mail-report.csv
poetry run python -c 'from empire_mail import send_report_email; send_report_email(subject="Empire report email test", text="Attached is a test report.", report_path="/tmp/empire-mail-report.csv")'
```

Test an email to two recipients with two attachments:

```bash
echo "first,report" > /tmp/empire-mail-report-1.csv
echo "second,report" > /tmp/empire-mail-report-2.csv
poetry run python -c 'from empire_mail import send_email; send_email(to=["person-one@example.com", "person-two@example.com"], subject="Empire multi-recipient attachment test", text="Attached are two test reports.", attachments=["/tmp/empire-mail-report-1.csv", "/tmp/empire-mail-report-2.csv"])'
```

Pass `to="recipient@example.com"` to any helper to override
`EMPIRE_MAIL_TO_DEFAULT`.

To load a different environment file, pass its path to the helper:

```bash
source bin/env-load path/to/other.env
```

## Logging

`empire-mail` uses standard Python library logging and does not configure
handlers, formats, or levels. Applications that use the package own logging
configuration.

The package logs safe operational metadata such as SMTP host, port, TLS mode,
recipient count, attachment count, and whether a message includes HTML. It does
not log passwords, message bodies, HTML bodies, attachment contents, sender
addresses, or recipient addresses.

For a standalone Python app, configure logging in the app entrypoint:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("empire_mail").setLevel(logging.INFO)
```

Use `DEBUG` when you want more detail while troubleshooting SMTP setup:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("empire_mail").setLevel(logging.DEBUG)
```

Airflow already configures Python logging for task execution. To adjust
`empire-mail` verbosity inside a DAG or task module, set the package logger
level without adding handlers:

```python
import logging

logging.getLogger("empire_mail").setLevel(logging.INFO)
```

## Future Airflow usage

Keep Airflow integration outside this package. An Airflow DAG or task can import
these helpers and call them after loading environment variables through the
runtime deployment configuration.

```python
from empire_mail import send_report_email


def notify_report_ready(report_path: str) -> None:
    send_report_email(
        subject="Empire report ready",
        text="The scheduled report is attached.",
        report_path=report_path,
    )
```
