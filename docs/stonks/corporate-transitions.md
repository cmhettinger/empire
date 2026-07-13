# Securities corporate-transition runbook

Use this process when a securities scrape reports an unresolved duplicate
exchange/ticker combination that may be caused by a merger, redomiciliation,
successor registrant, share exchange, or similar corporate transition.

The SEC source files are preserved as evidence. Do not delete or rewrite source
observations to resolve a canonical-data conflict.

## Process

1. Run the scrape DAG normally.

   If validation reports an unresolved duplicate exchange/ticker combination,
   treat it as a review item. Do not automatically merge, close, or overwrite
   the affected records.

2. Verify the transition using primary evidence.

   Prefer SEC filings and exchange notices. Establish the predecessor and
   successor CIKs, the affected security and exchange listing, the effective
   date, the exchange ratio where applicable, and the source URLs.

3. Create a scoped data remediation.

   Add an idempotent SQL script under `db/data-remediations/stonks/`. The script
   must assert its expected records before changing them and run in one
   transaction.

4. Record the canonical lifecycle and successor relationship.

   The remediation should close the predecessor listing and security as
   appropriate, preserve both issuer records, insert a
   `stonks.security_successor_relationship` row, and write `security_event`
   audit records with the primary-source evidence.

5. Apply the remediation explicitly.

   First apply any required Flyway schema migration. Then run the remediation
   through `bin/run-data-remediation --file ... --apply`; it must never be part
   of Flyway's automatic migration locations.

6. Rerun and verify.

   Rerun the scrape DAG or its validation stage. The successor should be the
   only active listing for the exchange/ticker. Subsequent dated predecessor
   observations on or after the relationship effective date are retained as
   evidence on the historical listing, but must not reopen it. Unverified
   duplicate exchange/ticker combinations must continue to fail validation.

## Example

The July 2026 XOM redomiciliation is implemented by
`db/data-remediations/stonks/2026-07-11-exxon-xom-successor.sql`. Exxon Mobil
Corporation is the predecessor; ExxonMobil Holdings Corporation is the
successor NYSE/XOM listing effective July 2, 2026.
