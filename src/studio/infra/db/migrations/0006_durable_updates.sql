-- 0006: pemrosesan update chat yang tahan crash (hotfix reliability Fase 3, ADR-0013).
--
-- Lifecycle update: received → processing → committed → delivered (atau failed).
-- * isi update disimpan saat diterima, karena aiogram mengakui offset ke Telegram sebelum
--   handler selesai: update yang hilang karena crash TIDAK akan dikirim ulang Telegram;
-- * aksi bisnis + status `committed` + balasan (ui_reply_outbox) ditulis dalam SATU transaksi;
-- * lease + fencing token mencegah dua pemroses meng-commit update yang sama.

-- Digantikan ui_inbox (dedupe sekarang bagian dari lifecycle, bukan tanda "sudah diproses"
-- yang dipasang sebelum pemrosesan).
DROP TABLE ui_processed_updates;

CREATE TABLE ui_inbox (
    channel         TEXT NOT NULL,
    update_id       INTEGER NOT NULL,
    chat_id         TEXT NOT NULL,
    user_id         TEXT,
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('received', 'processing', 'committed', 'delivered', 'failed')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_owner     TEXT,
    lease_token     INTEGER NOT NULL DEFAULT 0,
    lease_until     TEXT,
    next_attempt_at TEXT NOT NULL,
    last_error      TEXT,
    received_at     TEXT NOT NULL,
    committed_at    TEXT,
    delivered_at    TEXT,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (channel, update_id)
);
CREATE INDEX idx_ui_inbox_due ON ui_inbox (status, next_attempt_at);

-- Lapis kedua: update yang aksi bisnisnya sudah di-commit tidak pernah bisa kembali diproses.
CREATE TRIGGER ui_inbox_no_reprocess_after_commit
BEFORE UPDATE OF status ON ui_inbox
WHEN OLD.status IN ('committed', 'delivered', 'failed')
 AND NEW.status IN ('received', 'processing')
BEGIN
    SELECT RAISE(ABORT, 'committed update cannot be processed again');
END;

-- Balasan untuk satu update. Satu baris = satu panggilan Bot API (pesan panjang sudah dipecah),
-- supaya crash di tengah pengiriman paling banyak mengulang satu panggilan.
CREATE TABLE ui_reply_outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL,
    update_id       INTEGER NOT NULL,
    seq             INTEGER NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('send', 'edit', 'edit_keyboard', 'answer')),
    payload         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'dead')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TEXT NOT NULL,
    claimed_by      TEXT,
    claimed_until   TEXT,
    message_id      INTEGER,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    sent_at         TEXT,
    UNIQUE (channel, update_id, seq),
    FOREIGN KEY (channel, update_id) REFERENCES ui_inbox (channel, update_id)
);
CREATE INDEX idx_ui_reply_outbox_due ON ui_reply_outbox (status, next_attempt_at);

-- Balasan hanya boleh lahir bersama commit (atau kegagalan final) update-nya.
CREATE TRIGGER ui_reply_outbox_requires_commit
BEFORE INSERT ON ui_reply_outbox
WHEN (SELECT status FROM ui_inbox WHERE channel = NEW.channel AND update_id = NEW.update_id)
     NOT IN ('committed', 'failed')
BEGIN
    SELECT RAISE(ABORT, 'reply rows require a committed or failed update');
END;
