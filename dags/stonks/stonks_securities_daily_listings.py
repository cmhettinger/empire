from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task
from empire_core import EmpireDatabase
from empire_stonks_securities import upsert_sec_listings_from_provider_observations


@dag(
    dag_id="stonks_securities_daily_listings",
    start_date=datetime(2026, 6, 18),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["stonks", "securities", "sec", "listings", "manual"],
)
def stonks_securities_daily_listings():
    @task(task_id="upsert_sec_listings")
    def upsert_sec_listings() -> dict:
        with EmpireDatabase.connect_from_env() as conn:
            result = upsert_sec_listings_from_provider_observations(connection=conn)

        return result.to_dict()

    upsert_sec_listings()


stonks_securities_daily_listings_dag = stonks_securities_daily_listings()
