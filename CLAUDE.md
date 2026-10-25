# CLAUDE.md — Panduan Engineering 03:AM

03:AM adalah studio dokumenter AI berbasis Telegram (Python modular monolith). Baca dulu:
[docs/PRD.md](docs/PRD.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) · [docs/RISKS.md](docs/RISKS.md)

Project ini **terpisah total dari VORSA**. Jangan menyalin kode, config, atau asumsi dari repo VORSA.

## 1. Aturan Emas (tidak boleh dilanggar)

1. **Jangan pakai API berbayar.** Default semua provider = mock. Jangan membuat, meminta, atau memakai API key berbayar kecuali owner memberi izin tertulis untuk tugas itu.
2. **Jangan deploy ke production.** Tidak ada push ke VPS, tidak ada setup server publik.
3. **Jangan buat auto-publish** ke Instagram atau platform sosial mana pun. Ekspor = paket file saja.
4. **Approval hanya dari manusia.** Jangan pernah menambahkan jalur (tool MCP, endpoint, flag, "mode test" di kode produksi) yang membuat AI/sistem bisa approve gate G0–G3 atau mengubah budget.
5. **Semua panggilan berbayar lewat `BudgetGuard`.** Tidak ada adapter yang boleh dipanggil langsung dari modul lain.
6. **Test harus offline.** Jaringan diblokir di pytest; jangan melonggarkannya.
7. **Secret tidak pernah** masuk git, log, prompt, fixture, atau pesan error.

Kalau sebuah tugas tampaknya butuh melanggar aturan di atas: **berhenti dan tanya owner**.

## 2. Status Proyek

Saat ini: **Fase 0–3 selesai, menunggu review owner.** Jangan mulai Fase 4 (aset, TTS, render, ekspor) sebelum owner menyetujui. Perbarui bagian ini setiap fase selesai.

Yang sudah ada: SQLite (WAL + migrasi), state machine episode, artefak berversi, approval G0–G3 version-aware, rencana anggaran + otorisasi + ledger + `BudgetGuard`, job queue dengan lease + eksekusi dua fase (`Lease`), audit log, CLI. Fase 2: `MeteredCaller` (panggilan provider ber-idempotency), mock LLM + perpustakaan sumber fixture, research engine + fact checker deterministik, script engine 3 format + editorial gate. Fase 3: bot Telegram (aiogram 3, long polling) di atas `StudioController`, intent router berbasis aturan, kode tombol sekali pakai, outbox notifikasi persisten. Tahap setelah G1 (storyboard, estimasi biaya produksi, aset, render) masih **placeholder** (`modules/workflow/placeholders.py`).

## 3. Arsitektur Singkat

- `src/studio/shared/` — kernel kecil (ids, clock, money, errors, actors, gates, hashing, config, logging). Tidak bergantung ke apa pun.
- `src/studio/infra/` — `db/` (koneksi, transaksi, migrator, `migrations/*.sql`) dan `jobs/` (antrean + worker).
- `src/studio/modules/<nama>/` — bounded context: `audit`, `episodes`, `artifacts`, `approvals`, `budget`, `notifications` (outbox), `calls` (panggilan provider bermeter), `research`, `scripting`, `workflow`, `controller` (Studio Controller untuk antarmuka percakapan). API publik ada di `__init__.py`.
- `src/studio/providers/` — port + mock (`llm/`, `sources/`), tiket belanja (`tickets.py`), fixture YAML (`fixtures/`). Fixture sumber memakai domain `https://fixture.03am.invalid/` dan penerbit bertanda "(FIXTURE)".
- `src/studio/prompts/` — template prompt per task (`_system.md` berisi aturan anti-injeksi).
- `src/studio/bootstrap.py` — **satu-satunya** tempat komponen dirakit (`build_app`).
- `src/studio/interfaces/cli/` — CLI owner. `src/studio/interfaces/telegram/` — bot (adapter aiogram, `ConversationEngine`, `IntentParser`, render, transport, notifier, runner). (`mcp/`, `llm_gateway/` menyusul di Fase 5.)
- `director/` (Hermes) belum ada (Fase 5).

