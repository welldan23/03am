-- 0001: skema inti Fase 1 (audit, episode, artefak, approval, anggaran, job).

-- Audit log: append-only, dijaga trigger.
CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    episode_id  TEXT,
    data        TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_audit_episode ON audit_log (episode_id, at);
CREATE INDEX idx_audit_action ON audit_log (action, at);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

-- Episode.
CREATE TABLE episodes (
    id                TEXT PRIMARY KEY,
    category          TEXT NOT NULL
                      CHECK (category IN ('sejarah', 'geopolitik', 'sains', 'geografi', 'misteri')),
    target_duration_s INTEGER NOT NULL CHECK (target_duration_s BETWEEN 30 AND 180),
    idea              TEXT,
    title             TEXT,
    status            TEXT NOT NULL,
    failed_from       TEXT,
    failure_reason    TEXT,
    version           INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX idx_episodes_status ON episodes (status);

-- Artefak berversi (tidak pernah ditimpa).
CREATE TABLE artifacts (
    id           TEXT PRIMARY KEY,
    episode_id   TEXT NOT NULL REFERENCES episodes (id),
    kind         TEXT NOT NULL,
    version      INTEGER NOT NULL CHECK (version >= 1),
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    UNIQUE (episode_id, kind, version)
);

CREATE TRIGGER artifacts_immutable BEFORE UPDATE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifacts are immutable; create a new version');
END;

-- Approval gate G0–G3.
CREATE TABLE approvals (
    id              TEXT PRIMARY KEY,
    episode_id      TEXT NOT NULL REFERENCES episodes (id),
    gate            TEXT NOT NULL CHECK (gate IN ('G0', 'G1', 'G2', 'G3')),
    episode_version INTEGER NOT NULL,
    subject         TEXT NOT NULL,
    subject_hash    TEXT NOT NULL,
    spend_cap_idr   INTEGER CHECK (spend_cap_idr IS NULL OR spend_cap_idr >= 0),
    status          TEXT NOT NULL
                    CHECK (status IN ('pending', 'approved', 'rejected', 'revision_requested',
                                      'superseded', 'expired')),
    token_hash      TEXT,
    requested_at    TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    decided_at      TEXT,
    decided_by      TEXT,
    notes           TEXT,
    decision_data   TEXT NOT NULL DEFAULT '{}'
);
CREATE UNIQUE INDEX uq_approvals_one_pending ON approvals (episode_id, gate)
    WHERE status = 'pending';
CREATE INDEX idx_approvals_episode ON approvals (episode_id, gate, status);

-- Keputusan final tidak bisa diubah lagi, kecuali approved → superseded (karena revisi).
CREATE TRIGGER approvals_decision_final BEFORE UPDATE OF status ON approvals
WHEN OLD.status <> 'pending'
     AND NOT (OLD.status = 'approved' AND NEW.status = 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'approval decision is final');
END;

-- Periode anggaran bulanan (snapshot rencana yang diaktifkan owner).
CREATE TABLE budget_periods (
    period       TEXT PRIMARY KEY,
    status       TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    plan         TEXT NOT NULL,
    plan_hash    TEXT NOT NULL,
    fx_usd_idr   TEXT NOT NULL,
    activated_by TEXT NOT NULL,
    activated_at TEXT NOT NULL
);

-- Otorisasi belanja: semua lahir dari keputusan owner.
CREATE TABLE spend_authorizations (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('operational', 'preproduction', 'production')),
    period        TEXT,
    episode_id    TEXT REFERENCES episodes (id),
    approval_id   TEXT REFERENCES approvals (id),
    max_idr       INTEGER NOT NULL CHECK (max_idr >= 0),
    status        TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    created_by    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    revoked_at    TEXT,
    revoke_reason TEXT,
    CHECK ((kind = 'operational' AND period IS NOT NULL AND episode_id IS NULL)
        OR (kind <> 'operational' AND episode_id IS NOT NULL AND approval_id IS NOT NULL))
);
CREATE UNIQUE INDEX uq_auth_operational_period ON spend_authorizations (period)
    WHERE kind = 'operational';
CREATE UNIQUE INDEX uq_auth_episode_active ON spend_authorizations (episode_id, kind)
    WHERE kind <> 'operational' AND status = 'active';

-- Ledger biaya (reservasi → realisasi / pelepasan).
CREATE TABLE ledger_entries (
    id                  TEXT PRIMARY KEY,
    idempotency_key     TEXT NOT NULL UNIQUE,
    period              TEXT NOT NULL,
    mode                TEXT NOT NULL CHECK (mode IN ('simulated', 'real')),
    category            TEXT NOT NULL CHECK (category IN ('openai', 'higgsfield', 'tts')),
    source              TEXT NOT NULL CHECK (source IN ('studio', 'hermes')),
    purpose             TEXT NOT NULL,
    authorization_id    TEXT NOT NULL REFERENCES spend_authorizations (id),
    episode_id          TEXT REFERENCES episodes (id),
    status              TEXT NOT NULL CHECK (status IN ('reserved', 'committed', 'released')),
    reserved_usd_micros INTEGER NOT NULL CHECK (reserved_usd_micros >= 0),
    reserved_idr        INTEGER NOT NULL CHECK (reserved_idr >= 0),
    actual_usd_micros   INTEGER CHECK (actual_usd_micros IS NULL OR actual_usd_micros >= 0),
    actual_idr          INTEGER CHECK (actual_idr IS NULL OR actual_idr >= 0),
    fx_usd_idr          TEXT NOT NULL,
    price_ref           TEXT NOT NULL,
    overrun             INTEGER NOT NULL DEFAULT 0 CHECK (overrun IN (0, 1)),
    meta                TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK ((status = 'committed') = (actual_idr IS NOT NULL))
);
CREATE INDEX idx_ledger_usage ON ledger_entries (period, mode, category, status);
CREATE INDEX idx_ledger_authorization ON ledger_entries (authorization_id, mode, status);

-- Antrean job dengan lease.
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL,
    episode_id      TEXT,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'obsolete',
                                      'cancelled')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL CHECK (max_attempts >= 1),
    run_after       TEXT NOT NULL,
    lease_owner     TEXT,
    lease_until     TEXT,
    idempotency_key TEXT NOT NULL UNIQUE,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_jobs_ready ON jobs (status, run_after);
CREATE INDEX idx_jobs_episode ON jobs (episode_id, status);
