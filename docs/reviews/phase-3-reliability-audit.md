# Audit & Hotfix Reliability Fase 3 — Pemrosesan Update Telegram

| | |
|---|---|
| Tanggal | 2026-10-26 |
| Branch | `claude/phase-3-reliability` (basis: `claude/phase-3-telegram` @ `6455bb2`) |
| Status | Selesai, **menunggu persetujuan owner** |
| Cakupan | Hanya reliability pemrosesan update. Tanpa Fase 4, tanpa Hermes, tanpa API berbayar, tanpa deploy, tanpa perubahan budget. |
| Keputusan | [ADR-0013](../adr/0013-pemrosesan-update-tahan-crash.md) |

---

## 1. Akar Masalah

Temuan awal: `StudioBot.handle()` memanggil `UpdateLog.register()` **sebelum** handler berjalan dan balasan terkirim, jadi update dianggap selesai padahal belum.

Saat menelusuri `StudioBot.handle`, `UpdateLog`, `ConversationEngine`, `CoreRunner`, `NotificationDispatcher`, adapter/transport aiogram, dan migrasi `0005`, ternyata ada **lima** titik kegagalan:

| # | Titik kegagalan | Akibat sebelum hotfix |
|---|---|---|
| F1 | `register()` dicatat sebelum pemrosesan | Crash setelah register = update "sudah diproses", aksi owner **hilang**. |
| F2 | aiogram menjalankan handler sebagai task (`handle_as_tasks=True`) dan mengakui offset di `getUpdates` berikutnya, sebelum handler selesai | Telegram **tidak** mengirim ulang update yang hilang karena crash. Dedupe saja tidak bisa memulihkan; isi update tidak tersimpan di mana pun. |
| F3 | Satu update = beberapa transaksi terpisah (simpan state percakapan, hanguskan kode tombol, keputusan approval, enqueue job) | Crash di antaranya meninggalkan efek setengah jadi, misalnya kode tombol sudah hangus tapi approval belum diputuskan → owner harus membuka kartu baru. |
| F4 | Balasan hanya di memori (`Reply`) lalu langsung dikirim | Crash/putus jaringan setelah commit = balasan **hilang**; owner tidak tahu aksinya berhasil. |
| F5 | Duplikat callback dijawab `answer("")` dengan `callback_id` yang sama | Jawaban kedua bisa merebut slot jawaban milik pemrosesan asli, sehingga pop-up penolakan/peringatan tidak muncul. |

Titik lain yang diperiksa dan **sudah aman** sebelum hotfix:
- `ConversationEngine` & `StudioController` murni operasi database (tanpa I/O provider/Telegram), jadi aman dijalankan di dalam satu transaksi.
- `CoreRunner` menserialkan semua akses DB proses bot di satu thread; worker memakai koneksi sendiri.
- `NotificationDispatcher` sudah *at-least-once* per penerima (`delivered_to`). Kartu approval di notifikasi dibuat ulang saat dikirim, jadi retry tidak memakai kode basi.
- Transport aiogram sudah memetakan `retry_after`, timeout, jaringan, dan "diblokir" ke `TransportError`.

---

## 2. Perubahan Arsitektur

### 2.1 Lifecycle update yang persisten (`ui_inbox`, migrasi `0006`)

```
received ─claim─▶ processing ─commit─▶ committed ─semua balasan terkirim─▶ delivered
   ▲                  │
   └─release/backoff──┤ (error sementara, mis. SQLite busy)
                      └─ jatah percobaan habis ─▶ failed (+ pesan error, tanpa efek bisnis)
```

