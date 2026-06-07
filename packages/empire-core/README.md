# empire-core

`empire-core` provides lightweight platform services for Empire:

- run context / run tracking
- filesystem-backed object storage with metadata in Postgres

The package is runtime agnostic. It reads configuration from environment
variables when requested, but does not load `.env` files and does not configure
global logging.

## What this package owns

`empire-core` owns reusable platform capabilities. It does not own orchestration,
runtime startup, mount provisioning, or global logging configuration.

Airflow, CLIs, APIs, and scripts should call this package. They remain
responsible for loading environment variables and configuring logging.

## Package layout

The package is organized by platform capability:

```text
empire_core/
  db/             database connection and small Postgres helpers
  run_context/    run tracking models, repository, and service
  object_store/   object metadata, service, repository, and storage backends
```

Consumers should usually use the stable top-level imports:

```python
from empire_core import EmpireDatabase, ObjectStore, RunContext, RunService, StoredObject
```

## Database

The schema is owned by the monorepo-level Flyway migration:

```text
db/flyway/sql/V2026.05.22.0001__core_create_run_context_and_object_store.sql
```

The database generates `run_id` and `object_id` with `gen_random_uuid()`.
The Python repositories use `INSERT ... RETURNING` to retrieve those IDs.

Storage roots are initialized outside Flyway schema migrations so each runtime
can map stable root names to local filesystem paths.

Example root names:

```text
global
jellyfin
```

Example local/dev mapping:

```text
config   -> /Users/chris/Documents/project/empire/object-store/config
global   -> /Users/chris/Documents/project/empire/object-store/global
jellyfin -> /Users/chris/Documents/project/empire/object-store/jellyfin
```

Example server mapping:

```text
global   -> /mnt/empire-object-store/global
jellyfin -> /mnt/empire-object-store/jellyfin
```

## Configuration

For local development, add these values to the monorepo-level environment file:

```text
deploy/env/local.env
```

`EmpireDatabase.connect_from_env()` reads:

```text
EMPIRE_DB_HOST
EMPIRE_DB_PORT              optional; defaults to 5432
EMPIRE_DB_NAME
EMPIRE_DB_USER
EMPIRE_DB_PASSWORD
```

`ObjectStore.from_connection()` reads:

```text
EMPIRE_OBJECT_STORE_TOMBSTONE_DAYS    optional; defaults to 30
```

The storage-root initialization script reads:

```text
EMPIRE_STORAGE_ROOT_GLOBAL
EMPIRE_STORAGE_ROOT_JELLYFIN
```

More roots can be added later by defining additional `EMPIRE_STORAGE_ROOT_*`
variables.

Storage roots are not loaded directly from environment variables. They are rows
in `core.storage_root`, so each environment can map a stable root name such as
`global` or `jellyfin` to its own local or server filesystem path.

Initialize or update storage-root rows after Flyway migrations:

```bash
bin/init-storage-roots
```

For first local setup, create the directories too:

```bash
bin/init-storage-roots --create-dirs
```

## Run context

Run tracking is for Empire business/domain lineage. Airflow still owns
orchestration.

```python
from datetime import date

from empire_core import EmpireDatabase, RunService

report_date = date(2026, 5, 23)

with EmpireDatabase.connect_from_env() as conn:
    run_service = RunService.from_connection(conn)

    ctx = run_service.start_run(
        domain="weather",
        job_name="weather_refresh",
        subject_key="ashburn-va",
        effective_date=report_date,
        run_type="airflow",
        runner="airflow",
        runner_ref={"dag_id": "weather_refresh"},
        heartbeat_timeout_seconds=1800,
    )

    run_service.heartbeat(ctx.run_id)

    run_service.complete_run(ctx.run_id, summary={"stored_object_count": 1})
```

### Failure handling

```python
try:
    refresh_weather()
except Exception as exc:
    run_service.fail_run(
        ctx.run_id,
        error_message=str(exc),
        summary={"failed_step": "refresh_weather"},
    )
    raise
```

### Selecting report sources

```python
weather_run = run_service.find_latest_successful_run(
    domain="weather",
    job_name="weather_refresh",
    subject_key="ashburn-va",
    effective_date=report_date,
    before=cutoff_time,
)

if weather_run is None:
    raise RuntimeError("No successful weather run is available")
```

For candidate discovery:

```python
runs = run_service.find_successful_runs(
    domain="weather",
    job_name="weather_refresh",
    subject_key="ashburn-va",
    after=window_start,
    before=cutoff_time,
    limit=20,
)
```

## Object store

The object store writes bytes to:

```text
storage_root.base_uri / object_key / filename
```

It records metadata in `core.stored_object`.

