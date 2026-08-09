# Tech-Indicators Keys And Constraints V1

Status: frozen S2.3 implementation contract as of 2026-08-09.

This document freezes V1 keys, foreign keys, delete actions, checks, integrity
triggers, and the Python/PostgreSQL validation boundary for the payload schema
in [`tech-indicators-payload-schema-v1.md`](tech-indicators-payload-schema-v1.md)
and auxiliary schema in
[`tech-indicators-publication-schema-v1.md`](tech-indicators-publication-schema-v1.md).
S2.4 freezes non-integrity access indexes in
[`tech-indicators-indexes-v1.md`](tech-indicators-indexes-v1.md); S2.5
implements both contracts.

## Payload Keys And Foreign Keys

Each physical payload slot uses these constraints, with `{slot}` replaced by
`a` or `b` in names and relation references:

```sql
CONSTRAINT pk_ohlcv_daily_tech_indicators_{slot}
    PRIMARY KEY (provider_listing_id, trading_date),

CONSTRAINT fk_tech_indicators_{slot}_source_bar
    FOREIGN KEY (provider_listing_id, trading_date)
    REFERENCES stonks.ohlcv_daily(provider_listing_id, trading_date)
    ON DELETE CASCADE,

CONSTRAINT fk_tech_indicators_{slot}_benchmark_listing
    FOREIGN KEY (relative_strength_benchmark_provider_listing_id)
    REFERENCES stonks.provider_listing(provider_listing_id)
    ON DELETE RESTRICT,

CONSTRAINT fk_tech_indicators_{slot}_run
    FOREIGN KEY (run_id)
    REFERENCES core.core_run(run_id)
    ON DELETE SET NULL
```

The composite source FK is row ownership: deleting one source bar deletes the
same-date row from both slots; deleting its provider listing cascades through
source bars. Benchmark lineage is non-owning and restrictive: deleting SPX
cannot silently null supported-subject semantics or delete subject rows. Core
run lineage is optional evidence and becomes null on cleanup.

No payload row has a publication FK. Publication visibility is normalized in
membership. There is no FK to canonical `stonks.listing`, a source snapshot,
or a report object.

## Payload Checks

Each slot receives the following checks with the same expression and a
slot-specific constraint name:

```sql
CONSTRAINT ck_tech_indicators_{slot}_calculation_version
    CHECK (
        calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
        AND calculation_version = btrim(calculation_version)
    ),

CONSTRAINT ck_tech_indicators_{slot}_history_count
    CHECK (history_observation_count > 0),

CONSTRAINT ck_tech_indicators_{slot}_source_numeric
    CHECK (
        open <> 'NaN'::numeric
        AND high <> 'NaN'::numeric
        AND low <> 'NaN'::numeric
        AND close <> 'NaN'::numeric
        AND (volume IS NULL OR volume <> 'NaN'::numeric)
    ),

CONSTRAINT ck_tech_indicators_{slot}_source_bar_shape
    CHECK (
        high >= low
        AND high >= open
        AND high >= close
        AND low <= open
        AND low <= close
        AND (volume IS NULL OR volume >= 0)
    ),

CONSTRAINT ck_tech_indicators_{slot}_streaks
    CHECK (
        consecutive_up_days >= 0
        AND consecutive_down_days >= 0
        AND NOT (
            consecutive_up_days > 0
            AND consecutive_down_days > 0
        )
    ),

CONSTRAINT ck_tech_indicators_{slot}_bounded_points
    CHECK (
        (rsi_14 IS NULL OR rsi_14 BETWEEN 0.0 AND 100.0)
        AND (plus_di_14 IS NULL OR plus_di_14 BETWEEN 0.0 AND 100.0)
        AND (minus_di_14 IS NULL OR minus_di_14 BETWEEN 0.0 AND 100.0)
        AND (adx_14 IS NULL OR adx_14 BETWEEN 0.0 AND 100.0)
        AND (
            close_location_1d IS NULL
            OR close_location_1d BETWEEN 0.0 AND 1.0
        )
        AND (
            spx_correlation_60d IS NULL
            OR spx_correlation_60d BETWEEN -1.0 AND 1.0
        )
        AND (
            spx_correlation_252d IS NULL
            OR spx_correlation_252d BETWEEN -1.0 AND 1.0
        )
    ),

CONSTRAINT ck_tech_indicators_{slot}_nonnegative_measures
    CHECK (
        (atr_14 IS NULL OR atr_14 >= 0.0)
        AND (return_volatility_20d_pct IS NULL OR return_volatility_20d_pct >= 0.0)
        AND (return_volatility_60d_pct IS NULL OR return_volatility_60d_pct >= 0.0)
        AND (price_stddev_20 IS NULL OR price_stddev_20 >= 0.0)
        AND (volume_avg_20 IS NULL OR volume_avg_20 >= 0.0)
        AND (volume_avg_60 IS NULL OR volume_avg_60 >= 0.0)
        AND (dollar_volume_avg_20 IS NULL OR dollar_volume_avg_20 >= 0.0)
        AND (dollar_volume IS NULL OR dollar_volume >= 0.0)
        AND (
            bollinger_bandwidth_20_2 IS NULL
            OR bollinger_bandwidth_20_2 >= 0.0
        )
    ),

CONSTRAINT ck_tech_indicators_{slot}_benchmark_shape
    CHECK (
        (
            relative_strength_benchmark_provider_listing_id IS NOT NULL
            AND relative_strength_benchmark_provider_listing_id
                <> provider_listing_id
        )
        OR (
            relative_strength_benchmark_provider_listing_id IS NULL
            AND rel_spx IS NULL
            AND pct_rel_spx_20 IS NULL
            AND pct_rel_spx_50 IS NULL
            AND relative_return_spx_20d_pct IS NULL
            AND relative_return_spx_63d_pct IS NULL
            AND relative_return_spx_126d_pct IS NULL
            AND relative_return_spx_252d_pct IS NULL
            AND spx_beta_60d IS NULL
            AND spx_beta_252d IS NULL
            AND spx_correlation_60d IS NULL
            AND spx_correlation_252d IS NULL
        )
    ),

CONSTRAINT ck_tech_indicators_{slot}_timestamps
    CHECK (updated_at >= created_at)
```

