# Laporan Implementasi Fase 3 — Telegram Studio Bot

| | |
|---|---|
| Tanggal | 2026-10-25 |
| Branch | `claude/phase-3-telegram` (basis: `claude/phase-2-research` @ `51b5897`) |
| Status | Selesai, **menunggu persetujuan owner** sebelum Fase 4 |
| Biaya nyata | Rp0 — semua provider mock, tidak ada panggilan jaringan, tidak ada deploy |

Ringkasnya: 03:AM sekarang punya **satu bot Telegram privat** sebagai antarmuka utama. Owner bisa membuat dokumenter, memilih topik (G0), membaca ResearchBrief dan naskah per segmen, bertanya sumber klaim, melihat biaya & budget, meminta revisi naskah, dan memutuskan approval G0–G3 lewat tombol. Semua itu bisa lewat menu atau kalimat biasa. Bot hanya antarmuka: setiap keputusan diproses Studio Controller → workflow (state machine, approval version-aware, BudgetGuard), dan SQLite tetap sumber kebenaran.

---

## 1. Arsitektur Baru

```
Telegram ─▶ aiogram 3.31 (long polling) ─▶ adapter (Update → Inbound)
        ─▶ StudioBot: chat pribadi? → owner allowlist (from_user.id)? → dedupe update_id
        ─▶ CoreRunner (1 thread untuk semua akses DB dari proses bot)
        ─▶ ConversationEngine (sinkron, state percakapan di SQLite)
              ├─ teks   ─▶ IntentParser (aturan; port untuk Hermes Fase 5) ─▶ StudioController
              └─ tombol ─▶ callbacks (≤ 64 byte) ─▶ StudioController.press(kode sekali pakai)
        ─▶ Reply (send / edit / answer) ─▶ Transport aiogram (retry, rate limit) ─▶ Telegram

worker (thread/proses lain, koneksi DB sendiri) ─▶ kejadian di DB
        ─▶ trigger SQLite ─▶ notification_outbox ─▶ NotificationDispatcher ─▶ Telegram
```

Komponen ([ADR-0012](../adr/0012-antarmuka-telegram-dan-outbox.md)):

| Komponen | Lokasi | Peran |
|---|---|---|
| `StudioController` | `modules/controller/service.py` | Satu-satunya pintu antarmuka ke logika bisnis. **Setiap** metode memeriksa owner lagi. Membaca episode/riset/naskah/biaya/budget, menerbitkan kartu approval & konfirmasi, mengeksekusi tombol lewat `WorkflowService`. |
| `ActionCodes` | `modules/controller/actions.py` | Kode tombol sekali pakai (hash di server, terikat actor, kedaluwarsa, hangus per kartu). |
| `ConversationStore`, `UpdateLog` | `modules/controller/state.py` | State percakapan & dedupe update di SQLite (selamat dari restart). |
| `Outbox` | `modules/notifications` | Notifikasi persisten; baris dibuat **trigger DB** di transaksi kejadiannya. |
| `ConversationEngine` | `interfaces/telegram/engine.py` | Pesan/tombol → controller → layar. Tanpa aiogram, jadi dites offline. |
| `RuleBasedIntentParser` | `interfaces/telegram/intents.py` | Teks bebas → maksud + slot. Tidak pernah memutuskan; ambigu → slot kosong → bot bertanya. |
| `render`, `texts` | `interfaces/telegram/` | Layar HTML ber-escape, pagination, pemecah 4096 karakter, semua teks Indonesia di satu file. |
| `StudioBot`, `CoreRunner` | `interfaces/telegram/bot.py` | Gerbang keamanan + jembatan async → inti sinkron. |
| `AiogramTransport` | `interfaces/telegram/transport.py` | Kirim/edit/jawab dengan penanganan error Telegram. |
| `NotificationDispatcher` | `interfaces/telegram/notifier.py` | Kirim outbox di luar transaksi, `delivered_to` per penerima, backoff. |
| runner | `interfaces/telegram/runner.py` | Long polling, worker thread, kunci poller tunggal, shutdown rapi. |

