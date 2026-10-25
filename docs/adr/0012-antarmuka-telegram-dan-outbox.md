# ADR-0012 — Antarmuka Telegram: Studio Controller, Kode Tombol Sekali Pakai, Outbox Notifikasi

| | |
|---|---|
| Status | **Diterima** (2026-10-25) |
| Implementasi | Fase 3 |
| Terkait | ADR-0003 (approval di luar LLM) · ADR-0005 (satu bot) · ADR-0011 (job dua fase) |

## Konteks

Fase 3 menambah bot Telegram sebagai antarmuka utama. Risikonya:

1. bot menjadi "sumber kebenaran kedua" atau punya jalur pintas ke logika bisnis;
2. callback Telegram dipalsukan, diputar ulang, atau ditekan ganda;
3. notifikasi hilang saat bot restart, atau dikirim dari dalam transaksi database;
4. Hermes (Fase 5) harus bisa menggantikan pemahaman teks tanpa menyentuh keamanan.

## Keputusan

### 1. Studio Controller sebagai satu-satunya pintu

`studio.modules.controller.StudioController` berada di lapisan di atas `workflow` (dicek import-linter). Antarmuka (Telegram sekarang, Hermes nanti) hanya memanggil controller:

- setiap metode baca/tulis memeriksa ulang `actor` adalah owner di allowlist (bukan hanya di bot);
- semua perubahan state lewat `WorkflowService` (state machine, approval version-aware, BudgetGuard). Revisi naskah memakai keputusan REVISE di G1 atau RETRY dari FAILED, jadi approval lama digantikan, versi episode naik, dan editorial gate dijalankan ulang;
- identitas Telegram = `Actor.owner("telegram:<from_user.id>")`. Username tidak pernah dipakai.

### 2. Kode tombol sekali pakai di server (`ui_action_codes`)

- `callback_data` aksi = `a:<kode>` (13 karakter acak base32, 64 bit). Hanya **hash** kode yang disimpan. Payload (approval mana, keputusan apa) ada di server dan hanya berisi ID, tanpa rahasia.
- Kode terikat ke actor penerima, punya masa berlaku (`STUDIO_ACTION_TTL_MINUTES`, tidak pernah melebihi masa approval), dan dikelompokkan per kartu. Memakai satu kode menghanguskan seluruh kartu dalam satu UPDATE bersyarat (`used_at IS NULL`). Membuka kartu baru untuk approval yang sama menghanguskan kartu lama milik actor itu.
- Callback navigasi (`m:`, `e:`, `r:`, `s:` …) hanya membawa ID publik (ULID) dan tetap diproses hanya untuk owner. Semua `callback_data` dicek ≤ 64 byte saat dibuat.
- Kode dihanguskan (commit) **sebelum** aksinya dijalankan, jadi klik ganda dari banyak koneksi hanya mengeksekusi satu kali. Keputusan tetap divalidasi `ApprovalService` (pending, kedaluwarsa, versi, hash subjek).
- Token approval Fase 1 (`issue_token`) tidak dipakai Telegram: dengan lebih dari satu owner, token per approval akan saling menimpa antar-kartu. Kode per actor menggantikan perannya.

### 3. Outbox notifikasi lewat trigger database (`notification_outbox`)

- Trigger `AFTER INSERT ON audit_log` (approval diminta, riset dimulai, brief selesai, naskah selesai, episode gagal/selesai/ditutup) dan `AFTER UPDATE OF status ON jobs` (job dijadwalkan ulang) menulis baris outbox **di transaksi kejadiannya**. Rollback = tidak ada notifikasi; commit = notifikasi pasti ada. Logika bisnis tidak perlu diubah.
- Dispatcher mengklaim baris dengan lease, mengirim **di luar transaksi**, mencatat setiap penerima yang sudah menerima (`delivered_to`), lalu menandai `sent`. Gagal sementara → backoff (menghormati `retry_after` Telegram); gagal permanen → `dead`.
- Jaminannya *at-least-once* per penerima. Duplikat hanya mungkin kalau proses mati tepat di antara "terkirim" dan "dicatat terkirim".
- Dispatcher bangun saat ada aktivitas (aksi bot, job selesai di worker yang sama) atau saat notifikasi tertunda jatuh tempo; selain itu cek setiap `STUDIO_NOTIFY_IDLE_SECONDS`. Tidak ada polling agresif.

### 4. Conversation layer terpisah dari business logic

- `ConversationEngine` (sinkron, tanpa aiogram) memetakan pesan/tombol → controller → layar. State percakapan ada di SQLite (`ui_conversations`), update yang sudah diproses di `ui_processed_updates`.
- Pemahaman teks lewat port `IntentParser`. Fase 3 memakai `RuleBasedIntentParser` (deterministik). Parser **tidak pernah** menerima callback dan tidak bisa menghasilkan keputusan approval; "setujui saja" dijawab dengan daftar kartu. Hermes (Fase 5) dapat mengganti/melengkapi parser tanpa mengubah engine maupun controller.
- Proses bot memakai satu thread inti untuk semua akses database (koneksi SQLite tidak thread-safe). Worker job berjalan di thread/proses lain dengan koneksinya sendiri.

## Konsekuensi

- (+) Tidak ada jalur dari Telegram ke state yang melewati state machine, approval, atau BudgetGuard.
- (+) Replay, klik ganda, update yang dikirim ulang, dan tombol kartu lama tidak punya efek.
- (+) Notifikasi selamat dari restart tanpa logika "kirim lalu commit" yang rapuh.
- (−) Trigger outbox menghubungkan tabel lintas modul (seperti trigger 0003, TD-08). Mengubah nama aksi audit `episode.transition` / `approval.requested` harus ikut memperbarui migrasi outbox.
- (−) Jaminan at-least-once: owner bisa (jarang) menerima notifikasi ganda setelah crash.
- (−) `fcntl` (kunci poller tunggal) hanya tersedia di Linux/macOS; target deploy memang Linux.
