-- Keep stonks source snapshot identity compatible with core object/run cleanup.
--
-- Source snapshots are persistent provider-content identities. The core run and
-- stored object rows they were first seen through are retention-managed
-- execution/artifact metadata, so they must not become permanent retention
-- anchors.

ALTER TABLE stonks.provider_source_snapshot
    DROP CONSTRAINT IF EXISTS provider_source_snapshot_first_seen_object_id_fkey;

ALTER TABLE stonks.provider_source_snapshot
    ADD CONSTRAINT fk_provider_source_snapshot_first_seen_object
        FOREIGN KEY (first_seen_object_id)
        REFERENCES core.stored_object(object_id)
        ON DELETE SET NULL;

ALTER TABLE stonks.provider_source_snapshot
    DROP CONSTRAINT IF EXISTS provider_source_snapshot_first_seen_run_id_fkey;

ALTER TABLE stonks.provider_source_snapshot
    ADD CONSTRAINT fk_provider_source_snapshot_first_seen_run
        FOREIGN KEY (first_seen_run_id)
        REFERENCES core.core_run(run_id)
        ON DELETE SET NULL;

ALTER TABLE stonks.provider_source_snapshot_object
    DROP CONSTRAINT IF EXISTS provider_source_snapshot_object_object_id_fkey;

ALTER TABLE stonks.provider_source_snapshot_object
    ADD CONSTRAINT fk_provider_source_snapshot_object_object
        FOREIGN KEY (object_id)
        REFERENCES core.stored_object(object_id)
        ON DELETE CASCADE;