The benchmark check permits a resolved benchmark with all 11 SPX values null
during aligned warm-up or another expected unavailable condition. It forbids
SPX values without benchmark lineage and self-benchmarking. The FK guarantees
the referenced listing exists; Python guarantees it is the reviewed active
`YAHOO/XIDX/SPX` identity for supported subjects.

## Publication Keys And Foreign Keys

`stonks.tech_indicators_publication` uses:

```sql
CONSTRAINT pk_tech_indicators_publication
    PRIMARY KEY (publication_id),

CONSTRAINT fk_tech_indicators_publication_run
    FOREIGN KEY (run_id)
    REFERENCES core.core_run(run_id)
    ON DELETE SET NULL,

CONSTRAINT fk_tech_indicators_publication_benchmark
    FOREIGN KEY (benchmark_provider_listing_id)
    REFERENCES stonks.provider_listing(provider_listing_id)
    ON DELETE RESTRICT,

CONSTRAINT fk_tech_indicators_publication_json_report
    FOREIGN KEY (json_report_object_id)
    REFERENCES core.stored_object(object_id)
    ON DELETE SET NULL,

CONSTRAINT fk_tech_indicators_publication_pdf_report
    FOREIGN KEY (pdf_report_object_id)
    REFERENCES core.stored_object(object_id)
    ON DELETE SET NULL
```

`resume_provider_listing_id` deliberately has no FK. It is immutable bounded
cursor evidence that remains intelligible after provider-listing cleanup; a
missing cursor listing makes resume validation fail rather than rewriting
publication history.

## Publication Checks

The publication relation uses these exact checks:

