# empire

<p align="center">

![Type](https://img.shields.io/badge/Type-Internal%20Research-informational.svg)
![License](https://img.shields.io/badge/License-Proprietary-red.svg)
![Status](https://img.shields.io/badge/Status-Private-important.svg)

</p>

A **local-first research system** focused on correctness, reproducibility,
and explicit system design.

---

## Purpose

`empire` is designed to be:

- **explicit** rather than magical
- **safe by default**
- **extensible** to additional data sources over time

The project favors:

- deterministic behavior
- reproducible workflows
- modular architecture
- intentional operational boundaries

---

## Repository Structure

### `apps/`

Runnable application code:

- APIs
- data ingestion
- processing services
- tooling

### `packages/`

Reusable shared libraries used across applications and services.

### `db/`

Database assets:

- Flyway migrations
- schema definitions
- curated seed reference data

### `deploy/`

Deployment assets:

- Docker Compose
- environment configuration
- infrastructure topology

### `docs/`

Canonical repository documentation.

---

## Getting Started

All documentation lives in the `docs/` directory.

If you are new to the project, start here:

➡️ [`docs/README.md`](docs/README.md)

This will walk you through:

- local prerequisites
- environment setup
- database startup
- Flyway migrations
- first-time local initialization

---

## Principles

Empire prioritizes:

- **clarity over convenience**
- **composition over hidden behavior**
- **explicit configuration over convention**
- **local-first development**
- **repeatable infrastructure**

---

## License

This repository is **private and proprietary**.

All rights reserved.

No part of this repository may be used, copied,
modified, distributed, or disclosed without
explicit written permission.