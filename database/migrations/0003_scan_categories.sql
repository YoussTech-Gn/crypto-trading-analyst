-- Migration: 0003_scan_categories
-- Adds a display/filter category to each ranked asset. Categories never affect ranking.

ALTER TABLE scan_rankings ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'CRYPTO';