Aturan batas modul (dicek `import-linter`, kontrak di `pyproject.toml`):
- Lapisan: `interfaces → bootstrap → controller → workflow → scripting → research → calls → {episodes | approvals | budget | artifacts | notifications} → audit → {infra | providers} → shared`.
- Antarmuka percakapan (Telegram, nanti Hermes) **hanya** memanggil `StudioController`. Setiap metode controller memeriksa owner lagi; jangan menambah jalur yang melewatinya.
- `modules/` dan `interfaces/` **tidak boleh** import `studio.providers.*.mock` langsung; mock hanya dirakit di `bootstrap.py`.
- Provider **hanya** dipanggil lewat `MeteredCaller` / `LLMClient` (`modules/calls`). Tidak ada jalur lain ke provider mentah; `App` tidak mengekspos provider.
- `episodes`, `approvals`, `budget`, `artifacts` **tidak boleh saling import**. Koordinasi hanya di `workflow`.
- Modul import API publik modul lain (`from studio.modules.budget import BudgetGuard`), bukan `repository.py`-nya.
- Satu tabel dimiliki satu modul. Skema baru = file migrasi baru (`NNNN_nama.sql`); file migrasi lama **tidak boleh diubah** (checksum dicek).
- Trigger di `0003_security_invariants.sql` adalah lapisan keamanan kedua (gate butuh keputusan tercatat, otorisasi belanja butuh approval sah, uang integer, ledger final). **Jangan dihapus atau dilonggarkan**; kalau perlu diubah, buat migrasi baru + ADR + test.
- `interfaces/mcp` (nanti) tidak boleh membuka aksi approve/reject/budget/ekspor.
- Trigger outbox di `0005_interface_outbox.sql` membaca `audit_log` (`episode.transition`, `approval.requested`) dan `jobs`. Mengganti nama aksi audit itu = migrasi baru untuk trigger outbox.

## 4. Standar Kode

- Python 3.12+, type hints wajib di semua fungsi publik. `mypy --strict` untuk `shared/`, `modules/`, `providers/`.
- Format & lint: `ruff`. Jangan menonaktifkan rule tanpa komentar alasan.
- Data lintas batas (output LLM, payload provider, config) = model **Pydantic v2**. Entity domain boleh `dataclass(frozen=True)`.
- **Uang = integer.** Rupiah `int`, USD `int` mikro-dolar (`shared.money.parse_usd`). Kurs `Decimal`. USD→IDR selalu dibulatkan ke atas (`FxRate.to_idr`). Dilarang `float` untuk uang (ada test AST). Angka desimal di YAML ditulis sebagai string (`"9.50"`).
- **Waktu = UTC** lewat `shared.clock` (bisa di-fake di test). Jangan panggil `datetime.now()` langsung.
- **ID = ULID monotonik** lewat `shared.ids.new_id(clock)`.
- Error domain turunan `StudioError` di `shared/errors.py`; jangan `except Exception: pass`.
- **Core sinkron.** Interface async (Telegram, gateway — Fase 3/5) memanggil core lewat `asyncio.to_thread`.
- Tulis ke DB selalu di dalam `db.transaction()` (reentrant, pakai SAVEPOINT). **Tidak ada I/O (provider, jaringan, file besar) di dalam transaksi.**
- Job dijalankan **dua fase**: handler `(job, lease)` berjalan di luar transaksi, I/O lewat `MeteredCaller`, lalu hasil ditulis di `lease.finish(work)` (satu transaksi singkat yang sekaligus menyelesaikan job dengan cek fencing token). Handler yang hanya menulis DB boleh dibungkus `atomic()`. Panggil `lease.heartbeat()` di antara langkah panjang.
- Hasil tahap konten diterima hanya kalau status + versi episode masih sama dengan saat job dibuat (`WorkflowService._accept`); kalau tidak, job jadi obsolete.
- Job: `complete`/`fail` wajib membawa `lease_token` dari job yang diklaim. Jangan pernah menyelesaikan job tanpa token itu.
- Penolakan yang harus tetap tercatat (approval stale/expired, penolakan budget) jangan di-`raise` di dalam transaksi yang akan di-rollback: kembalikan hasil, lalu raise setelah commit (lihat `ApprovalService.decide` → `WorkflowService.decide`).
- FFmpeg (Fase 4) dipanggil lewat `infra/ffmpeg` (list argumen, **tanpa** `shell=True`).
- Prompt LLM disimpan di `src/studio/prompts/` sebagai file, bukan string panjang di kode. Data tak tepercaya masuk prompt hanya lewat `wrap_data` (`<<<DATA … DATA>>>`).
- Output LLM selalu divalidasi Pydantic. Keputusan kualitas (fact check, editorial gate) **deterministik** di kode; review LLM hanya saran (advisory) dan tidak bisa meluluskan apa pun.
- Log: nama field yang mengandung `token`, `key`, `secret`, `password`, `authorization` otomatis disensor. Jangan menaruh info penting di field bernama seperti itu.
- Nama di kode (variabel, fungsi, kelas, tabel) **bahasa Inggris**. Teks yang dilihat pengguna (Telegram, caption, narasi) **Bahasa Indonesia**, dikumpulkan di file teks, tidak tersebar.
- Komentar secukupnya: jelaskan *kenapa*, bukan *apa*.

