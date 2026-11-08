-- Migration 109: drop the dead products.logout_behavior column.
-- Nothing reads it at runtime (the seed Header always signs out); the core
-- admin page + schema fields were removed in the same change. 005 stays as history.
ALTER TABLE public.products DROP COLUMN IF EXISTS logout_behavior;