Lapisan import-linter sekarang: `interfaces → bootstrap → controller → workflow → scripting → research → calls → {episodes | approvals | budget | artifacts | notifications} → audit → {infra | providers} → shared`.

Perubahan kecil di modul lama:
- `WorkflowService.retry(…, notes=, expected_version=)`: catatan revisi ikut ke job tahap; dipakai untuk revisi naskah yang gagal editorial gate.
- `shared/logging`: `SecretFilter` untuk log standar (aiogram/aiohttp) + `configure_logging(extra_secrets=…)` untuk token yang dibaca dari `.env`.
- `Settings`: `telegram_bot_token` (`SecretStr`), `telegram_owner_ids`, TTL tombol/langkah, interval notifikasi, opsi worker di proses bot.

### 1.1 Revisi naskah lewat workflow (bukan edit langsung)

| Kondisi episode | Jalur | Efek |
|---|---|---|
| `AWAITING_EDITORIAL` (G1 menunggu) | keputusan **REVISE** ke `SCRIPTING` | approval G1 (+ setelahnya) digantikan, versi episode naik, naskah ditulis ulang dengan catatan, editorial gate jalan lagi, kartu G1 baru |
| `FAILED` dari `SCRIPTING` | **RETRY** dengan catatan | tahap naskah diulang, editorial gate jalan lagi |
| status lain | ditolak dengan penjelasan | — |

Revisi dari teks bebas ("Naskahnya terlalu kaku…") selalu lewat **kartu konfirmasi**; revisi dari kartu approval lewat pilihan tahap lalu catatan.

---

## 2. Security Controls

| Kontrol | Implementasi | Bukti test |
|---|---|---|
| Allowlist owner | `STUDIO_OWNER_IDS=telegram:<id>`; identitas dari `from_user.id` numerik, username tidak dipakai | `test_identity_is_numeric_user_id_from_allowlist` |
| Non-owner tidak dapat data | ditolak sebelum menyentuh DB; satu balasan generik; audit `telegram.unauthorized` (dibatasi 1×/10 menit/akun) | `test_stranger_gets_nothing_and_is_audited`, `test_stranger_cannot_press_owner_buttons` |
| Cek owner berlapis | controller memeriksa owner di setiap metode; `ApprovalService` memeriksa lagi saat memutuskan | `test_controller_refuses_non_owner_reads_and_writes` |
| Chat pribadi saja | grup/supergroup/channel diabaikan; callback dari grup dijawab "bot privat" | `test_group_chats_are_ignored` |
| Callback tidak dipercaya | `a:<kode 13 karakter>` → mapping di server (hash saja); payload hanya ID; kode palsu/tidak dikenal ditolak & diaudit | `test_forged_callbacks_are_refused`, `test_every_button_fits_callback_limit_and_carries_no_secrets` |
| Sekali pakai, kedaluwarsa, terikat actor | `used_at` + UPDATE bersyarat per kartu; TTL ≤ masa approval; kode milik owner A tidak bisa dipakai owner B | `test_card_button_replay_is_refused`, `test_action_code_expires_after_ttl`, `test_action_codes_are_bound_to_the_owner_who_received_them` |
| Klik ganda / konkuren | kode dihanguskan (commit) sebelum aksi; 4 koneksi bersamaan → tepat 1 eksekusi | `test_concurrent_double_click_executes_once` |
| Update dikirim ulang | `ui_processed_updates` (dedupe `update_id`) | `test_duplicate_telegram_update_is_processed_once`, `test_resent_text_update_is_ignored` |
| Tombol lama setelah revisi | approval lama digantikan + versi/hash dicek `ApprovalService`; kartu baru menghanguskan kartu lama | `test_old_card_is_refused_after_content_is_revised` |
| Approval kedaluwarsa | ditolak; bot menawarkan terbit ulang (kartu konfirmasi) | `test_expired_approval_offers_reissue` |
| Tidak ada keputusan dari teks | "setujui saja" → daftar kartu; parser tidak menerima callback | `test_decisions_are_never_taken_from_free_text`, `test_callbacks_never_reach_the_text_intent_parser` |
| Token bot | hanya dari env/.env sebagai `SecretStr`; disensor di structlog & log standar (termasuk traceback) | `test_bot_token_never_appears_in_logs_or_repr` |
| Tanpa detail internal | error tak terduga → pesan umum; error domain di-escape HTML | `test_internal_errors_never_leak_details`, `test_user_text_cannot_inject_html` |
| Satu poller | kunci file `data/telegram-poller.lock` | `test_only_one_poller_per_data_dir` |
| Audit tindakan sensitif | `ui.action_used` / `ui.action_refused` + audit domain (`approval.decided` dengan actor `owner:telegram:<id>`, `episode.created`, `budget.period_activated`, …) | `test_g0_requires_owner_choice_via_card` |
| Tidak ada API berbayar | mock tetap default; `PAID_PROVIDERS_ENABLED=true` tetap ditolak; dashboard menampilkan "API berbayar: NONAKTIF" | `test_budget_dashboard_shows_plan_from_config` |

