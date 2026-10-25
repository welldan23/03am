-- 0005: antarmuka percakapan (Fase 3) + outbox notifikasi (ADR-0012).

-- Update dari kanal chat yang sudah diproses. Telegram bisa mengirim ulang update yang sama
-- (restart, timeout long polling); update yang sudah tercatat diabaikan.
CREATE TABLE ui_processed_updates (
    channel     TEXT NOT NULL,
    update_id   INTEGER NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (channel, update_id)
);

-- Kode tombol sekali pakai. callback_data hanya berisi kode acak pendek; yang disimpan di sini
-- cuma hash-nya. Kode terikat ke actor yang menerimanya, punya masa berlaku, dan semua kode
-- dalam satu grup (satu kartu) hangus bersamaan begitu salah satunya dipakai.
CREATE TABLE ui_action_codes (
    id          TEXT PRIMARY KEY,
    group_id    TEXT NOT NULL,
    code_hash   TEXT NOT NULL UNIQUE,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    used_action TEXT
);
CREATE INDEX idx_ui_action_codes_group ON ui_action_codes (group_id);
CREATE INDEX idx_ui_action_codes_expiry ON ui_action_codes (expires_at);

-- State percakapan per chat (alur buat dokumenter, menunggu catatan revisi, episode aktif).
-- Disimpan di SQLite supaya bot yang di-restart tidak kehilangan konteks.
CREATE TABLE ui_conversations (
    channel    TEXT NOT NULL,
    chat_id    TEXT NOT NULL,
    actor      TEXT NOT NULL,
    state      TEXT NOT NULL,
    data       TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (channel, chat_id)
);

-- Outbox notifikasi. Baris dibuat oleh trigger di transaksi yang SAMA dengan kejadiannya,
-- jadi notifikasi tidak bisa hilang (commit) atau muncul tanpa kejadian (rollback).
-- Pengiriman dilakukan dispatcher di luar transaksi.
CREATE TABLE notification_outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key       TEXT NOT NULL UNIQUE,
    kind            TEXT NOT NULL,
    episode_id      TEXT,
    ref_id          TEXT,
    data            TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'dead')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TEXT NOT NULL,
    claimed_by      TEXT,
    claimed_until   TEXT,
    delivered_to    TEXT NOT NULL DEFAULT '[]',
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    sent_at         TEXT
);
CREATE INDEX idx_notification_outbox_due ON notification_outbox (status, next_attempt_at);

CREATE TRIGGER notification_outbox_no_delete
BEFORE DELETE ON notification_outbox
BEGIN
    SELECT RAISE(ABORT, 'notification outbox rows cannot be deleted');
END;

-- Kejadian penting dari audit log → outbox.
CREATE TRIGGER outbox_from_audit
AFTER INSERT ON audit_log
WHEN NEW.action = 'approval.requested'
  OR (NEW.action = 'episode.transition' AND (
        json_extract(NEW.data, '$.to') IN ('RESEARCHING', 'FAILED', 'EXPORTED', 'REJECTED',
                                            'CANCELLED', 'STORYBOARDING')
        OR (json_extract(NEW.data, '$.to') = 'SCRIPTING'
            AND json_extract(NEW.data, '$.from') = 'FACT_CHECKING')))
BEGIN
    INSERT INTO notification_outbox (event_key, kind, episode_id, ref_id, data,
                                     next_attempt_at, created_at)
    VALUES (
        'audit:' || NEW.id,
        CASE
            WHEN NEW.action = 'approval.requested' THEN 'approval.requested'
            WHEN json_extract(NEW.data, '$.to') = 'RESEARCHING' THEN 'research.started'
            WHEN json_extract(NEW.data, '$.to') = 'SCRIPTING' THEN 'research.brief_ready'
            WHEN json_extract(NEW.data, '$.to') = 'STORYBOARDING' THEN 'script.ready'
            WHEN json_extract(NEW.data, '$.to') = 'FAILED' THEN 'episode.failed'
            WHEN json_extract(NEW.data, '$.to') = 'EXPORTED' THEN 'episode.completed'
            ELSE 'episode.closed'
        END,
        NEW.episode_id,
        NEW.entity_id,
        NEW.data,
        NEW.at,
        NEW.at
    );
END;

-- Job dijadwalkan ulang setelah gagal sementara → outbox (satu notifikasi per percobaan).
CREATE TRIGGER outbox_from_job_retry
AFTER UPDATE OF status ON jobs
WHEN OLD.status = 'running' AND NEW.status = 'queued'
BEGIN
    INSERT OR IGNORE INTO notification_outbox (event_key, kind, episode_id, ref_id, data,
                                               next_attempt_at, created_at)
    VALUES (
        'job:' || NEW.id || ':' || NEW.attempts,
        'job.retry',
        NEW.episode_id,
        NEW.id,
        json_object(
            'attempts', NEW.attempts,
            'max_attempts', NEW.max_attempts,
            'run_after', NEW.run_after,
            'stage', json_extract(NEW.payload, '$.expected_status'),
            'error', NEW.last_error
        ),
        NEW.updated_at,
        NEW.updated_at
    );
END;
