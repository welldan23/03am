-- 0003: invarian keamanan di level database (pertahanan berlapis).
-- Kode aplikasi sudah memeriksa semua ini; trigger memastikan jalur internal mana pun
-- (service yang dipanggil langsung, skrip, bug) tetap tidak bisa melewatinya.

-- 1. Episode hanya bisa keluar dari gate (selain dibatalkan) kalau ada keputusan manusia
--    yang tercatat untuk gate itu, untuk versi episode yang sama, dan jenis keputusannya
--    cocok dengan arah transisi.
CREATE TRIGGER episodes_gate_exit_requires_decision
BEFORE UPDATE OF status ON episodes
WHEN OLD.status IN ('AWAITING_TOPIC', 'AWAITING_EDITORIAL', 'AWAITING_COST', 'AWAITING_FINAL')
     AND NEW.status <> 'CANCELLED'
     AND NOT EXISTS (
         SELECT 1 FROM approvals a
         WHERE a.episode_id = OLD.id
           AND a.episode_version = OLD.version
           AND a.decided_by IS NOT NULL
           AND a.gate = CASE OLD.status
               WHEN 'AWAITING_TOPIC' THEN 'G0'
               WHEN 'AWAITING_EDITORIAL' THEN 'G1'
               WHEN 'AWAITING_COST' THEN 'G2'
               ELSE 'G3' END
           AND a.status = CASE
               WHEN NEW.status = 'REJECTED' THEN 'rejected'
               WHEN (OLD.status = 'AWAITING_TOPIC' AND NEW.status = 'RESEARCHING')
                 OR (OLD.status = 'AWAITING_EDITORIAL' AND NEW.status = 'ESTIMATING_COST')
                 OR (OLD.status = 'AWAITING_COST' AND NEW.status = 'GENERATING_ASSETS')
                 OR (OLD.status = 'AWAITING_FINAL' AND NEW.status = 'EXPORTING') THEN 'approved'
               ELSE 'revision_requested' END
     )
BEGIN
    SELECT RAISE(ABORT, 'gate exit requires a recorded owner decision');
END;

-- 2. Otorisasi belanja episode wajib lahir dari approval G0/G2 yang disetujui, dan batasnya
--    tidak boleh melebihi batas yang tertera di approval itu.
CREATE TRIGGER spend_authorizations_require_approval
BEFORE INSERT ON spend_authorizations
WHEN NEW.kind <> 'operational'
     AND NOT EXISTS (
         SELECT 1 FROM approvals a
         WHERE a.id = NEW.approval_id
           AND a.episode_id = NEW.episode_id
           AND a.status = 'approved'
           AND a.gate = CASE NEW.kind WHEN 'preproduction' THEN 'G0' ELSE 'G2' END
           AND a.spend_cap_idr IS NOT NULL
           AND NEW.max_idr <= a.spend_cap_idr
     )
BEGIN
    SELECT RAISE(ABORT, 'episode spend authorization requires an approved G0/G2 approval');
END;

-- 3. Otorisasi operasional hanya untuk periode yang sudah diaktifkan owner.
CREATE TRIGGER spend_authorizations_operational_requires_period
BEFORE INSERT ON spend_authorizations
WHEN NEW.kind = 'operational'
     AND NOT EXISTS (
         SELECT 1 FROM budget_periods p WHERE p.period = NEW.period AND p.status = 'active'
     )
BEGIN
    SELECT RAISE(ABORT, 'operational authorization requires an active budget period');
END;

-- 4. Otorisasi episode tidak bisa dinaikkan batasnya atau dihidupkan lagi setelah dicabut.
CREATE TRIGGER spend_authorizations_episode_cap_fixed
BEFORE UPDATE OF max_idr ON spend_authorizations
WHEN OLD.kind <> 'operational' AND NEW.max_idr > OLD.max_idr
BEGIN
    SELECT RAISE(ABORT, 'episode spend authorization cap cannot be raised');
END;

CREATE TRIGGER spend_authorizations_episode_no_revive
BEFORE UPDATE OF status ON spend_authorizations
WHEN OLD.kind <> 'operational' AND OLD.status = 'revoked' AND NEW.status = 'active'
BEGIN
    SELECT RAISE(ABORT, 'revoked episode spend authorization cannot be revived');
END;

-- 5. Nilai uang di ledger & otorisasi wajib integer.
CREATE TRIGGER ledger_reserved_amounts_are_integers
BEFORE INSERT ON ledger_entries
WHEN typeof(NEW.reserved_idr) <> 'integer' OR typeof(NEW.reserved_usd_micros) <> 'integer'
BEGIN
    SELECT RAISE(ABORT, 'ledger amounts must be integers');
END;

CREATE TRIGGER ledger_actual_amounts_are_integers
BEFORE UPDATE OF actual_idr, actual_usd_micros ON ledger_entries
WHEN NEW.actual_idr IS NOT NULL
     AND (typeof(NEW.actual_idr) <> 'integer' OR typeof(NEW.actual_usd_micros) <> 'integer')
BEGIN
    SELECT RAISE(ABORT, 'ledger amounts must be integers');
END;

CREATE TRIGGER spend_authorizations_max_is_integer
BEFORE INSERT ON spend_authorizations
WHEN typeof(NEW.max_idr) <> 'integer'
BEGIN
    SELECT RAISE(ABORT, 'authorization cap must be an integer');
END;

-- 6. Entri ledger yang sudah selesai (committed/released) tidak bisa diubah lagi.
CREATE TRIGGER ledger_settled_is_final
BEFORE UPDATE ON ledger_entries
WHEN OLD.status <> 'reserved'
BEGIN
    SELECT RAISE(ABORT, 'settled ledger entry is final');
END;

CREATE TRIGGER ledger_no_delete
BEFORE DELETE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger entries cannot be deleted');
END;