```sql
CONSTRAINT ck_tech_indicators_publication_kind
    CHECK (
        publication_kind IN (
            'DAILY',
            'CORRECTION',
            'VERSION_REBUILD',
            'BACKFILL',
            'ELIGIBILITY_REMOVAL'
        )
    ),

CONSTRAINT ck_tech_indicators_publication_status
    CHECK (
        status IN (
            'BUILDING', 'PREPARED', 'PUBLISHED',
            'FAILED', 'ABANDONED', 'RETIRED'
        )
    ),

CONSTRAINT ck_tech_indicators_publication_version
    CHECK (
        calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
        AND calculation_version = btrim(calculation_version)
    ),

CONSTRAINT ck_tech_indicators_publication_method
    CHECK (
        publication_method IS NULL
        OR publication_method IN ('IN_PLACE', 'STAGED', 'MEMBERSHIP_ONLY')
    ),

CONSTRAINT ck_tech_indicators_publication_method_kind
    CHECK (
        publication_method IS NULL
        OR (
            publication_kind = 'ELIGIBILITY_REMOVAL'
            AND publication_method = 'MEMBERSHIP_ONLY'
        )
        OR (
            publication_kind IN ('VERSION_REBUILD', 'BACKFILL')
            AND publication_method = 'STAGED'
        )
        OR (
            publication_kind IN ('DAILY', 'CORRECTION')
            AND publication_method IN ('IN_PLACE', 'STAGED')
        )
    ),

CONSTRAINT ck_tech_indicators_publication_scope
    CHECK (
        (scope_schema_version IS NULL AND scope_hash IS NULL)
        OR (
            scope_schema_version = 1
            AND scope_hash ~ '^[a-f0-9]{64}$'
        )
    ),

CONSTRAINT ck_tech_indicators_publication_dates
    CHECK (
        requested_start_date IS NULL
        OR requested_end_date IS NULL
        OR requested_end_date >= requested_start_date
    ),

CONSTRAINT ck_tech_indicators_publication_benchmark
    CHECK (
        (
            benchmark_required IS NULL
            AND benchmark_provider_listing_id IS NULL
            AND benchmark_contract_version IS NULL
            AND benchmark_coverage_start_date IS NULL
            AND benchmark_coverage_end_date IS NULL
            AND benchmark_source_row_count IS NULL
        )
        OR (
            benchmark_required
            AND benchmark_provider_listing_id IS NOT NULL
            AND benchmark_contract_version = 'TECH_INDICATORS_SPX_V1'
            AND benchmark_coverage_start_date IS NOT NULL
            AND benchmark_coverage_end_date IS NOT NULL
            AND benchmark_coverage_end_date >= benchmark_coverage_start_date
            AND benchmark_source_row_count > 0
        )
        OR (
            NOT benchmark_required
            AND benchmark_provider_listing_id IS NULL
            AND benchmark_contract_version IS NULL
            AND benchmark_coverage_start_date IS NULL
            AND benchmark_coverage_end_date IS NULL
            AND benchmark_source_row_count IS NULL
        )
    ),

CONSTRAINT ck_tech_indicators_publication_counts
    CHECK (
        (expected_listing_count IS NULL OR expected_listing_count >= 0)
        AND (expected_source_row_count IS NULL OR expected_source_row_count >= 0)
        AND (expected_payload_row_count IS NULL OR expected_payload_row_count >= 0)
        AND (inserted_row_count IS NULL OR inserted_row_count >= 0)
        AND (updated_row_count IS NULL OR updated_row_count >= 0)
        AND (deleted_row_count IS NULL OR deleted_row_count >= 0)
        AND (equivalent_row_count IS NULL OR equivalent_row_count >= 0)
        AND (warning_count IS NULL OR warning_count >= 0)
        AND (failure_count IS NULL OR failure_count >= 0)
        AND (completed_batch_count IS NULL OR completed_batch_count >= 0)
        AND (staged_payload_row_count IS NULL OR staged_payload_row_count >= 0)
    ),

CONSTRAINT ck_tech_indicators_publication_cursor
    CHECK (
        (
            completed_batch_count IS NULL
            AND staged_payload_row_count IS NULL
            AND resume_provider_listing_id IS NULL
            AND resume_trading_date IS NULL
            AND resume_cursor_updated_at IS NULL
        )
        OR (
            completed_batch_count IS NOT NULL
            AND staged_payload_row_count IS NOT NULL
            AND (
                (
                    completed_batch_count = 0
                    AND resume_provider_listing_id IS NULL
                    AND resume_trading_date IS NULL
                    AND resume_cursor_updated_at IS NULL
                )
                OR (
                    completed_batch_count > 0
                    AND resume_provider_listing_id IS NOT NULL
                    AND resume_trading_date IS NOT NULL
                    AND resume_cursor_updated_at IS NOT NULL
                )
            )
        )
    ),

CONSTRAINT ck_tech_indicators_publication_prepared_shape
    CHECK (
        status NOT IN ('PREPARED', 'PUBLISHED', 'RETIRED')
        OR (
            publication_method IS NOT NULL
            AND scope_schema_version = 1
            AND scope_hash IS NOT NULL
            AND benchmark_required IS NOT NULL
            AND expected_listing_count IS NOT NULL
            AND expected_source_row_count IS NOT NULL
            AND expected_payload_row_count IS NOT NULL
            AND inserted_row_count IS NOT NULL
            AND updated_row_count IS NOT NULL
            AND deleted_row_count IS NOT NULL
            AND equivalent_row_count IS NOT NULL
            AND warning_count IS NOT NULL
            AND failure_count IS NOT NULL
            AND completed_batch_count IS NOT NULL
            AND staged_payload_row_count IS NOT NULL
            AND source_validated_at IS NOT NULL
            AND prepared_at IS NOT NULL
            AND (
                status <> 'PREPARED'
                OR (
                    run_id IS NOT NULL
                    AND json_report_object_id IS NOT NULL
                    AND pdf_report_object_id IS NOT NULL
                    AND json_report_object_id <> pdf_report_object_id
                )
            )
        )
    ),

CONSTRAINT ck_tech_indicators_publication_method_cursor
    CHECK (
        publication_method = 'STAGED'
        OR (
            COALESCE(completed_batch_count, 0) = 0
            AND COALESCE(staged_payload_row_count, 0) = 0
            AND resume_provider_listing_id IS NULL
            AND resume_trading_date IS NULL
            AND resume_cursor_updated_at IS NULL
        )
    ),

CONSTRAINT ck_tech_indicators_publication_timestamps
    CHECK (
        updated_at >= created_at
        AND (
            (status = 'BUILDING'
             AND prepared_at IS NULL AND published_at IS NULL
             AND failed_at IS NULL AND abandoned_at IS NULL AND retired_at IS NULL)
            OR (status = 'PREPARED'
                AND prepared_at IS NOT NULL AND published_at IS NULL
                AND prepared_at >= created_at
                AND failed_at IS NULL AND abandoned_at IS NULL AND retired_at IS NULL)
            OR (status = 'PUBLISHED'
                AND prepared_at IS NOT NULL AND published_at IS NOT NULL
                AND prepared_at >= created_at AND published_at >= prepared_at
                AND failed_at IS NULL AND abandoned_at IS NULL AND retired_at IS NULL)
            OR (status = 'FAILED'
                AND failed_at IS NOT NULL AND published_at IS NULL
                AND failed_at >= created_at
                AND (prepared_at IS NULL OR failed_at >= prepared_at)
                AND abandoned_at IS NULL AND retired_at IS NULL)
            OR (status = 'ABANDONED'
                AND abandoned_at IS NOT NULL AND published_at IS NULL
                AND abandoned_at >= created_at
                AND (prepared_at IS NULL OR abandoned_at >= prepared_at)
                AND failed_at IS NULL AND retired_at IS NULL)
            OR (status = 'RETIRED'
                AND prepared_at IS NOT NULL AND published_at IS NOT NULL
                AND retired_at IS NOT NULL
                AND prepared_at >= created_at AND published_at >= prepared_at
                AND retired_at >= published_at
                AND failed_at IS NULL AND abandoned_at IS NULL)
        )
    )
```