| Langkah | Transaksi | Isi |
|---|---|---|
| receive | singkat | `INSERT OR IGNORE` isi update + langsung diklaim (`lease_owner`, `lease_until`, `lease_token=1`). Update yang sudah ada hanya diklaim ulang kalau belum di-commit **dan** lease lamanya sudah habis. |
| commit | **satu** transaksi `BEGIN IMMEDIATE` | cek `status=processing` + owner + token → `ConversationEngine.handle()` (semua aksi bisnis) → status `committed` + baris balasan. Rollback = tidak ada efek apa pun. |
| flush | per baris | kirim balasan berurutan; tiap baris dicatat `sent` + `message_id` segera setelah berhasil. |
| recover | start + berkala | update `received/processing` yang lease-nya habis diproses ulang; balasan tertunda dikirim; `committed` yang balasannya habis → `delivered`. Allowlist & chat pribadi **dicek ulang**. |

Lapisan perlindungan dari efek ganda (dari dalam ke luar):
1. Trigger `ui_inbox_no_reprocess_after_commit`: update `committed/delivered/failed` tidak bisa kembali ke `received/processing`.
2. Trigger `ui_reply_outbox_requires_commit`: baris balasan hanya bisa lahir bersama commit.
3. Fencing: `owns()` di awal transaksi bisnis **dan** `UPDATE … WHERE status='processing' AND lease_owner=? AND lease_token=?` saat commit.
4. Lapisan yang sudah ada: kode tombol sekali pakai, approval version-aware, idempotency key job, BudgetGuard.

### 2.2 Reply outbox persisten (`ui_reply_outbox`)

- Satu baris = satu panggilan Bot API (`send` / `edit` / `edit_keyboard` / `answer`). Pesan > 4096 karakter sudah dipecah saat commit, jadi crash paling banyak mengulang satu panggilan.
- Baris diklaim dengan lease, jadi dua pemroses tidak mengirim baris yang sama bersamaan.
- Gagal sementara → backoff (menghormati `retry_after`), baris berikutnya **menunggu** supaya urutan pesan terjaga. Gagal permanen → `dead`, baris berikutnya lanjut.

### 2.3 File

| File | Perubahan |
|---|---|
| `src/studio/infra/db/migrations/0006_durable_updates.sql` | **baru**: `ui_inbox`, `ui_reply_outbox`, 2 trigger invarian; `ui_processed_updates` dihapus |
| `src/studio/modules/controller/inbox.py` | **baru**: `UpdateInbox`, `ReplyOutbox` |
| `src/studio/interfaces/telegram/processor.py` | **baru**: `UpdateProcessor` (receive → commit → flush → recover), serialisasi update/balasan, titik fault injection |
| `src/studio/interfaces/telegram/core.py` | **baru**: `CoreRunner` dipindah dari `bot.py` (menghindari import melingkar) |
| `src/studio/interfaces/telegram/bot.py` | gerbang keamanan tetap; dedupe lama diganti `UpdateProcessor`; duplikat callback tidak lagi dijawab |
| `src/studio/interfaces/telegram/runner.py` | pemulihan dijalankan **sebelum** polling dimulai + loop pemulihan berkala |
| `src/studio/interfaces/telegram/notifier.py` | pembersihan memakai `UpdateInbox.prune` |
| `src/studio/modules/controller/state.py`, `__init__.py`, `src/studio/bootstrap.py`, `src/studio/shared/config.py` | `UpdateLog` dihapus; `App.inbox`, `App.replies`; setting `STUDIO_UPDATE_LEASE_SECONDS` (30), `STUDIO_UPDATE_MAX_ATTEMPTS` (5) |
| `tests/telegram/test_crash_recovery.py` | **baru**: 18 test fault injection |
| `tests/telegram/fakes.py`, `tests/telegram/test_reliability.py` | harness memakai processor + `fault=`; 2 test diperbarui untuk lifecycle baru (§4.2) |
| Dokumen | ADR-0013 (baru), ADR-0012 (catatan), CLAUDE.md §3/§4.1/§7, ARCHITECTURE §5.1a & tabel, DEVELOPMENT_PLAN AC3.21–AC3.22, TELEGRAM_SETUP troubleshooting, `.env.example`, laporan ini |

---

## 3. Hasil Crash Recovery Tests