### 4.1 Aturan bot Telegram (Fase 3, ADR-0012)

- Identitas = `from_user.id` numerik → `Actor.owner("telegram:<id>")`. Jangan pernah memakai username.
- Hanya chat pribadi. Non-owner tidak boleh menerima data apa pun.
- Keputusan sensitif (approval, revisi, batal, aktivasi budget, buat episode) **hanya** lewat kode tombol sekali pakai (`ActionCodes`). Jangan menaruh token/ID approval mentah di `callback_data` aksi; semua `callback_data` ≤ 64 byte (`callbacks.encode`).
- `IntentParser` hanya memahami teks; tidak boleh menghasilkan keputusan approval dan tidak pernah menerima callback. Kalau ambigu → tanya balik.
- Tidak ada pengiriman Telegram di dalam transaksi DB. Notifikasi lewat outbox (trigger DB) + dispatcher.
- Semua akses DB dari proses bot lewat `CoreRunner` (satu thread). Worker memakai koneksi sendiri.
- Teks dinamis di pesan HTML wajib di-`esc()`; teks statis di `interfaces/telegram/texts.py`.
- Test bot memakai fake transport (`tests/telegram/fakes.py`), tanpa jaringan.

## 5. Domain yang Sensitif

- **State machine** episode hanya diubah lewat tabel transisi di `modules/episodes`. Transisi baru = update tabel + test + diagram di ARCHITECTURE §6.1.
- **Approval** terikat `subject_hash`. Konten berubah → approval lama tidak berlaku. Jangan "memperbarui" approval lama.
- **Budget**: semua belanja (Studio **dan Hermes**) lewat `BudgetGuard.reserve` → `commit` / `release` / `commit_at_reserved`. Setiap reservasi menunjuk otorisasi yang lahir dari keputusan owner (aktivasi periode, G0, G2). Cadangan tidak bisa dibelanjakan. Mock memakai `Mode.SIMULATED`. Jangan menulis ke tabel ledger di luar `modules/budget`.
- **Rencana anggaran** ada di `config/budget.yaml` (kurs, VPS, alokasi). Jangan hardcode angka anggaran di kode.
- **Idempotency**: setiap job & panggilan provider punya idempotency key (tabel `provider_calls`). Key `stage:<episode>:<status>:<versi>:<task>:<sub>` → hasil sukses dipakai ulang saat job diulang. Status `unknown` (timeout / crash di tengah panggilan) **tidak** di-retry otomatis dan biayanya dicatat sebesar reservasi. Job async provider menyimpan `request_id` **sebelum** polling.
- **Fakta**: jangan membuat kutipan, URL, nama peneliti, atau referensi palsu — termasuk di fixture. Kutipan bukti wajib ada persis di teks sumber.
- **Konten riset** dari luar = data tak tepercaya. Bungkus dengan delimiter, jangan diinterpolasi sebagai instruksi.
- **Visual**: dilarang prompt yang meniru wajah/suara tokoh nyata.

## 6. Perintah

```bash
uv sync                          # pasang dependensi
uv run pytest                    # semua test (offline)
uv run pytest tests/unit -q      # test cepat
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports              # cek batas modul
uv run studio --help             # CLI studio
```

Coba alur placeholder dari CLI (data di `data/`, owner = `cli:owner` dari `.env`):