`FAILED`/`ABANDONED` may retain `prepared_at` when failure occurs after
preparation. They may also terminate before scope/count/report facts exist.

## Membership Keys, FKs, And Checks

Membership uses:

```sql
CONSTRAINT pk_tech_indicators_publication_listing
    PRIMARY KEY (publication_id, provider_listing_id),

CONSTRAINT fk_tech_indicators_membership_publication
    FOREIGN KEY (publication_id)
    REFERENCES stonks.tech_indicators_publication(publication_id)
    ON DELETE RESTRICT,

CONSTRAINT fk_tech_indicators_membership_listing
    FOREIGN KEY (provider_listing_id)
    REFERENCES stonks.provider_listing(provider_listing_id)
    ON DELETE CASCADE,

CONSTRAINT fk_tech_indicators_membership_benchmark
    FOREIGN KEY (benchmark_provider_listing_id)
    REFERENCES stonks.provider_listing(provider_listing_id)
    ON DELETE RESTRICT,

CONSTRAINT ck_tech_indicators_membership_version
    CHECK (
        calculation_version ~ '^[A-Z][A-Z0-9_]{0,63}$'
        AND calculation_version = btrim(calculation_version)
    ),

CONSTRAINT ck_tech_indicators_membership_action
    CHECK (action IN ('PRESENT', 'REMOVE')),

CONSTRAINT ck_tech_indicators_membership_image
    CHECK (
        source_row_count >= 0
        AND payload_row_count >= 0
        AND (
            (
                action = 'REMOVE'
                AND target_slot IS NULL
                AND source_coverage_start_date IS NULL
                AND source_coverage_end_date IS NULL
                AND source_row_count = 0
                AND payload_row_count = 0
                AND benchmark_provider_listing_id IS NULL
            )
            OR (
                action = 'PRESENT'
                AND target_slot IN ('A', 'B')
                AND payload_row_count = source_row_count
                AND (
                    (
                        source_row_count = 0
                        AND source_coverage_start_date IS NULL
                        AND source_coverage_end_date IS NULL
                    )
                    OR (
                        source_row_count > 0
                        AND source_coverage_start_date IS NOT NULL
                        AND source_coverage_end_date IS NOT NULL
                        AND source_coverage_end_date >= source_coverage_start_date
                    )
                )
            )
        )
    ),

CONSTRAINT ck_tech_indicators_membership_timestamps
    CHECK (
        updated_at >= created_at
        AND (
            (
                is_active
                AND activated_at IS NOT NULL
                AND deactivated_at IS NULL
            )
            OR (
                NOT is_active
                AND activated_at IS NULL
                AND deactivated_at IS NULL
            )
            OR (
                NOT is_active
                AND activated_at IS NOT NULL
                AND deactivated_at IS NOT NULL
                AND deactivated_at >= activated_at
            )
        )
    )
```

