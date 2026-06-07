# empire-stonks-securities

Reusable securities reference-data utilities for Empire stonks.

This package owns the package-level config model and object-store integration for
SEC-backed securities reference data. Airflow and other runtimes should call into
this package rather than embedding provider or object-store logic directly.

## Config

The seed config currently lives at:

```text
object-store/config/stonks-securities/config.yml
```

Publish it to the Empire object store with:

```bash
bin/stonks-securities-put-config
```

The canonical object-store registration is:

```text
config:stonks-securities/config.yml
```

with logical name:

```text
stonks-securities-config
```

## Status

This is the package skeleton. Config parsing and config publication are in place;
provider collection, normalization, and database loading should be added once the
securities ingestion contract is finalized.
