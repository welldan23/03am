# ADR-0011 — Eksekusi Job Dua Fase & Catatan Panggilan Provider

| | |
|---|---|
| Status | **Diterima** (2026-10-25) |
| Implementasi | Fase 2 (menyelesaikan TD-01 dari audit Fase 1) |
| Terkait | ADR-0008 (antrean SQLite) · ADR-0009 (metering token) · ADR-0010 (otorisasi belanja) |

## Konteks

Di Fase 1, handler job berjalan **di dalam** transaksi `BEGIN IMMEDIATE` yang sama dengan penandaan job selesai. Itu aman untuk placeholder yang cepat, tapi untuk panggilan LLM/provider ada tiga masalah:

1. Selama provider dipanggil (detik sampai menit), semua penulis SQLite lain menunggu.
2. Kalau transaksi di-rollback setelah provider sudah menagih, catatan biayanya ikut hilang.
3. Kalau job diulang (crash, lease habis), panggilan berbayar terulang secara buta.

## Keputusan

### 1. Handler di luar transaksi, hasil lewat `Lease.finish`

- Signature handler: `Handler = Callable[[Job, Lease], JobOutcome]`. Worker **tidak** membuka transaksi untuk handler.
- `Lease.finish(work)` = satu transaksi singkat: `work()` menulis hasil, lalu `queue.complete` dengan cek fencing token + masa lease. Lease hilang → seluruh tulisan di-rollback (`LeaseLostError`).
- `Lease.heartbeat()` memperpanjang lease di antara langkah panjang; `Lease.require_outside_transaction()` menolak I/O yang tidak sengaja dipanggil di dalam transaksi.
- Handler yang hanya menulis DB cukup dibungkus `atomic(fn)`.
- Handler wajib memanggil `finish` (atau mengembalikan `OBSOLETE`); kalau tidak, worker menganggapnya bug (`JobExecutionError`).

### 2. Setiap panggilan provider punya baris `provider_calls`

`MeteredCaller.call` menjalankan empat langkah:

| Langkah | Transaksi | Isi |
|---|---|---|
| 1 | singkat | heartbeat; cari baris berdasarkan `idempotency_key`. `succeeded` → respons dipakai ulang (tanpa biaya). `unknown` → ditolak. `in_flight` (worker mati di tengah) → ditandai `unknown`, biaya di-commit sebesar reservasi, tidak diulang — kecuali provider menyatakan `idempotent_replay`. `failed` → attempt baru. |
| 2 | sendiri | `BudgetGuard.reserve` (penolakan tetap teraudit), lalu insert `in_flight` dengan estimasi token/biaya, otorisasi, dan ledger entry. |
| 3 | **tanpa transaksi** | panggil provider dengan `SpendTicket` (HMAC atas fingerprint request + ledger + otorisasi). Mock menolak panggilan tanpa tiket sah. |
| 4 | singkat | cek baris masih `in_flight` dengan attempt yang sama (kalau tidak: worker basi → `LeaseLostError`), lalu `guard.commit` biaya aktual + `settle`. |

- Timeout setelah terkirim → `unknown`, commit sebesar reservasi (provider mungkin tetap menagih), **tidak** di-retry otomatis.
- Provider tidak tersedia / menolak → `failed` + reservasi di-release. Yang retryable diulang lewat retry job biasa.
- Key berbentuk `stage:<episode>:<status>:<versi>:<task>:<sub>`, jadi job yang diulang memakai hasil yang sama, sedangkan revisi (versi baru) menghasilkan panggilan baru.
- Trigger DB: baris `succeeded`/`unknown` final, baris tidak bisa dihapus.

### 3. Hasil tahap diterima hanya kalau episode belum berubah

Tahap konten berjalan di luar transaksi lewat `ContentStages`. Hasilnya ditulis di `WorkflowService._accept` (di dalam `finish`), yang memeriksa ulang status + versi episode. Episode sudah direvisi/dibatalkan → job `OBSOLETE`, hasil dibuang (biaya tetap tercatat di ledger).

## Konsekuensi

- (+) Tidak ada write lock selama I/O. Biaya yang sudah ditagih tidak pernah hilang dari ledger.
- (+) Crash di titik mana pun tidak menyebabkan bayar dua kali: hasil sukses dipakai ulang, hasil tak jelas berhenti untuk diputuskan owner.
- (+) Worker basi tertolak berlapis: cek baris `in_flight`/attempt, `LedgerStateError` dari guard, rowcount `settle`, dan fencing token di `complete`.
- (−) Status `unknown` butuh tindakan owner. Fase 2 belum punya perintah khusus untuk itu (lihat technical debt di `docs/reviews/phase-2-implementation.md`).
- (−) Panggilan provider yang lebih lama dari lease belum mengirim heartbeat dari dalam panggilan; timeout provider harus lebih pendek dari lease.