The one-active-membership rule is an integrity index, not an S2.4 query index:

```sql
CREATE UNIQUE INDEX uq_tech_indicators_membership_active_listing
    ON stonks.tech_indicators_publication_listing (provider_listing_id)
    WHERE is_active;
```

## Lifecycle And Cross-Relation Enforcement

Checks cannot compare `OLD`/`NEW` rows or a membership with its parent. S2.5
therefore adds two narrow `BEFORE` triggers. They contain integrity logic only,
not calculation, readiness, or workflow orchestration.

The publication trigger rejects changes to immutable identity/version/kind,
changes to method or resolved scope after first population, illegal status
edges, and retirement while active membership remains:

```sql
CREATE FUNCTION stonks.enforce_tech_indicators_publication_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'BUILDING' THEN
            RAISE EXCEPTION 'tech-indicators publication must start BUILDING';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.publication_id IS DISTINCT FROM OLD.publication_id
       OR NEW.publication_kind IS DISTINCT FROM OLD.publication_kind
       OR NEW.calculation_version IS DISTINCT FROM OLD.calculation_version THEN
        RAISE EXCEPTION 'tech-indicators publication identity is immutable';
    END IF;

    IF OLD.publication_method IS NOT NULL
       AND NEW.publication_method IS DISTINCT FROM OLD.publication_method THEN
        RAISE EXCEPTION 'tech-indicators publication method is immutable';
    END IF;

    IF OLD.scope_hash IS NOT NULL
       AND (
           NEW.scope_hash IS DISTINCT FROM OLD.scope_hash
           OR NEW.scope_schema_version IS DISTINCT FROM OLD.scope_schema_version
       ) THEN
        RAISE EXCEPTION 'tech-indicators publication scope is immutable';
    END IF;

    IF OLD.effective_date IS NOT NULL
       AND NEW.effective_date IS DISTINCT FROM OLD.effective_date THEN
        RAISE EXCEPTION 'tech-indicators effective date is immutable';
    END IF;

    IF OLD.requested_start_date IS NOT NULL
       AND NEW.requested_start_date IS DISTINCT FROM OLD.requested_start_date THEN
        RAISE EXCEPTION 'tech-indicators start date is immutable';
    END IF;

    IF OLD.requested_end_date IS NOT NULL
       AND NEW.requested_end_date IS DISTINCT FROM OLD.requested_end_date THEN
        RAISE EXCEPTION 'tech-indicators end date is immutable';
    END IF;

    IF OLD.benchmark_required IS NOT NULL
       AND (NEW.benchmark_required,
            NEW.benchmark_provider_listing_id,
            NEW.benchmark_contract_version,
            NEW.benchmark_coverage_start_date,
            NEW.benchmark_coverage_end_date,
            NEW.benchmark_source_row_count)
           IS DISTINCT FROM
           (OLD.benchmark_required,
            OLD.benchmark_provider_listing_id,
            OLD.benchmark_contract_version,
            OLD.benchmark_coverage_start_date,
            OLD.benchmark_coverage_end_date,
            OLD.benchmark_source_row_count) THEN
        RAISE EXCEPTION 'tech-indicators benchmark facts are immutable';
    END IF;

    IF OLD.prepared_at IS NOT NULL
       AND (NEW.expected_listing_count,
            NEW.expected_source_row_count,
            NEW.expected_payload_row_count,
            NEW.inserted_row_count,
            NEW.updated_row_count,
            NEW.deleted_row_count,
            NEW.equivalent_row_count,
            NEW.warning_count,
            NEW.failure_count,
            NEW.completed_batch_count,
            NEW.staged_payload_row_count,
            NEW.resume_provider_listing_id,
            NEW.resume_trading_date,
            NEW.resume_cursor_updated_at,
            NEW.source_validated_at,
            NEW.prepared_at)
           IS DISTINCT FROM
           (OLD.expected_listing_count,
            OLD.expected_source_row_count,
            OLD.expected_payload_row_count,
            OLD.inserted_row_count,
            OLD.updated_row_count,
            OLD.deleted_row_count,
            OLD.equivalent_row_count,
            OLD.warning_count,
            OLD.failure_count,
            OLD.completed_batch_count,
            OLD.staged_payload_row_count,
            OLD.resume_provider_listing_id,
            OLD.resume_trading_date,
            OLD.resume_cursor_updated_at,
            OLD.source_validated_at,
            OLD.prepared_at) THEN
        RAISE EXCEPTION 'prepared tech-indicators publication facts are immutable';
    END IF;

    IF OLD.prepared_at IS NOT NULL THEN
        IF OLD.run_id IS NOT NULL
           AND NEW.run_id IS DISTINCT FROM OLD.run_id
           AND NEW.run_id IS NOT NULL THEN
            RAISE EXCEPTION 'tech-indicators run evidence cannot be replaced';
        END IF;
        IF OLD.json_report_object_id IS NOT NULL
           AND NEW.json_report_object_id IS DISTINCT FROM OLD.json_report_object_id
           AND NEW.json_report_object_id IS NOT NULL THEN
            RAISE EXCEPTION 'tech-indicators JSON report evidence cannot be replaced';
        END IF;
        IF OLD.pdf_report_object_id IS NOT NULL
           AND NEW.pdf_report_object_id IS DISTINCT FROM OLD.pdf_report_object_id
           AND NEW.pdf_report_object_id IS NOT NULL THEN
            RAISE EXCEPTION 'tech-indicators PDF report evidence cannot be replaced';
        END IF;
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT (
           (OLD.status = 'BUILDING' AND NEW.status IN ('PREPARED', 'FAILED', 'ABANDONED'))
           OR (OLD.status = 'PREPARED' AND NEW.status IN ('PUBLISHED', 'FAILED', 'ABANDONED'))
           OR (OLD.status = 'PUBLISHED' AND NEW.status = 'RETIRED')
       ) THEN
        RAISE EXCEPTION 'invalid tech-indicators publication status transition';
    END IF;

    IF NEW.status = 'RETIRED' AND OLD.status IS DISTINCT FROM 'RETIRED'
       AND EXISTS (
           SELECT 1
           FROM stonks.tech_indicators_publication_listing AS membership
           WHERE membership.publication_id = OLD.publication_id
             AND membership.is_active
       ) THEN
        RAISE EXCEPTION 'active tech-indicators publication cannot be retired';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tech_indicators_publication_transition
BEFORE INSERT OR UPDATE ON stonks.tech_indicators_publication
FOR EACH ROW
EXECUTE FUNCTION stonks.enforce_tech_indicators_publication_transition();
```