```python
from empire_core import EmpireDatabase, ObjectStore

with EmpireDatabase.connect_from_env() as conn:
    object_store = ObjectStore.from_connection(conn)
    stored = object_store.put_bytes(
        run_context=ctx,
        storage_root="nas_weather",
        object_key=f"weather/ashburn-va/{report_date:%Y/%m/%d}/{ctx.run_id}/raw",
        filename="forecast.json",
        data=forecast_bytes,
        content_type="application/json",
        object_kind="raw_payload",
        metadata={"provider": "openweather"},
    )
```

### Storing local files

For larger files, use `put_file()` so the object store streams from an existing
local file instead of loading all bytes into memory. By default, the source file
is removed after it is safely written into the storage root. Pass `move=False`
to copy instead.

```python
stored = object_store.put_file(
    run_context=ctx,
    storage_root="jellyfin",
    object_key="media/youtube/channel/video-id",
    filename="movie.mp4",
    source_path="/tmp/empire-download/movie.mp4",
    content_type="video/mp4",
    object_kind="media_asset",
)
```

### Reading bytes

```python
data = object_store.get_bytes(stored.object_id)
```

### Listing run objects

```python
objects = object_store.find_objects_by_run_id(weather_run.run_id)
```

### Reference objects

Reference, audit, and manual objects do not require fake runs. Run-scoped
objects require a real `run_context`.

```python
stored = object_store.put_bytes(
    run_context=None,
    object_scope="reference",
    domain="weather",
    logical_name="openweather-icon-10d",
    storage_root="nas_weather",
    object_key="reference/weather/icons/openweather",
    filename="10d.png",
    data=icon_bytes,
    content_type="image/png",
    object_kind="weather_icon",
    expires_at=None,
)
```

### Well-known object updates

Stored object paths are unique by `(storage_root, object_key, filename)`.
Normal writes should leave `overwrite` unset so accidental path reuse fails
fast.

For well-known reference objects such as package configuration, pass
`overwrite=True` to replace the bytes and metadata at the same object path.
This keeps the path stable while preserving the same metadata row/object ID.

```python
stored = object_store.put_bytes(
    run_context=None,
    object_scope="reference",
    domain="weather",
    logical_name="weather-config",
    storage_root="config",
    object_key="weather",
    filename="config.yml",
    data=config_bytes,
    content_type="text/yaml",
    object_kind="weather_config",
    overwrite=True,
)
```

Use this only for intentional well-known objects. Run-scoped artifacts should
normally use run-specific object keys instead of overwriting.

### Logical-name lookup

```python
icons = object_store.find_by_logical_name(
    domain="weather",
    logical_name="openweather-icon-10d",
    object_scope="reference",
)
```

### Expiration cleanup

Expiration is controlled by `expires_at` on each stored object.

```python
deleted_count = object_store.delete_expired_objects(limit=100)
```

For scheduled maintenance that should keep cleaning until no eligible expired
objects remain, use the batch-oriented cleanup helper:

```python
result = object_store.cleanup_expired_objects(batch_size=100)
```

Expired files are deleted from the filesystem. Missing files are still marked
deleted. Failed deletes increment `delete_attempts` and record
`last_delete_error`.

Metadata tombstones can be purged later:

```python
purged_count = object_store.purge_deleted_objects(limit=100)
```

For scheduled maintenance that should keep purging until no eligible tombstones
remain, use the batch-oriented purge helper:

```python
result = object_store.purge_deleted_objects_all(batch_size=100)
```

Deleted metadata for one run can be purged through the run-scoped helper:

```python
purged_count = object_store.purge_deleted_objects_by_run_id(run_id)
purged_count = object_store.purge_deleted_objects_by_run_id(
    run_id,
    ignore_purge_after=True,
)
```

Objects can also be deleted directly by object ID or by run ID:

```python
object_store.delete_object(object_id)
object_store.delete_objects_by_run_id(run_id)
```

These methods delete physical files and mark metadata rows deleted. They do not
delete run rows; run rows remain as lineage/history.

Filesystem deletes also prune empty parent directories up to the storage root.

For local/dev cleanup, the repository includes operational scripts:

```bash
bin/run-objects-cleanup <run_id>
bin/run-objects-purge <run_id>
bin/run-objects-purge <run_id> --ignore-purge-after
bin/run-nuke <run_id> --yes
```

`run-nuke` deletes active files, purges deleted object metadata immediately, and
deletes the run row. Use it only when the run should be completely removed from
lineage/history.

## Path safety

`object_key` must be a relative folder-like path.
`filename` must be a single leaf filename.

Rejected examples:

```text
../escape
/absolute/path
safe/../escape
../file.txt as filename
```

## Logging

The package defines module loggers with `logging.getLogger(__name__)`.
It does not call `basicConfig` and does not change global logging behavior.

## Development

Install dependencies:

```bash
poetry install
```

Run tests:

```bash
poetry run pytest
```

Run import/bytecode verification:

```bash
poetry run python -m compileall src tests
```
