-- 0004: catatan panggilan provider (TD-01) + format dokumenter episode.

ALTER TABLE episodes ADD COLUMN format TEXT
    CHECK (format IS NULL OR format IN ('quick_files', 'archives', 'deep_files'));

-- Satu baris per idempotency key panggilan provider. Dipakai untuk:
-- * memakai ulang respons yang sudah dibayar (crash/retry tidak membayar dua kali);
-- * mendeteksi panggilan yang terputus di tengah jalan (status in_flight saat recovery);
-- * jejak biaya: estimasi token, estimasi biaya, otorisasi, dan entri ledger.
CREATE TABLE provider_calls (
    id                     TEXT PRIMARY KEY,
    idempotency_key        TEXT NOT NULL UNIQUE,
    episode_id             TEXT REFERENCES episodes (id),
    job_id                 TEXT,
    lease_token            INTEGER NOT NULL,
    provider               TEXT NOT NULL,
    task                   TEXT NOT NULL,
    purpose                TEXT NOT NULL,
    mode                   TEXT NOT NULL CHECK (mode IN ('simulated', 'real')),
    request_fingerprint    TEXT NOT NULL,
    request                TEXT NOT NULL,
    status                 TEXT NOT NULL
                           CHECK (status IN ('in_flight', 'succeeded', 'failed', 'unknown')),
    attempt                INTEGER NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    ledger_entry_id        TEXT NOT NULL REFERENCES ledger_entries (id),
    authorization_id       TEXT NOT NULL REFERENCES spend_authorizations (id),
    estimated_input_tokens INTEGER NOT NULL CHECK (estimated_input_tokens >= 0),
    max_output_tokens      INTEGER NOT NULL CHECK (max_output_tokens > 0),
    estimated_cost_idr     INTEGER NOT NULL CHECK (estimated_cost_idr >= 0),
    response               TEXT,
    input_tokens           INTEGER,
    output_tokens          INTEGER,
    actual_cost_idr        INTEGER,
    model                  TEXT,
    error                  TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    CHECK ((status = 'succeeded') = (response IS NOT NULL))
);
CREATE INDEX idx_provider_calls_episode ON provider_calls (episode_id, created_at);

-- Hasil yang sudah pasti (berhasil) atau tidak diketahui tidak boleh ditimpa.
CREATE TRIGGER provider_calls_settled_final
BEFORE UPDATE ON provider_calls
WHEN OLD.status IN ('succeeded', 'unknown')
BEGIN
    SELECT RAISE(ABORT, 'settled provider call is final');
END;

CREATE TRIGGER provider_calls_no_delete
BEFORE DELETE ON provider_calls
BEGIN
    SELECT RAISE(ABORT, 'provider calls cannot be deleted');
END;