The membership trigger locks/validates its parent, matches calculation and
benchmark lineage, permits activation only for a `PUBLISHED` parent, preserves
candidate facts, and forbids reactivation of historical membership:

```sql
CREATE FUNCTION stonks.enforce_tech_indicators_membership_integrity()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    parent_status VARCHAR(16);
    parent_version VARCHAR(64);
    parent_benchmark_required BOOLEAN;
    parent_benchmark_provider_listing_id UUID;
BEGIN
    SELECT
        publication.status,
        publication.calculation_version,
        publication.benchmark_required,
        publication.benchmark_provider_listing_id
    INTO STRICT
        parent_status,
        parent_version,
        parent_benchmark_required,
        parent_benchmark_provider_listing_id
    FROM stonks.tech_indicators_publication AS publication
    WHERE publication.publication_id = NEW.publication_id
    FOR KEY SHARE;

    IF NEW.calculation_version IS DISTINCT FROM parent_version THEN
        RAISE EXCEPTION 'membership calculation version does not match publication';
    END IF;

    IF NEW.benchmark_provider_listing_id IS NOT NULL
       AND (
           parent_benchmark_required IS DISTINCT FROM true
           OR NEW.benchmark_provider_listing_id
                IS DISTINCT FROM parent_benchmark_provider_listing_id
       ) THEN
        RAISE EXCEPTION 'membership benchmark does not match publication';
    END IF;

    IF NEW.is_active AND parent_status <> 'PUBLISHED' THEN
        RAISE EXCEPTION 'active membership requires a published parent';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF (NEW.publication_id, NEW.provider_listing_id, NEW.action,
            NEW.target_slot, NEW.calculation_version,
            NEW.source_coverage_start_date, NEW.source_coverage_end_date,
            NEW.source_row_count, NEW.payload_row_count,
            NEW.benchmark_provider_listing_id, NEW.candidate_completed_at)
           IS DISTINCT FROM
           (OLD.publication_id, OLD.provider_listing_id, OLD.action,
            OLD.target_slot, OLD.calculation_version,
            OLD.source_coverage_start_date, OLD.source_coverage_end_date,
            OLD.source_row_count, OLD.payload_row_count,
            OLD.benchmark_provider_listing_id, OLD.candidate_completed_at) THEN
            RAISE EXCEPTION 'tech-indicators membership candidate facts are immutable';
        END IF;

        IF NOT OLD.is_active AND NEW.is_active
           AND OLD.deactivated_at IS NOT NULL THEN
            RAISE EXCEPTION 'historical tech-indicators membership cannot reactivate';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tech_indicators_membership_integrity
BEFORE INSERT OR UPDATE ON stonks.tech_indicators_publication_listing
FOR EACH ROW
EXECUTE FUNCTION stonks.enforce_tech_indicators_membership_integrity();
```