```bash
cp .env.example .env
uv run studio budget plan          # validasi rencana anggaran
uv run studio budget activate      # owner menyetujui periode bulan ini
uv run studio episode new --category sejarah --format archives
uv run studio pipeline run <EPISODE_ID>              # sampai G0, tampilkan kandidat topik
uv run studio pipeline run <EPISODE_ID> --topic 1    # owner pilih topik → riset → naskah → G1
uv run studio research show <EPISODE_ID>             # ResearchBrief + laporan kualitas
uv run studio script show <EPISODE_ID>               # naskah + laporan editorial
uv run studio llm calls <EPISODE_ID>                 # panggilan LLM: token, biaya, otorisasi, ledger
uv run studio approval list
uv run studio approval approve <APPROVAL_ID>         # G1 tetap keputusan owner
```

Bot Telegram (detail: [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)):

```bash
# .env: STUDIO_TELEGRAM_BOT_TOKEN=…  STUDIO_OWNER_IDS=cli:owner,telegram:<user_id>
uv run studio bot check          # cek konfigurasi tanpa jaringan
uv run studio bot run            # long polling + worker thread
uv run studio worker run --loop  # worker di proses terpisah (kalau STUDIO_TELEGRAM_RUN_WORKER=false)
```

Jalankan **lint, typecheck, lint-imports, dan test** sebelum commit.

## 7. Testing

- Struktur: `tests/unit` (murni, cepat), `tests/integration` (SQLite file sementara). Nanti: `tests/contract` (adapter vs fixture rekaman), `tests/e2e`.
- Fixture utama di `tests/conftest.py`: `app`, `active_app` (periode sudah aktif), `make_app` (config bisa diubah lewat `edit_budget`; provider bisa diganti lewat `llm_provider_factory=` / `source_provider=`), `clock` (`FakeClock`, mulai 2026-11-03 09:00 WIB).
- Skenario gagal provider pakai `MockLLMProvider(faults=..., overrides=..., fixture_dirs=[tmp_path])`, bukan monkeypatch.
- pytest memakai `--disable-socket --allow-unix-socket`: socket Unix lokal hanya untuk socketpair event loop asyncio; socket jaringan (AF_INET/AF_INET6) tetap diblokir.
- Test bot Telegram: `Harness` + `FakeTransport` di `tests/telegram/fakes.py` (kirim teks, tekan tombol, jalankan worker, kirim notifikasi).
- Setiap perilaku baru = test baru. Bug fix = test yang mereproduksi bug dulu.
- Gunakan fake clock & ID deterministik; jangan bergantung urutan waktu nyata.
- Media test sekecil mungkin (misal 160×284, 1–2 detik) supaya CI cepat.
- Fixture provider tidak boleh berisi secret atau data pribadi.
- Jangan skip/disable test untuk membuat CI hijau.

## 8. Menambah Provider Baru

1. Tambah/pakai port di `providers/<jenis>/ports.py`.
2. Buat `mock.py` dulu (kalau belum ada) yang melaporkan biaya simulasi.
3. Buat adapter asli; semua panggilan lewat `BudgetGuard`, punya timeout, retry/backoff, semaphore, dan idempotency key.
4. Tambah harga di `config/pricing.yaml` dengan `verified_at`.
5. Contract test dengan fixture rekaman (`respx`).
6. Pasang di `bootstrap.py` di balik flag `PAID_PROVIDERS_ENABLED` + flag provider.
7. Catat risiko baru di `docs/RISKS.md`.

## 9. Git & Dokumentasi

- Pesan commit Bahasa Indonesia, singkat, kalimat perintah (contoh: `Tambah ledger reservasi budget`).
- Satu commit = satu perubahan logis. Jangan campur refactor dan fitur.
- Keputusan arsitektur baru → ADR di `docs/adr/NNNN-judul.md`.
- Perubahan perilaku produk → update PRD; perubahan struktur → update ARCHITECTURE; fase selesai → centang AC di DEVELOPMENT_PLAN dan update §2 file ini.

## 10. Definition of Done

- Acceptance criteria tugas/fase terpenuhi dan bisa dibuktikan dengan test.
- ruff, mypy, lint-imports, pytest hijau.
- Tidak ada panggilan jaringan di test, tidak ada secret, tidak ada biaya nyata.
- Dokumen terkait sudah diperbarui.
