# ADR-0013 — Pemrosesan Update Telegram yang Tahan Crash

| | |
|---|---|
| Status | **Diterima** (2026-10-26) — memperbaiki ADR-0012 §4 |
| Implementasi | Hotfix reliability Fase 3 (migrasi `0006_durable_updates.sql`) |
| Terkait | ADR-0011 (job dua fase, fencing token) · ADR-0012 (antarmuka Telegram & outbox) |

## Konteks

Di Fase 3, `StudioBot.handle()` mencatat `update_id` sebagai "sudah diproses" **sebelum** handler berjalan dan sebelum balasan terkirim. Audit menemukan:

1. Crash setelah pencatatan tapi sebelum aksi bisnis → update dianggap selesai, aksinya hilang.
2. aiogram menjalankan handler sebagai task (`handle_as_tasks`) dan mengakui offset di polling berikutnya. Telegram **tidak akan** mengirim ulang update yang hilang karena crash, jadi dedupe saja tidak cukup: isi update harus disimpan sendiri.
3. Satu update bisa menghasilkan beberapa transaksi terpisah (state percakapan, kode tombol hangus, keputusan approval). Crash di antaranya meninggalkan efek setengah jadi (kode hangus tapi approval belum diputuskan).
4. Balasan hanya ada di memori; crash setelah commit = balasan hilang.
5. Duplikat callback dijawab dengan `callback_id` yang sama, yang bisa merebut slot jawaban pop-up milik pemrosesan asli.

## Keputusan

### 1. Inbox persisten dengan lifecycle eksplisit (`ui_inbox`)

```
received ─claim─▶ processing ─commit─▶ committed ─semua balasan terkirim─▶ delivered
   ▲                  │
   └─release/backoff──┤ (error sementara, mis. SQLite busy)
                      └─ jatah percobaan habis ─▶ failed (+ pesan error)
```

- **receive**: isi update (`Inbound`) disimpan dan langsung diklaim dalam satu transaksi singkat (`lease_owner`, `lease_until`, `lease_token`). Update yang sama datang lagi hanya diklaim ulang kalau **belum di-commit** dan lease sebelumnya sudah habis (pemrosesnya mati).
- **commit**: `ConversationEngine.handle()` (semua aksi bisnis) + status `committed` + baris balasan ditulis dalam **satu** transaksi `BEGIN IMMEDIATE`, diawali cek fencing token. Rollback = tidak ada efek bisnis, tidak ada balasan; update diproses ulang nanti. Commit = efek bisnis final.
- Trigger DB `ui_inbox_no_reprocess_after_commit` melarang update `committed/delivered/failed` kembali ke `received/processing`. Trigger `ui_reply_outbox_requires_commit` melarang baris balasan tanpa commit.
- Error sementara → `release` dengan backoff eksponensial; setelah `STUDIO_UPDATE_MAX_ATTEMPTS` → `failed` + pesan error ramah (tanpa efek bisnis).
- Saat pemulihan, allowlist owner & syarat chat pribadi **dicek ulang** dari isi update yang tersimpan.

### 2. Reply outbox persisten (`ui_reply_outbox`)

- Satu baris = **satu panggilan Bot API** (pesan > 4096 karakter sudah dipecah saat commit), urut per update (`seq`).
- Dikirim di luar transaksi; setiap baris dicatat `sent` (dengan `message_id`) segera setelah berhasil. Gagal sementara → dijadwal ulang dan baris berikutnya menunggu (urutan pesan terjaga); gagal permanen → `dead`, baris berikutnya lanjut.
- Baris diklaim dengan lease, jadi dua pemroses tidak mengirim baris yang sama bersamaan.

### 3. Pemulihan

`UpdateProcessor.recover()` berjalan saat bot start (sebelum polling) dan berkala: proses ulang update `received/processing` yang lease-nya habis, kirim balasan tertunda, dan tuntaskan `committed` yang balasannya sudah habis terkirim.

### 4. Semantik yang dijanjikan

| Lapisan | Jaminan | Mekanisme |
|---|---|---|
| Aksi bisnis (approval, job, belanja, kode tombol) | **exactly-once efek** | satu transaksi + fencing token + trigger no-reprocess, ditambah lapisan yang sudah ada: kode tombol sekali pakai, approval version-aware, idempotency key job, BudgetGuard |
| Pengiriman Telegram | **at-least-once** dengan dedupe per baris | outbox + `sent` per panggilan API |

Bot API tidak punya idempotency key untuk `sendMessage`. Kalau Telegram sudah menerima pesan tapi proses mati sebelum `sent` (dan `message_id`) tercatat, pesan itu **dikirim lagi** saat pemulihan: owner bisa melihat pesan dobel. Pesan dobel berisi kartu dengan kode tombol yang sama (bukan kartu baru), jadi menekan tombol di salah satunya tetap hanya berlaku sekali. `editMessageText`, `editMessageReplyMarkup`, dan `answerCallbackQuery` aman diulang (hasil sama / ditolak tanpa efek).

## Konsekuensi

- (+) Tidak ada aksi yang hilang karena crash/restart, dan tidak ada aksi yang terjadi dua kali.
- (+) SQLite busy tidak lagi langsung menggagalkan aksi owner; dicoba ulang otomatis.
- (−) Transaksi bisnis mencakup seluruh `ConversationEngine.handle()`. Engine harus tetap bebas I/O (sudah dijaga: tidak ada panggilan provider/Telegram di dalamnya).
- (−) Pesan dobel tetap mungkin di satu jendela sempit (lihat §4). Didokumentasikan, tidak bisa dihilangkan tanpa dukungan API.
- (−) Isi pesan owner disimpan di `ui_inbox` sampai dibersihkan (30 hari).
