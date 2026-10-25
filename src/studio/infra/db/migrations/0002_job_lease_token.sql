-- 0002: fencing token untuk lease job.
-- Naik +1 setiap kali job diklaim. complete/fail wajib membawa token yang sama, jadi worker
-- lama (termasuk worker yang di-restart dengan ID sama) tidak bisa menyelesaikan job yang
-- sudah diklaim ulang.
ALTER TABLE jobs ADD COLUMN lease_token INTEGER NOT NULL DEFAULT 0;