### 2.1 Mutation check

Kontrol keamanan sengaja dirusak satu per satu, lalu `tests/telegram` dijalankan:

| Mutasi | Hasil |
|---|---|
| Allowlist owner di bot dimatikan | tertangkap |
| Cek chat pribadi dimatikan | tertangkap |
| Dedupe `update_id` dimatikan | tertangkap (setelah ditambah test pesan teks yang dikirim ulang) |
| Kode tidak terikat actor | tertangkap |
| Kode tidak kedaluwarsa | tertangkap |
| Satu kartu tidak hangus bersamaan | tertangkap |
| Controller tanpa cek owner | tertangkap |
| Keputusan dari teks bebas diizinkan | tertangkap |
| Outbox mengirim ulang ke penerima yang sudah menerima | tertangkap |
| Kartu approval kedaluwarsa tetap diterbitkan | tertangkap |
| Escape HTML ringkasan konfirmasi dimatikan | tertangkap |
| Cek `used_at` dihapus | **tidak** tertangkap sendirian: replay tetap ditolak oleh lapisan kedua (UPDATE `… AND used_at IS NULL` + cek rowcount). Kalau dua lapis itu dihapus sekaligus, test gagal (approval sudah tidak pending). Ini pertahanan berlapis, bukan celah. |

---

## 3. File yang Dibuat & Diubah

45 file (31 baru, 14 diubah), +7.652 / −150 baris.

**Baru — kode**
- `src/studio/infra/db/migrations/0005_interface_outbox.sql`: tabel `ui_processed_updates`, `ui_action_codes`, `ui_conversations`, `notification_outbox` + trigger outbox dari `audit_log` & `jobs`.
- `src/studio/modules/controller/`: `__init__.py`, `actions.py`, `service.py`, `state.py`, `views.py`.
- `src/studio/modules/notifications/__init__.py`.
- `src/studio/interfaces/telegram/`: `__init__.py`, `adapter.py`, `bot.py`, `callbacks.py`, `engine.py`, `intents.py`, `notifier.py`, `render.py`, `runner.py`, `texts.py`, `transport.py`, `types.py`.

**Baru — test**: `tests/telegram/` → `__init__.py`, `conftest.py`, `fakes.py` (fake transport + `Harness`), `test_approvals.py`, `test_flow.py`, `test_intents.py`, `test_notifications.py`, `test_reliability.py`, `test_render.py`, `test_security.py`.

**Baru — dokumen**: `docs/TELEGRAM_SETUP.md`, `docs/adr/0012-antarmuka-telegram-dan-outbox.md`, laporan ini.

**Diubah**
- `pyproject.toml`, `uv.lock`: `aiogram>=3.31,<4` (memaksa pydantic 2.13.5 karena batas `<2.14` dari aiogram); lapisan `controller` & `notifications`; pytest `--allow-unix-socket` (socket Unix lokal untuk event loop asyncio; socket jaringan tetap diblokir).
- `src/studio/bootstrap.py`: merakit controller, action codes, state percakapan, update log, outbox.
- `src/studio/shared/config.py`, `src/studio/shared/logging.py`, `src/studio/modules/workflow/service.py` (lihat §1).
- `src/studio/interfaces/cli/main.py`: `studio bot check`, `studio bot run`, `studio worker run --loop`.
- `.env.example`, `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md` (v0.4), `docs/DEVELOPMENT_PLAN.md` (AC3.x + bukti), `docs/PRD.md` (FR-TG), `docs/adr/README.md`.

