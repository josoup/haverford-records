-- Haverford records aggregator — canonical schema.
--
-- Three ideas this schema is built around:
--   1. Raw documents are immutable and never thrown away, so a parser fix can
--      reprocess history without re-hitting anyone's website.
--   2. The record book is HUMAN-OWNED. The engine reads it; only a sign-off
--      writes it.
--   3. Candidates carry a stable key, because the nightly job fully
--      re-evaluates and must UPSERT rather than pile up duplicates.

-- ============================================================ raw layer ====

CREATE TABLE source (
    key             text PRIMARY KEY,          -- 'haverford_site', 'tfrrs', ...
    display_name    text NOT NULL,
    base_url        text NOT NULL,
    enabled         boolean NOT NULL DEFAULT true
);

-- Append-only. A source AMENDING a result (a DQ applied days later, a wind
-- reading corrected) shows up as a new row with the same url and a different
-- content_hash -- which is exactly how we detect amendments.
CREATE TABLE raw_document (
    id              bigserial PRIMARY KEY,
    source_key      text NOT NULL REFERENCES source(key),
    url             text NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    http_status     int  NOT NULL,
    content_hash    text NOT NULL,             -- sha256 of body
    body            text,
    UNIQUE (url, content_hash)
);
CREATE INDEX raw_document_url_idx        ON raw_document (url, fetched_at DESC);
CREATE INDEX raw_document_source_idx     ON raw_document (source_key, fetched_at DESC);

-- =========================================================== entities =====

CREATE TABLE sport (
    id              serial PRIMARY KEY,
    code            text NOT NULL UNIQUE,      -- 'msoc', 'wtrack', ...
    name            text NOT NULL,
    gender          text NOT NULL CHECK (gender IN ('M','W','COED')),
    UNIQUE (name, gender)
);

CREATE TABLE season (
    id              serial PRIMARY KEY,
    sport_id        int NOT NULL REFERENCES sport(id),
    label           text NOT NULL,             -- '2024-25'
    start_year      int  NOT NULL,
    UNIQUE (sport_id, label)
);

-- The athlete spine. Everything else resolves against this.
CREATE TABLE athlete (
    id              bigserial PRIMARY KEY,
    display_name    text NOT NULL,
    first_name      text,
    last_name       text,
    grad_year       int,
    hometown        text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    merged_into     bigint REFERENCES athlete(id)   -- set when deduped away
);
CREATE INDEX athlete_last_name_idx ON athlete (lower(last_name));

-- The crosswalk. THE most important table in the system: a human decision
-- about identity, recorded once, is permanent. Never re-fuzzy-match a pair a
-- person already resolved.
CREATE TABLE athlete_alias (
    id              bigserial PRIMARY KEY,
    athlete_id      bigint NOT NULL REFERENCES athlete(id),
    source_key      text   NOT NULL REFERENCES source(key),
    source_athlete_id text,                    -- stable id where the source has one
    name_as_written text NOT NULL,
    confidence      real,                      -- null when a human decided
    resolved_by     text NOT NULL DEFAULT 'auto' CHECK (resolved_by IN ('auto','human')),
    resolved_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_key, source_athlete_id, name_as_written)
);

CREATE TABLE roster_entry (
    id              bigserial PRIMARY KEY,
    athlete_id      bigint NOT NULL REFERENCES athlete(id),
    sport_id        int    NOT NULL REFERENCES sport(id),
    season_id       int    NOT NULL REFERENCES season(id),
    jersey          text,
    position        text,
    class_year      text,                      -- 'Fr.', 'So.', ...
    height          text,
    hometown        text,
    previous_school text,
    raw_document_id bigint NOT NULL REFERENCES raw_document(id),   -- provenance
    UNIQUE (athlete_id, season_id)
);

-- =========================================================== the marks ====

-- One row per observed performance/statline, normalized. Conditions are
-- columns rather than notes because a track mark is not comparable without
-- them.
CREATE TABLE mark (
    id              bigserial PRIMARY KEY,
    athlete_id      bigint NOT NULL REFERENCES athlete(id),
    sport_id        int    NOT NULL REFERENCES sport(id),
    season_id       int    REFERENCES season(id),
    stat_key        text   NOT NULL,           -- '800m', 'career_assists', ...
    value           numeric NOT NULL,          -- canonical unit; see unit
    unit            text   NOT NULL,           -- 'centiseconds','cm','count'
    occurred_on     date,
    event_name      text,                      -- meet or opponent
    conditions      jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- e.g. {"wind":1.8,"timing":"FAT","track":"banked","altitude_m":30}
    raw_document_id bigint NOT NULL REFERENCES raw_document(id),
    UNIQUE (athlete_id, stat_key, occurred_on, value, raw_document_id)
);
CREATE INDEX mark_lookup_idx ON mark (sport_id, stat_key, value);

