-- Media-scheduling: add notes column to authorized_users.
-- Closes the phantom-field-on-write slip surfaced at Phase 0 of
-- media-scheduling-wiring: the frontend `AuthorizedUser` type +
-- `_persistable()` helper silently dropped `notes` on every
-- insert/update because the column did not exist in the schema.
-- Phase 1 Part 3 closes the gap at the layer of the cause (schema),
-- not the consumer.
--
-- Nullable; no default — pre-existing rows keep NULL notes,
-- matching the frontend type's `notes?: string | null`.

ALTER TABLE media_scheduling.authorized_users
    ADD COLUMN IF NOT EXISTS notes TEXT;