---

## 4. Hasil Test & Quality Gates (lokal)

| Gate | Perintah | Hasil |
|---|---|---|
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 150 files already formatted |
| Typecheck | `uv run mypy` (strict) | no issues found in 92 source files |
| Batas modul | `uv run lint-imports` | 2 kept, 0 broken |
| Test (Python 3.13) | `uv run pytest -v` | **389 passed, 0 failed, 0 skipped, 0 error** |
| Test (Python 3.12.3) | `uv run --python 3.12 pytest -q` | 389 passed |
| Lockfile | `uv lock --check` | konsisten |

389 = 287 regresi Fase 1–2 (semua tetap lulus) + 102 test baru di `tests/telegram/`:

| File | Kategori | Test |
|---|---|---|
| `test_intents.py` | conversation intent (unit) | 31 |
| `test_reliability.py` | reliability, transport aiogram, adapter, worker, poller | 17 |
| `test_approvals.py` | callback replay, klik ganda konkuren, kartu basi, kedaluwarsa, revisi, G2/G3 | 14 |
| `test_security.py` | authorization, chat pribadi, token di log, HTML injection | 12 |
| `test_flow.py` | integrasi end-to-end, review riset/naskah, pagination, ambiguitas | 10 |
| `test_render.py` | callback ≤ 64 byte, pemecahan 4096, pagination, budget display | 10 |
| `test_notifications.py` | outbox transaksional, restart recovery, retry_after, dead letter | 8 |

---

## 5. Hasil GitHub Actions

