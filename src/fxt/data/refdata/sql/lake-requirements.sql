-- fxt meta database: what the lake should contain
-- Run after meta-db.sql and meta-db-seed.sql (needs sources, markets, symbols, intervals).
--
-- One row = one (tier, interval) data set that should exist, per year, for:
--   symbol IS NULL   every symbol the source carries in that market (source_symbols)
--   symbol = 'X'     that symbol only
--
-- Merging, per (source, market, symbol), keyed by (tier, interval):
--   start from the market-wide rows, then let the symbol's rows replace/add
--   (like dict.update). required = 0 cancels a market-wide row for one symbol.
--
-- Years (inclusive):
--   first_year NULL  raw:     the first raw year on disk for that (symbol, interval)
--                    derived: the symbol's first raw year (any raw interval)
--   last_year  NULL  the current year
-- Missing years in the middle are always caught; missing years at the start
-- only when first_year is set.
--
-- tier/interval for derived rows = the output interval of a derive job
-- (fxt.data.derived.jobs.JOBS, e.g. 1MIN -> bars-1min).
PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS lake_requirements (
    source     TEXT NOT NULL REFERENCES sources (name),
    market     TEXT NOT NULL REFERENCES markets (name),
    symbol     TEXT,
    tier       TEXT NOT NULL CHECK (tier IN ('raw', 'derived')),
    interval   TEXT NOT NULL REFERENCES intervals (name),
    first_year INTEGER CHECK (first_year IS NULL OR first_year BETWEEN 1900 AND 2200),
    last_year  INTEGER CHECK (last_year  IS NULL OR last_year  BETWEEN 1900 AND 2200),
    required   INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    notes      TEXT,
    CHECK (first_year IS NULL OR last_year IS NULL OR first_year <= last_year),
    FOREIGN KEY (market, symbol) REFERENCES symbols (market, name)
);

-- one row per scope + (tier, interval). SQLite treats NULLs as distinct in a
-- UNIQUE constraint, so market-wide rows get their own partial index.
CREATE UNIQUE INDEX IF NOT EXISTS lake_req_market
    ON lake_requirements (source, market, tier, interval) WHERE symbol IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS lake_req_symbol
    ON lake_requirements (source, market, symbol, tier, interval) WHERE symbol IS NOT NULL;

-- bar intervals the derive jobs write (canonical names; not source intervals).
-- Can move into meta-db-seed.sql's intervals insert.
INSERT OR IGNORE INTO intervals (name, seconds) VALUES
    ('1MIN',  60),
    ('1HOUR', 3600);

-- Requirements ------------------------------------------------------------
INSERT INTO lake_requirements (source, market, symbol, tier, interval, first_year, notes) VALUES
    ('dukascopy', 'forex', NULL, 'raw',     'TICK',  2013, '2012 skipped: most pairs have no January data'),
    ('dukascopy', 'forex', NULL, 'derived', '1MIN',  NULL, NULL),
    ('dukascopy', 'forex', NULL, 'derived', '1HOUR', NULL, NULL);

-- Examples (symbol-specific rows):
--   a pair whose history starts later:
--     ('dukascopy', 'forex', 'XXXYYY', 'raw', 'TICK', 2016, 'history starts 2016')
--   one pair without 1HOUR bars:
--     (source, market, symbol, tier, interval, required) = ('dukascopy', 'forex', 'XXXYYY', 'derived', '1HOUR', 0)
--   a bars-only index (raw is 1MIN, so no TICK and no 1MIN derive step):
--     ('somesrc', 'index', 'SPX', 'raw',     '1MIN',  2015, NULL),
--     ('somesrc', 'index', 'SPX', 'derived', '1HOUR', NULL, NULL)

COMMIT;
