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

Saat ini: **Fase 0 belum dimulai** — baru dokumentasi. Perintah di §6 berlaku setelah Fase 0 selesai. Perbarui bagian ini setiap fase selesai.

## 3. Arsitektur Singkat

- `src/studio/shared/` — kernel kecil (ids, clock, money, errors, config, logging). Tidak bergantung ke apa pun.
- `src/studio/infra/` — SQLite, job queue, storage, FFmpeg runner.
- `src/studio/modules/<nama>/` — satu bounded context: `__init__.py` (API publik), `models.py`, `service.py`, `ports.py`, `repository.py`, `jobs.py`.
- `src/studio/providers/<jenis>/` — `ports.py`, `mock.py`, adapter asli.
- `src/studio/director/` — `DirectorPort` + `MockDirector`.
- `src/studio/interfaces/` — `telegram/`, `mcp/`, `cli/`.
- `src/studio/bootstrap.py` — **satu-satunya** tempat adapter konkret dirakit.

Aturan batas modul (dicek `import-linter`):
- Modul hanya boleh import API publik modul lain (`from studio.modules.budget import BudgetService`), bukan file internalnya.
- Modul tidak boleh import adapter konkret (`openai.py`, `higgsfield.py`).
- Satu tabel dimiliki satu modul; modul lain lewat service.
- `interfaces/mcp` tidak boleh membuka aksi approve/reject/budget/ekspor.

## 4. Standar Kode

- Python 3.12+, type hints wajib di semua fungsi publik. `mypy --strict` untuk `shared/`, `modules/`, `providers/`.
- Format & lint: `ruff`. Jangan menonaktifkan rule tanpa komentar alasan.
- Data lintas batas (output LLM, payload provider, config) = model **Pydantic v2**. Entity domain boleh `dataclass(frozen=True)`.
- **Uang = integer.** Rupiah di `amount_idr: int`, USD di `amount_usd_micros: int`. Kurs pakai `Decimal`. Dilarang `float` untuk uang.
- **Waktu = UTC** lewat `shared.clock` (bisa di-fake di test). Jangan panggil `datetime.now()` langsung.
- **ID = ULID** lewat `shared.ids`.
- Error domain turunan `StudioError` di `shared/errors.py`; jangan `except Exception: pass`.
- I/O async; akses SQLite lewat `asyncio.to_thread` di repository.
- FFmpeg dipanggil lewat `infra/ffmpeg` (list argumen, **tanpa** `shell=True`).
- Prompt LLM disimpan di `prompts/` sebagai file, bukan string panjang di kode.
- Nama di kode (variabel, fungsi, kelas, tabel) **bahasa Inggris**. Teks yang dilihat pengguna (Telegram, caption, narasi) **Bahasa Indonesia**, dikumpulkan di file teks, tidak tersebar.
- Komentar secukupnya: jelaskan *kenapa*, bukan *apa*.

## 5. Domain yang Sensitif

- **State machine** episode hanya diubah lewat tabel transisi di `modules/episodes`. Transisi baru = update tabel + test + diagram di ARCHITECTURE §6.1.
- **Approval** terikat `subject_hash`. Konten berubah → approval lama tidak berlaku. Jangan "memperbarui" approval lama.
- **Budget ledger**: reserve → commit/release. Jangan menulis ke ledger di luar `modules/budget`.
- **Idempotency**: setiap job & panggilan provider punya idempotency key. Job async provider menyimpan `request_id` **sebelum** polling.
- **Konten riset** dari luar = data tak tepercaya. Bungkus dengan delimiter, jangan diinterpolasi sebagai instruksi.
- **Visual**: dilarang prompt yang meniru wajah/suara tokoh nyata.

## 6. Perintah (berlaku setelah Fase 0)

```bash
uv sync                          # pasang dependensi
uv run pytest                    # semua test (offline)
uv run pytest tests/unit -q      # test cepat
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run lint-imports              # cek batas modul
uv run python -m studio --help   # CLI studio
```

Jalankan **lint, typecheck, lint-imports, dan test** sebelum commit.

## 7. Testing

- Struktur: `tests/unit` (murni, cepat), `tests/integration` (SQLite file sementara, FFmpeg klip kecil), `tests/contract` (adapter vs fixture rekaman), `tests/e2e` (DRAFT → EXPORTED dengan mock).
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