Run [#7 (id 40238535074)](https://github.com/welldan23/03am/actions/runs/40238535074), event `push`, commit `b702c18`. Dicek lewat GitHub API (daftar job + log), bukan asumsi.

| Job | Install (`uv sync --locked`) | Lint | Format | Typecheck | Batas modul | Test (offline) | Kesimpulan |
|---|---|---|---|---|---|---|---|
| `check (3.12)` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `389 passed in 32.11s` | **success** |
| `check (3.13)` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ `389 passed in 27.55s` | **success** |

Satu-satunya warning: *"Node.js 20 is deprecated"* untuk `actions/checkout@v4` dan `astral-sh/setup-uv@v6` (TD-13). Warning ini tidak menggagalkan build.

Commit laporan ini (hanya dokumen) memicu run CI baru; hasilnya dilaporkan di ringkasan akhir ke owner.

---

## 6. Contoh Transcript Percakapan Telegram

Dihasilkan dari bot asli (engine + controller + SQLite + mock provider) dengan fake transport. Versi lengkap ada di [TELEGRAM_SETUP.md §4](../TELEGRAM_SETUP.md#4-contoh-percakapan-end-to-end). 👤 = owner, 👆 = tombol, 🤖 = bot, `(edit)` = pesan tombol diperbarui.

```text
👤 /start

🤖 🌙 03:AM — AI Documentary Studio
   Halo! Saya asisten studio. Pilih menu di bawah atau ketik saja, misalnya:
   • Cari topik sejarah yang menarik
   • Buat dokumenter tentang Krakatau, format 90 detik
   • Tampilkan episode yang belum saya approve
   
   ⚠️ Fase 3: semua AI & biaya masih simulasi (mock). Tidak ada API berbayar.
   [🎬 Buat Dokumenter] [📂 Episode Aktif] [💡 Ide Topik] [🔎 Review Riset] [📝 Review Naskah] [✅ Approval] [⚙️ Status Produksi] [💰 Budget] [🛠 Pengaturan]

👤 Cari topik sejarah yang menarik.

🤖 🎬 🏛 Sejarah
   Pilih format dokumenter:
   [⚡ Quick Files (30–45 dtk)] [🗂 The Archives (75–90 dtk)] [🔬 Deep Files (120–180 dtk)] [Batal]

👤 Pilih format 90 detik.

🤖 ❓ Buat dokumenter ini?
   The Archives · 90 detik · kategori sejarah
   [✅ Ya, lanjutkan] [Batal]

👆 [Ya, lanjutkan]

🤖 (edit) ✅ Episode dibuat. Studio sedang mencari kandidat topik…
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …

🤖 💡 Topik siap dipilih. G0 menunggu approval Anda.
   🗳 G0 · Pilih topik
   Episode (belum berjudul) #QH8F8V · versi 3
   Batas belanja yang disetujui: Rp5.000 (simulasi)
   
   1. Dentuman Krakatau 1883
   fenomena_alam · sensitivitas rendah · keterverifikasian tinggi
   Bagaimana satu gunung di Selat Sunda bisa terdengar sampai tengah Samudra Hindia?
   2. Naskah Voynich: Buku yang Belum Bisa Dibaca
   misteri_sejarah · sensitivitas rendah · keterverifikasian sedang
   Apa yang kita ketahui pasti tentang naskah yang tak seorang pun bisa baca?
   3. Garis Tak Kasatmata di antara Bali dan Lombok
   geografi · sensitivitas rendah · keterverifikasian tinggi
   Mengapa hewan di dua pulau bertetangga bisa begitu berbeda?
   4. Banda dan Perebutan Pala
   sejarah_dunia · sensitivitas sedang · keterverifikasian sedang
   Mengapa segenggam pala pernah lebih berharga dari emas?
   5. Garis Laut di Natuna
   geopolitik · sensitivitas tinggi · keterverifikasian sedang
   Siapa yang menentukan di mana laut sebuah negara berakhir?
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ 1] [✅ 2] [✅ 3] [✅ 4] [✅ 5] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👆 [✅ 1]

🤖 (edit) ✅ Topik dipilih: Dentuman Krakatau 1883. Riset dimulai.
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …
   …
   Panggilan LLM tercatat: 15
   Estimasi produksi: belum dihitung (dibuat setelah G1 disetujui).
   
   ⚠️ Semua angka Fase 3 adalah biaya simulasi dari mock provider.
   [📁 Episode] [🏠 Menu]

👤 Naskahnya terlalu kaku, buat lebih natural.

🤖 ❓ Kirim revisi naskah?
   Revisi naskah — approval G1 yang menunggu akan dibatalkan, naskah ditulis ulang, lalu diperiksa editorial gate lagi.
   Catatan: Naskahnya terlalu kaku, buat lebih natural.
   Episode: Dentuman Krakatau 1883 #QH8F8V
   [✅ Ya, lanjutkan] [Batal]

👆 [Ya, lanjutkan]

🤖 (edit) ✅ Revisi naskah dikirim. Naskah ditulis ulang lalu dicek ulang.
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …

🤖 📝 Naskah selesai — Dentuman Krakatau 1883 #QH8F8V
   79.6 dtk · 194 kata. Menyiapkan kartu G1…
   [📝 Lihat naskah] [📁 Episode]

🤖 📝 Naskah siap direview. G1 menunggu approval Anda.
   🗳 G1 · Persetujuan editorial
   Episode Dentuman Krakatau 1883 #QH8F8V · versi 11
   Naskah: Dentuman yang Terdengar Ribuan Kilometer · 79.6 dtk (target 90) · editorial gate LULUS · 7 catatan
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ Approve] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👤 Tampilkan episode yang belum saya approve.

🤖 ✅ Menunggu keputusan Anda (1)
   • G1 · Persetujuan editorial — Dentuman Krakatau 1883 #QH8F8V
     kedaluwarsa 06 Nov 02:00 UTC
   [🗳 G1 · Dentuman Krakatau 1883] [🏠 Menu]

👤 setujui saja

🤖 🔒 Untuk keamanan, approval hanya bisa diputuskan lewat tombol di kartu approval. Ini daftar yang sedang menunggu:
   
   ✅ Menunggu keputusan Anda (1)
   • G1 · Persetujuan editorial — Dentuman Krakatau 1883 #QH8F8V
     kedaluwarsa 06 Nov 02:00 UTC
   [🗳 G1 · Dentuman Krakatau 1883] [🏠 Menu]

👆 [🗳 G1]

🤖 (edit) 🗳 G1 · Persetujuan editorial
   Episode Dentuman Krakatau 1883 #QH8F8V · versi 11
   Naskah: Dentuman yang Terdengar Ribuan Kilometer · 79.6 dtk (target 90) · editorial gate LULUS · 7 catatan
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ Approve] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👆 [Approve]

🤖 (edit) ✅ Disetujui. Episode → ESTIMATING_COST.
   [📁 Episode] [🏠 Menu]
```

---

## 7. Technical Debt yang Tersisa

| ID | Tingkat | Masalah | Kapan |
|---|---|---|---|
| TD-23 | Sedang | Intent router berbasis aturan: kosakata terbatas, belum tahan typo/bahasa campur. Sudah dipisah di balik port `IntentParser`. | Fase 5 (Hermes) |
| TD-24 | Sedang | G1 belum menampilkan jumlah shot dan belum melampirkan dokumen; G2/G3 masih placeholder berlabel simulasi (AC3.3b, AC2.6). | Fase 4 |
| TD-25 | Sedang | Mock LLM mengabaikan isi catatan revisi (TD-18): naskah revisi = naskah fixture yang sama, hanya `notes` yang berubah. | Fase 6 (LLM asli) |
| TD-26 | Rendah | Notifikasi *at-least-once*: bisa dobel kalau proses mati tepat setelah kirim sebelum dicatat. | Diterima |
| TD-27 | Rendah | Dedupe update *at-most-once*: kalau proses mati setelah update dicatat tapi sebelum diproses, update itu hilang (owner mengirim ulang). Aksi sensitif tetap aman karena kode sekali pakai. | Diterima |
| TD-28 | Rendah | Override editorial gate belum tersedia di Telegram (masih CLI) karena butuh alasan tertulis & pertimbangan; sengaja ditunda. | Keputusan owner |
| TD-29 | Rendah | Satu thread inti untuk semua akses DB bot: cukup untuk 1–2 owner, bukan untuk banyak pengguna. | Diterima |
| TD-30 | Rendah | Kunci poller tunggal pakai `fcntl` (Linux/macOS). Mode webhook belum dibuat. | Fase 7 (VPS) |
| TD-31 | Rendah | Pembatas log penolakan orang asing di memori (reset saat restart); pembersihan `ui_*` hanya saat bot berjalan. | Fase 7 |
| TD-32 | Rendah | Kartu approval baru menghanguskan langkah "menunggu catatan revisi" untuk approval yang sama (owner perlu memilih ulang target revisi). | Diterima |
| TD-33 | Rendah | Belum ada preferensi notifikasi per owner (mute, ringkasan harian FR-TG-08). | Fase 5/7 |
| TD-34 | Info | aiogram 3.31 membatasi pydantic `<2.14`, jadi pydantic turun dari 2.14.1 ke 2.13.5. Semua test tetap lulus. | Pantau rilis aiogram |
| TD-14 | Sedang | (dari Fase 2) retry setelah status `unknown` belum punya peringatan khusus; tombol "Ulangi" di Telegram memakai jalur retry yang sama. | Fase 6 |
| TD-13 | Rendah | Warning Node.js 20 di GitHub Actions. | Kapan saja |
| TD-12 | Info | Branch default GitHub masih `claude/planning-docs`. | Keputusan owner |

---

## 8. Commit

| Commit | Isi |
|---|---|
| `b702c18` | Seluruh kode, test, dan dokumen Fase 3 (CI hijau, lihat §5) |
| commit berikutnya | Laporan ini dilengkapi hasil CI (dokumen saja) |

Branch: `claude/phase-3-telegram`. Belum ada PR dan belum di-merge; menunggu persetujuan owner sebelum Fase 4.