-- ======================================================= the record book ==

CREATE TABLE record_definition (
    id              serial PRIMARY KEY,
    sport_id        int  NOT NULL REFERENCES sport(id),
    scope           text NOT NULL CHECK (scope IN ('school','conference','meet','facility','class')),
    record_type     text NOT NULL CHECK (record_type IN ('counting','best_mark','streak')),
    stat_key        text NOT NULL,
    unit            text NOT NULL,
    direction       text NOT NULL CHECK (direction IN ('higher_better','lower_better')),
    conditions      jsonb NOT NULL DEFAULT '{}'::jsonb,   -- qualifying constraints
    label           text NOT NULL,
    UNIQUE (sport_id, scope, stat_key, label)
);

-- Human-owned. The engine reads this and never writes it; a sign-off does.
CREATE TABLE record_holder (
    id              bigserial PRIMARY KEY,
    record_definition_id int NOT NULL REFERENCES record_definition(id),
    athlete_id      bigint REFERENCES athlete(id),
    holder_name     text NOT NULL,             -- kept verbatim: pre-scrape history
    value           numeric NOT NULL,
    achieved_on     date,
    is_current      boolean NOT NULL DEFAULT true,
    verified_by     text,
    verified_at     timestamptz,
    notes           text
);
CREATE INDEX record_holder_current_idx ON record_holder (record_definition_id) WHERE is_current;

-- ========================================================== candidates ====

-- candidate_key = hash(record_definition_id, athlete_id, candidate_type,
--                      triggering value). Stable across nightly recomputes, so
-- the review state below survives -- a dismissed candidate STAYS dismissed
-- instead of reappearing in tomorrow's queue.
CREATE TABLE candidate (
    id              bigserial PRIMARY KEY,
    candidate_key   text NOT NULL UNIQUE,
    record_definition_id int NOT NULL REFERENCES record_definition(id),
    athlete_id      bigint NOT NULL REFERENCES athlete(id),
    candidate_type  text NOT NULL CHECK (candidate_type IN ('BROKEN','TIED','APPROACHING')),
    value           numeric,
    margin          numeric,                   -- distance to the standing record
    projection      jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {"rate":0.42,"opportunities_remaining":6,"projected_final":31.5}
    supporting_mark_id bigint REFERENCES mark(id),
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz NOT NULL DEFAULT now(),
    review_state    text NOT NULL DEFAULT 'pending'
                    CHECK (review_state IN ('pending','confirmed','rejected','needs_info')),
    reviewed_by     text,
    reviewed_at     timestamptz,
    review_notes    text
);
CREATE INDEX candidate_queue_idx ON candidate (review_state, last_seen_at DESC);

-- Sources disagreeing is a first-class thing to SHOW a reviewer, not something
-- to silently resolve by picking a favorite.
CREATE TABLE conflict (
    id              bigserial PRIMARY KEY,
    athlete_id      bigint REFERENCES athlete(id),
    stat_key        text NOT NULL,
    occurred_on     date,
    observations    jsonb NOT NULL,   -- [{"source":"tfrrs","value":24211}, ...]
    detected_at     timestamptz NOT NULL DEFAULT now(),
    resolved_by     text,
    resolved_at     timestamptz,
    resolution      jsonb
);

-- ================================================================= ops ====

CREATE TABLE ingest_run (
    id              bigserial PRIMARY KEY,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','ok','failed'))
);

-- A batch pipeline fails SILENTLY: a parser breaks, zero rows come back, and
-- everyone assumes it was a quiet week. Every run records its yield per source
-- so a zero-row Saturday in April can page somebody.
CREATE TABLE source_health (
    id              bigserial PRIMARY KEY,
    run_id          bigint NOT NULL REFERENCES ingest_run(id),
    source_key      text   NOT NULL REFERENCES source(key),
    pages_fetched   int NOT NULL DEFAULT 0,
    rows_parsed     int NOT NULL DEFAULT 0,
    parse_errors    int NOT NULL DEFAULT 0,
    trailing_avg    real,
    anomalous       boolean NOT NULL DEFAULT false
);