Semua dijalankan dengan `FakeTransport` + `FakeClock`. "Crash" = `SimulatedCrash` (BaseException, tidak tertangkap handler bot): transaksi terbuka di-rollback seperti SQLite saat proses mati, lalu bot di-restart (objek baru, database sama).

| # | Skenario (brief) | Test | Hasil yang dibuktikan |
|---|---|---|---|
| 1 | Crash setelah update diterima | `test_crash_before_commit_is_reprocessed_exactly_once[after_receive]` | Update tersimpan `processing`; belum diambil selama lease lama hidup; setelah lease habis diproses ulang → approval G1 diputuskan **sekali**, balasan terkirim, status `delivered`; pemulihan berikutnya tidak melakukan apa pun. |
| 2 | Crash sebelum business transaction commit | `test_crash_before_commit_is_reprocessed_exactly_once[before_commit]` | Rollback total (kode tombol belum hangus, approval masih pending, tidak ada baris balasan) → diproses ulang sekali. |
| 3 | Crash setelah commit, sebelum respons dikirim | `test_crash_after_commit_delivers_reply_without_rerunning_action` | Aksi sudah final; pemulihan hanya mengirim balasan; jumlah keputusan & job tidak bertambah. |
| 4 | Crash saat Telegram send berlangsung | `test_crash_during_send_resends_after_lease` | Baris balasan masih diklaim pemroses mati → dikirim setelah lease habis; satu kartu (satu grup kode). |
| 5 | Telegram menerima, crash sebelum acknowledgement tersimpan | `test_crash_after_telegram_accepted_send_may_duplicate_message_but_not_action`, `test_crash_after_telegram_accepted_edit_is_idempotent` | `sendMessage`: pesan **dobel** (batas Bot API, didokumentasikan), tapi isinya kartu yang sama (satu grup kode) → menekan "Ya" di kedua pesan hanya membuat **1** episode & **1** job. `editMessageText`: diulang ke pesan yang sama, tanpa pesan baru. |
| 6 | Duplicate update saat yang pertama masih diproses | `test_duplicate_update_while_first_is_processing` | Duplikat tidak memproses, tidak merebut lease (token tetap 1, attempts 1), dan **tidak** menjawab callback; keputusan sekali. |
| 7 | Restart dengan update berstatus PROCESSING | `test_restart_recovers_all_stuck_updates_in_order`, `test_recovery_rechecks_allowlist` | Dua update macet (teks + tombol) dipulihkan berurutan; owner yang dicabut dari allowlist sebelum restart → update ditutup `failed` tanpa balasan. |
| 8 | Callback approval dikirim ulang | `test_resent_approval_callback_never_decides_twice` | (a) dikirim ulang setelah `delivered` → tidak ada efek/balasan; (b) dikirim ulang saat `committed` tapi balasan tertunda → hanya balasan yang dikirim; (c) tombol lama ditekan lagi (update baru) → ditolak kode sekali pakai. |
| 9 | Dua worker memproses update yang sama | `test_stale_processor_cannot_commit_after_takeover`, `test_two_processes_receiving_same_update_concurrently`, `test_slow_handler_in_same_process_is_fenced_by_token` | Pemroses lama (token 1) yang bangun setelah diambil alih tidak commit & tidak mengirim apa pun; 4 proses (4 koneksi DB) bersamaan → tepat 1 keputusan & 1 jawaban callback; dalam proses yang sama, hanya token terbaru yang bisa commit. |
| 10 | SQLite busy/locked saat recovery | `test_sqlite_busy_during_recovery_is_retried` | Klaim gagal (busy) → tidak ada yang berubah; pemrosesan gagal (busy) → dilepas dengan backoff + `last_error`; percobaan berikutnya berhasil, keputusan sekali. |

Tambahan:

