-- Migration 005: Add logout_behavior column to products table
-- Controls how the logout button behaves in each product's frontend:
--   'redirect' = redirects to NoctusAI dashboard (SSO stays active)
--   'signout'  = actually signs out the user (for products with direct auth)

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS logout_behavior TEXT NOT NULL DEFAULT 'redirect';

-- Update existing products
UPDATE products SET logout_behavior = 'redirect' WHERE slug = 'erp-imobiliario';
UPDATE products SET logout_behavior = 'redirect' WHERE slug = 'personal-finance';
UPDATE products SET logout_behavior = 'signout'  WHERE slug = 'therapy-platform';

-- Also update the 001 migration's CREATE TABLE for fresh deploys
COMMENT ON COLUMN products.logout_behavior IS 'redirect = back to NoctusAI dashboard (SSO stays active), signout = actual sign out';
