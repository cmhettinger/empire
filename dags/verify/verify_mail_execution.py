from __future__ import annotations

from datetime import datetime
import logging

from airflow.sdk import dag, task
from empire_mail import send_html_email

log = logging.getLogger(__name__)


@dag(
    dag_id="verify_mail_execution",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["verify", "smoke", "mail"],
)
def verify_mail_execution():
    @task(task_id="send_html_hello_world")
    def send_html_hello_world() -> str:
        send_html_email(
            subject="Empire Airflow mail smoke test",
            text="Hello from Empire Airflow. This is the plain-text fallback.",
            html="""
            <html>
              <body>
                <h1>Hello from Empire Airflow</h1>
                <p>This HTML email was sent by the verify_mail_execution DAG.</p>
                <p><strong>Status:</strong> empire-mail is available inside Airflow.</p>
              </body>
            </html>
            """,
        )
        log.info("Sent Empire Airflow HTML mail smoke test")
        return "ok"

    send_html_hello_world()


verify_mail_execution_dag = verify_mail_execution()