| Test | Hasil |
|---|---|
| `test_committed_update_can_never_be_reprocessed` | Trigger DB menolak `committed → processing` dan menolak baris balasan tanpa commit. |
| `test_reply_order_is_preserved_when_one_send_fails`, `test_failed_send_holds_back_later_messages` | Pesan kedua tidak pernah mendahului pesan pertama yang gagal; setelah pulih urutannya "satu, dua". |
| `test_crash_after_last_reply_before_delivered_is_settled` | Crash setelah balasan terakhir tercatat terkirim tapi sebelum `delivered` → pemulihan menuntaskan status **tanpa** mengirim ulang. |

### 3.1 Mutation check

Kontrol reliability dirusak satu per satu, lalu `tests/telegram` dijalankan:

| Mutasi | Hasil |
|---|---|
| Status `committed` ditulis di luar transaksi bisnis | tertangkap |
| Pemulihan tidak cek ulang allowlist | tertangkap |
| Duplikat `committed` tidak mengirim balasan tertunda | tertangkap |
| Baris balasan tidak dicatat terkirim | tertangkap |
| Error sementara langsung dianggap gagal final | tertangkap |
| Klaim ulang mengabaikan lease yang masih hidup | tertangkap (setelah test duplikat ditambah assert lease tidak direbut) |
| Gagal kirim tidak menahan urutan | tertangkap (setelah ditambah test dua pesan berurutan) |
| Pemulihan tidak menuntaskan `delivered` | tertangkap (setelah ditambah test crash sebelum `delivered`) |
| Cek `owns()` di awal transaksi dihapus | **tidak** tertangkap sendirian: lapis kedua (token di `UPDATE` commit) menolak dan seluruh transaksi di-rollback |
| Cek token di `UPDATE` commit dihapus | **tidak** tertangkap sendirian: lapis pertama (`owns()`) menolak |
| **Kedua** lapis fencing dihapus | tertangkap (`test_slow_handler_in_same_process_is_fenced_by_token`) |

Dua lapis fencing sengaja redundan: masing-masing menutupi yang lain.

---

## 4. Hasil Test & Quality Gates

### 4.1 Lokal

| Gate | Perintah | Hasil |
|---|---|---|
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 156 files already formatted |
| Typecheck | `uv run mypy` (strict) | no issues found in 95 source files |
| Batas modul | `uv run lint-imports` | 2 kept, 0 broken |
| Test (Python 3.12.3) | `uv run pytest -v` | **407 passed, 0 failed, 0 skipped, 0 error** |
| Test (Python 3.13) | `uv run --python 3.13 pytest -q` | 407 passed |
| Lockfile | `uv lock --check` | konsisten (tidak ada dependensi baru) |

407 = 389 test sebelumnya (semua tetap lulus) + 18 test crash recovery baru.

### 4.2 Test lama yang diperbarui

Dua test di `tests/telegram/test_reliability.py` mengunci perilaku lama "error → pesan error langsung":

| Sebelum | Sesudah | Alasan |
|---|---|---|
| `test_internal_errors_never_leak_details`: error tak terduga → `INTERNAL_ERROR` seketika | error → **tidak ada** yang di-commit, update `received` dengan backoff; setelah `STUDIO_UPDATE_MAX_ATTEMPTS` percobaan → `failed` + `INTERNAL_ERROR` (tetap tanpa detail internal) | aksi owner tidak boleh hilang karena error sementara |
| `test_sqlite_busy_gets_friendly_message_and_retry` → `test_sqlite_busy_is_retried_then_reported` | busy dicoba ulang otomatis; `DB_BUSY` hanya setelah jatah habis | sama |

Jaminan keamanannya tidak berubah (tidak ada traceback/detail internal ke user).

### 4.3 Security & regresi

Tetap utuh dan tetap dites: owner allowlist (dicek sebelum update disimpan, dan dicek **ulang** saat pemulihan), private chat, approval G0–G3 version-aware, kode tombol sekali pakai, BudgetGuard, lease fencing job, idempotency job, redaksi token. Update dari orang asing/grup tidak pernah disimpan ke `ui_inbox`. Titik fault injection hanya parameter konstruktor (default tidak melakukan apa pun); tidak membuka jalur otorisasi.