## Python-Owned Validation Boundary

Python remains the only supported normal writer. Before SQL it validates:

- exact copied OHLCV equality with the owning source row and chronological
  `history_observation_count`;
- finiteness of every populated double, all formulas, denominator/null rules,
  warm-up masks, TA-Lib settings/output, and numerical equivalence tolerances;
- streak values against prior closes, every rolling/recursive window, and
  generated-expression reference values;
- exact SPX identity/support predicate, exact-date alignment, benchmark UUID on
  every supported row, all 11 field masks, beta/correlation estimators, and
  canonicalization;
- complete inactive/active slot images, row counts, source coverage, preserved
  out-of-request rows, and no extra/missing/duplicate natural keys;
- publication count reconciliation, Core success/report existence and facts,
  scope/source/benchmark final revalidation, lock ownership, and transition
  ordering; and
- deterministic resume cursor/payload agreement.

PostgreSQL deliberately does not repeat an all-74-double NaN/infinity check,
rolling formulas, copied-source equality, exact benchmark metadata resolution,
warm-up schedules, or complete-image count scans in row triggers. Those would
duplicate the calculator, add write cost, or require cross-row state. Direct
unsupported SQL writes are not made safe by these basic constraints.

## Access And Grants

S2.5 adds no relation-specific `GRANT` or `REVOKE`. Empire currently provisions
one database credential and has no migration-owned application-role hierarchy;
inventing a technical-indicators-only role here would exceed the established
database contract. The package is the supported writer. The explicit
`UNION ALL` consumer view is not automatically updatable, so it has no write
trigger or rule. A future least-privilege role split must be platform-wide and
must amend this contract before changing relation grants.

## Required S2.5-S2.7 Verification

Tests must cover both slots and all constraints above, including source and
provider cascades, benchmark restriction, Core/report cleanup, version syntax,
basic bounds, streak/SPX shapes, membership uniqueness, all legal/illegal
lifecycle edges, immutable candidate facts, A/B visibility, and representative
valid warm-up rows. They must also prove Python rejects non-finite or
formula-invalid rows that PostgreSQL intentionally does not exhaustively check.

Any weakening or expansion of this integrity/validation boundary requires an
explicit contract amendment before migration.