---

## 5. Hasil GitHub Actions

Run [#9 (id 40268224375)](https://github.com/welldan23/03am/actions/runs/40268224375), event `push`, commit `ad59990`. Dicek lewat GitHub API (daftar job + log).

| Job | Install (`uv sync --locked`) | Lint | Format | Typecheck | Batas modul | Test (offline) | Kesimpulan |
|---|---|---|---|---|---|---|---|
| `check (3.12)` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `407 passed in 34.36s` | **success** |
| `check (3.13)` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `407 passed in 29.50s` | **success** |

Satu-satunya warning: *"Node.js 20 is deprecated"* (TD-13), tidak menggagalkan build. Commit laporan ini (dokumen saja) memicu run CI baru; hasilnya dilaporkan di ringkasan akhir ke owner.

---

## 6. Keterbatasan Telegram Delivery yang Tersisa

| # | Keterbatasan | Dampak | Mitigasi |
|---|---|---|---|
| L1 | Bot API tidak punya idempotency key untuk `sendMessage`. Kalau Telegram sudah menerima pesan tapi proses mati sebelum `sent` + `message_id` tercatat, pesan dikirim lagi saat pemulihan. | Owner bisa melihat **pesan dobel** (jendela sempit: satu panggilan API). | Satu baris = satu panggilan API (jendela minimal). Pesan dobel berisi kartu dengan kode yang **sama**, jadi tombolnya tetap hanya berlaku sekali. Didokumentasikan di ADR-0013 & TELEGRAM_SETUP. |
| L2 | `answerCallbackQuery` hanya berlaku sebentar setelah tombol ditekan. | Kalau balasan baru terkirim setelah pemulihan, spinner tombol bisa sudah hilang tanpa pop-up. | Jawaban yang kedaluwarsa diabaikan (transport menelan error); hasil aksi tetap terlihat dari edit/pesan berikutnya. |
| L3 | Update yang hilang **sebelum** tersimpan di `ui_inbox` (crash di antara Telegram mengirim update dan `receive` commit) tidak bisa dipulihkan dari sisi bot. | Sangat jarang; owner perlu mengirim ulang. | `receive` adalah langkah pertama setelah cek keamanan. Kalau aiogram belum sempat mengakui offset, Telegram mengirim ulang update itu. |
| L4 | Notifikasi outbox (ADR-0012) tetap at-least-once per penerima. | Notifikasi bisa dobel setelah crash di jendela kirim → catat. | Sama dengan L1. Kartu approval di notifikasi dibuat ulang saat dikirim. |
| L5 | Error tak terduga yang berulang (bug) membuat update dicoba sampai `STUDIO_UPDATE_MAX_ATTEMPTS` kali (backoff sampai 60 detik) sebelum owner mendapat pesan error. | Owner menunggu beberapa puluh detik (backoff 1+2+4+8 detik + interval pemulihan) untuk pesan error. | Diterima: menukar kecepatan pesan error dengan tidak kehilangan aksi saat error sementara. |
| L6 | Isi pesan owner disimpan di `ui_inbox` sampai dibersihkan (30 hari, saat bot berjalan). | Data pesan owner di disk server. | Hanya owner yang tersimpan; folder data tidak di-commit; pembersihan harian. |

**Tidak ada klaim exactly-once delivery Telegram.** Yang exactly-once adalah efek bisnis.

---

## 7. Commit

| Commit | Isi |
|---|---|
| `ad59990` | Seluruh kode, test, dan dokumen hotfix (CI hijau, lihat §5) |
| commit berikutnya | Laporan ini dilengkapi hasil CI (dokumen saja) |

Branch: `claude/phase-3-reliability`. Belum ada PR dan belum di-merge; menunggu persetujuan owner.
