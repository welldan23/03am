# Arsitektur — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.1 — menunggu review |
| Gaya | Modular monolith, ports & adapters (hexagonal) |
| Dokumen terkait | [PRD.md](PRD.md) · [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) · [RISKS.md](RISKS.md) |

---

## 1. Prinsip Utama

1. **Manusia pegang kunci.** Approval (topik, editorial, biaya, final) hanya bisa dilakukan lewat jalur deterministik (tombol Telegram dari user di allowlist atau CLI owner). **AI tidak pernah bisa approve**, sekalipun diminta.
2. **SQLite adalah sumber kebenaran.** Status episode ada di database studio, bukan di memori Hermes atau di chat.
3. **Semua dunia luar lewat port.** LLM, video, gambar, TTS, sumber riset, Telegram, dan Hermes diakses lewat interface (port). Tiap port punya **adapter mock** yang jadi default.
4. **Uang dijaga di satu tempat.** Semua panggilan berbayar wajib lewat `budget` guard: reservasi dulu, baru panggil.
5. **Satu proses, banyak modul.** Bukan microservice. Batas modul ditegakkan oleh aturan import (import-linter), bukan oleh jaringan.
6. **Idempoten & bisa dilanjutkan.** Setiap langkah adalah job dengan idempotency key; restart tidak mengulang yang sudah sukses.
7. **Kecil dan murah.** Harus muat di VPS 2 vCPU / 4 GB bersama Hermes.

## 2. Gambaran Sistem (Context)

```
                        ┌──────────────────────── Telegram ───────────────────────┐
                        │                                                         │
                 ┌──────┴───────┐                                        ┌────────┴────────┐
                 │ Studio Bot   │ approval, status, preview,             │ Director Bot    │
                 │ (milik 03:AM)│ budget — deterministik                 │ (gateway Hermes)│
                 └──────┬───────┘                                        └────────┬────────┘
                        │                                                         │
┌───────────────────────┼─────────────── 03:AM Studio (Python) ───────┐   ┌───────┴────────┐
│                       ▼                                             │   │ Hermes Agent   │
│  interfaces/telegram  interfaces/cli          interfaces/mcp  ◀─────┼───┤ (AI Director)  │
│          │                 │                        │   MCP stdio   │   │  pakai LLM     │
│          └────────┬────────┴────────────────────────┘               │   │  murah         │
│                   ▼                                                 │   └───────┬────────┘
│        Application services (modules/*)                             │           │
│   episodes · workflow · discovery · research · factcheck · scripting│           │
│   storyboard · approvals · budget · assets · voice · render · export│           │
│                   │                                                 │           │
│                   ▼                                                 │           │
│        Ports ──▶ Adapters: mock (default) │ openai │ higgsfield │ tts │           │
│                   │                                                 │           │
│        infra: SQLite (WAL) · job queue · file storage · FFmpeg      │           │
└───────────────────┼─────────────────────────────────────────────────┘           │
                    ▼                                                             ▼
        OpenAI API · Higgsfield API · TTS · sumber riset           OpenAI API (LLM Hermes)
        (DIMATIKAN — mock dulu)                                     (DIMATIKAN — mock dulu)
```

## 3. Stack Teknologi

| Area | Pilihan | Alasan |
|---|---|---|
| Bahasa | Python 3.12+ | Sesuai target; container dev saat ini 3.13 |
| Paket & env | `uv` + `pyproject.toml` | Cepat, lockfile reproducible |
| Model data | Pydantic v2, pydantic-settings | Validasi output LLM (JSON schema) + config |
| Database | SQLite (stdlib `sqlite3`), mode WAL, migrasi SQL bernomor | Nol biaya, cukup untuk 1 owner; tanpa ORM berat |
| Async | `asyncio`; akses DB lewat `asyncio.to_thread` | Telegram & HTTP async, DB tetap simpel |
| Telegram | `aiogram` 3.x | Async, inline keyboard, FSM |
| HTTP | `httpx` + `tenacity` (retry/backoff) | Standar, mudah di-mock (`respx`) |
| MCP server | SDK resmi `mcp` (FastMCP), transport stdio | Jembatan ke Hermes |
| Video | FFmpeg ≥ 6 via `subprocess` + command builder sendiri | Kontrol penuh, mudah dites |
| Log | `structlog` (JSON) | Log terstruktur dengan `episode_id`, `job_id` |
| Test | `pytest`, `pytest-asyncio`, `respx`, `pytest-socket` | Test tanpa jaringan |
| Kualitas | `ruff` (lint+format), `mypy` (strict di core), `import-linter` | Menjaga batas modul |
| ID | ULID | Urut waktu, aman dipakai di nama folder |

## 4. Struktur Repository (Modular Monolith)

```
03am/
├── CLAUDE.md                     # aturan engineering untuk Claude Code
├── README.md
├── pyproject.toml                # dependensi, ruff, mypy, pytest, import-linter
├── uv.lock
├── .env.example                  # daftar env var (tanpa nilai rahasia)
├── .github/workflows/ci.yml      # lint + typecheck + test (offline)
│
├── docs/
│   ├── PRD.md · ARCHITECTURE.md · DEVELOPMENT_PLAN.md · RISKS.md
│   ├── adr/                      # Architecture Decision Records (0001-...)
│   └── spikes/                   # hasil eksperimen (Hermes, Higgsfield, TTS)
│
├── config/
│   ├── studio.example.yaml       # routing model, batas budget, flag provider
│   ├── pricing.yaml              # tabel harga + verified_at + kurs
│   └── styles/                   # style bible per kategori (sejarah.yaml, sains.yaml, …)
│
├── prompts/                      # template prompt (versi di-git, bukan di kode)
│   ├── discovery/ · research/ · factcheck/ · script/ · storyboard/
│
├── hermes/                       # integrasi AI Director
│   ├── config.example.yaml       # potongan mcp_servers untuk ~/.hermes/config.yaml
│   └── skills/documentary-director/SKILL.md
│
├── migrations/                   # 0001_init.sql, 0002_….sql
│
├── src/studio/
│   ├── __main__.py               # entrypoint: `python -m studio`
│   ├── bootstrap.py              # composition root: rakit adapter + service
│   │
│   ├── shared/                   # kernel kecil, tanpa dependensi ke modul lain
│   │   ├── ids.py · clock.py · money.py · errors.py · events.py
│   │   ├── config.py · logging.py
│   │
│   ├── infra/
│   │   ├── db/                   # koneksi, migrator, unit of work
│   │   ├── jobs/                 # antrean job berbasis SQLite + worker
│   │   ├── storage/              # layout folder episode, checksum
│   │   └── ffmpeg/               # runner + command builder
│   │
│   ├── modules/                  # satu folder = satu bounded context
│   │   ├── episodes/             # agregat Episode + state machine
│   │   ├── workflow/             # orkestrator: event → job berikutnya
│   │   ├── discovery/
│   │   ├── research/
│   │   ├── factcheck/
│   │   ├── scripting/
│   │   ├── storyboard/
│   │   ├── approvals/            # gate G0–G3, token sekali pakai
│   │   ├── budget/               # estimasi, ledger, guard, batas
│   │   ├── assets/
│   │   ├── voice/                # TTS + timing subtitle
│   │   ├── render/               # timeline → perintah FFmpeg
│   │   └── export/
│   │
│   ├── providers/                # port + adapter integrasi luar
│   │   ├── llm/                  # ports.py · router.py · mock.py · openai.py
│   │   ├── image/                # ports.py · mock.py · higgsfield.py
│   │   ├── video/                # ports.py · mock.py · higgsfield.py
│   │   ├── tts/                  # ports.py · mock.py · (openai.py / lokal)
│   │   └── sources/              # ports.py · mock.py · wikipedia.py
│   │
│   ├── director/                 # port DirectorPort + MockDirector
│   │
│   └── interfaces/
│       ├── telegram/             # bot, handlers, keyboards, auth, teks (Bahasa Indonesia)
│       ├── mcp/                  # MCP server untuk Hermes (allowlist tool)
│       └── cli/                  # perintah owner: run, approve, budget, export
│
└── tests/
    ├── unit/ · integration/ · contract/ · e2e/
    └── fixtures/                 # respons provider rekaman, media kecil
```

### 4.1 Isi standar satu modul

```
modules/scripting/
├── __init__.py      # API publik modul (yang boleh di-import modul lain)
├── models.py        # entity & value object (Pydantic / dataclass)
├── service.py       # use case (application service)
├── ports.py         # interface yang dibutuhkan modul (kalau ada)
├── repository.py    # akses tabel milik modul ini saja
└── jobs.py          # handler job untuk worker
```

### 4.2 Aturan dependensi (ditegakkan `import-linter`)

```
interfaces ──▶ modules ──▶ providers.ports ◀── providers.adapters
     │             │                 ▲
     └──▶ bootstrap (satu-satunya yang kenal adapter konkret)
modules  ──▶ shared, infra
shared   ──▶ (tidak bergantung ke siapa pun)
```

- Modul hanya boleh import **API publik** modul lain (`from studio.modules.budget import BudgetService`), tidak boleh ke `repository.py` modul lain.
- Modul **tidak boleh** import adapter konkret (`openai.py`, `higgsfield.py`). Adapter dipasang di `bootstrap.py`.
- Satu tabel dimiliki satu modul. Modul lain membaca lewat service.
- `interfaces/mcp` **tidak boleh** import `approvals` untuk aksi approve (hanya baca status).

## 5. Interface: Telegram & Hermes

### 5.1 Masalah yang harus dipecahkan

Bot Telegram hanya bisa di-poll oleh **satu proses** per token (proses kedua dapat error `409 Conflict`). Hermes punya gateway Telegram sendiri. Jadi kita harus memilih siapa yang memegang bot.

### 5.2 Opsi

| Opsi | Cara kerja | Plus | Minus |
|---|---|---|---|
| **A. Satu bot, milik Studio** | Studio Bot menerima semua pesan; pesan bebas diteruskan ke Hermes dalam mode headless / single-query | Satu chat, UX rapi | Tidak memakai gateway Hermes; integrasi lebih rapuh terhadap perubahan CLI Hermes |
| **B. Dua bot (rekomendasi)** | **Studio Bot** = approval, status, preview, budget. **Director Bot** = gateway Hermes untuk ngobrol & memberi arahan; Hermes memanggil studio lewat MCP | Approval 100% di luar jalur LLM; memakai Hermes sesuai desainnya; gagal satu tidak merusak yang lain | Owner punya 2 chat |
| C. Satu bot, milik Hermes | Semua lewat Hermes, approval juga | Paling sederhana | ❌ Approval lewat LLM — melanggar prinsip utama |

**Rekomendasi: Opsi B.** Bisa ditaruh di satu grup Telegram privat supaya terasa seperti satu ruang kerja. Keputusan final setelah spike Hermes (Fase 0).

### 5.3 Peran Hermes sebagai AI Director

Hermes **boleh**:
- membuat episode baru, meminta kandidat topik, menjalankan tahap berikutnya (enqueue job);
- membaca status, naskah, storyboard, laporan fakta, estimasi biaya;
- mengajukan revisi naskah/storyboard (menghasilkan **versi baru**, bukan menimpa);
- merangkum dan menjelaskan ke owner.

Hermes **tidak boleh** (tidak diekspos sama sekali di MCP):
- approve / reject gate mana pun;
- mengubah batas budget atau kill switch;
- menjalankan panggilan provider berbayar secara langsung;
- ekspor atau publikasi.

Pertahanan berlapis:
1. Tool approval **tidak ada** di MCP server studio (bukan sekadar disembunyikan).
2. Di config Hermes, `mcp_servers.studio.tools.include` berisi allowlist eksplisit.
3. Service `approvals` memeriksa `actor`: hanya `TelegramUser(id ∈ allowlist)` atau `CliOwner` yang valid.
4. Toolset berbahaya Hermes (terminal, tulis file, eksekusi kode) dimatikan untuk profil Director; kalau perlu, Hermes jalan di backend Docker.

### 5.4 Kontrak MCP (draft)

| Tool | Efek | Catatan |
|---|---|---|
| `studio_create_episode(category?, idea?)` | buat episode `DRAFT` | idempoten per `client_request_id` |
| `studio_propose_topics(episode_id)` | enqueue job discovery | |
| `studio_get_episode(episode_id)` | baca ringkasan + status | read-only |
| `studio_list_episodes(status?)` | daftar episode | read-only |
| `studio_get_artifact(episode_id, kind)` | baca naskah/storyboard/fakta/estimasi | read-only |
| `studio_request_revision(episode_id, stage, notes)` | buat versi baru tahap tsb | tidak melewati gate |
| `studio_advance(episode_id)` | jalankan tahap berikut **jika** tidak terhalang gate | gate tetap menolak |
| `studio_budget_summary()` | sisa budget | read-only |

`DirectorPort` di `src/studio/director/` mendefinisikan kemampuan yang sama untuk `MockDirector`, supaya alur bisa dites tanpa Hermes.

## 6. Model Domain

### 6.1 Agregat `Episode` & state machine

```
DRAFT
  └─▶ TOPICS_PROPOSED ──[G0 pilih]──▶ TOPIC_SELECTED
        └─▶ RESEARCHING ─▶ FACT_CHECKING ─▶ SCRIPTING ─▶ STORYBOARDING
              └─▶ AWAITING_EDITORIAL ──[G1]──▶ EDITORIAL_APPROVED
                    └─▶ COST_ESTIMATED ─▶ AWAITING_COST ──[G2]──▶ COST_APPROVED
                          └─▶ GENERATING_ASSETS ─▶ GENERATING_VOICE ─▶ RENDERING
                                └─▶ AWAITING_FINAL ──[G3]──▶ FINAL_APPROVED ─▶ EXPORTED

Dari status mana pun yang aktif:
  ─▶ FAILED (bisa retry ke status terakhir)  ─▶ CANCELLED (final)
Dari gate:
  [Revisi] ─▶ kembali ke tahap yang dipilih (versi baru)   [Tolak] ─▶ REJECTED (final)
```

- Transisi didefinisikan di **satu tabel transisi** (`episodes/state.py`). Transisi ilegal = exception, bukan diam-diam.
- Setiap transisi menulis baris ke `episode_events` (audit).
- Revisi setelah G1 (misal ganti naskah saat sudah `COST_APPROVED`) **membatalkan** approval yang lebih belakang: approval biaya lama hangus, harus estimasi ulang.

### 6.2 Approval

- Entity `Approval(id, episode_id, gate, subject_hash, status, decided_by, decided_at, expires_at, notes)`.
- `subject_hash` = hash konten yang disetujui (naskah+storyboard versi X, atau estimasi biaya versi Y). Konten berubah → hash beda → approval tidak berlaku.
- Tombol Telegram membawa token acak sekali pakai yang dipetakan ke `Approval.id` (tidak membawa data mentah).

### 6.3 Budget & ledger

```
estimate(storyboard) ──▶ CostEstimate(items[], total_idr, fx_rate, price_table_version)
        │
   [G2 approve]  ──▶ CostApproval(max_idr = total × (1 + margin))
        │
 sebelum tiap panggilan berbayar:
   BudgetGuard.reserve(episode, provider, est_idr)
     ✔ kill switch aktif?  ✔ approval G2 valid?  ✔ sisa approval cukup?
     ✔ sisa batas bulanan cukup?  ✔ sisa batas provider cukup?
        │ lolos → LedgerEntry(status=RESERVED)
        ▼
   panggil provider ──▶ sukses → COMMITTED (biaya aktual)
                    └─▶ gagal  → RELEASED
```

- Uang disimpan sebagai **integer**: rupiah (`amount_idr`) dan mikro-USD (`amount_usd_micros`). Tidak ada `float` untuk uang.
- Kurs & tabel harga punya versi; estimasi menyimpan versi yang dipakai.
- Biaya aktual > approval → job berhenti, episode kembali ke `AWAITING_COST` dengan estimasi baru.
- Biaya LLM milik Hermes tidak lewat guard studio → dikontrol lewat batas di dashboard OpenAI (project budget) + model murah. Lihat RISKS H-04.

### 6.4 Tabel utama (draft)

| Tabel | Pemilik | Isi |
|---|---|---|
| `episodes` | episodes | id, judul, kategori, durasi target, status, versi aktif |
| `episode_events` | episodes | audit transisi |
| `topic_candidates` | discovery | kandidat + label risiko |
| `sources` | research | URL, judul, penerbit, diakses_pada, kepercayaan |
| `claims`, `claim_evidence` | factcheck | klaim, status, relasi ke sumber |
| `scripts` | scripting | versi naskah, jumlah kata, estimasi durasi |
| `storyboards`, `shots` | storyboard | versi, shot, prompt, jenis visual |
| `approvals` | approvals | gate, subject_hash, keputusan |
| `cost_estimates`, `ledger_entries`, `budget_periods` | budget | estimasi, ledger, batas bulanan |
| `assets` | assets | path lokal, checksum, provider, request_id |
| `provider_calls` | providers (infra) | log panggilan: idempotency key, status, durasi, biaya |
| `jobs` | infra/jobs | antrean: tipe, payload, status, attempts, lease |

## 7. Pipeline & Job

- Antrean job di SQLite: `jobs(id, type, episode_id, payload, status, attempts, run_after, lease_until, idempotency_key UNIQUE)`.
- Worker async mengambil job dengan lease (supaya job yang ditinggal crash bisa diambil ulang).
- `workflow` mendengarkan event domain (`ScriptCreated`, `ApprovalGranted`, …) dan meng-enqueue job berikutnya. Gate = tidak ada job otomatis; menunggu manusia.
- Panggilan provider memakai `idempotency_key = hash(episode, shot, versi, prompt)`. Hasil sukses di `provider_calls` dipakai ulang, tidak dipanggil lagi.
- Job async provider (Higgsfield: `queued` → polling) disimpan `request_id`-nya, sehingga setelah restart worker melanjutkan polling, **bukan** submit ulang.

## 8. Hybrid Model Routing (LLM)

Tugas dipetakan ke **tier**, tier dipetakan ke model di config (nama model tidak di-hardcode).

| Tier | Contoh tugas | Karakter |
|---|---|---|
| `fast` | brainstorming topik, ringkas sumber, ekstrak klaim, format storyboard ke JSON | murah, cepat |
| `smart` | menulis naskah, menilai bukti cek fakta, QA akhir naskah | lebih mahal, dipakai hemat |

Aturan router:
1. Output wajib JSON yang divalidasi Pydantic; gagal validasi → retry 1× dengan pesan error, lalu gagal.
2. Cache respons berdasarkan hash (prompt + model + input) supaya revisi kecil tidak membayar ulang.
3. Budget mendekati batas → tugas `smart` yang boleh diturunkan (ditandai di config) pakai `fast`, dan owner diberi tahu.
4. Tiap panggilan tercatat token in/out + biaya.
5. Nama model & harga per token ada di `config/pricing.yaml` dengan `verified_at`; diverifikasi saat Fase 6.

## 9. Asset, Voice & Render

### 9.1 Strategi visual hemat

| Jenis shot | Sumber | Biaya relatif |
|---|---|---|
| `text_card` / `map` | dibuat lokal (FFmpeg/Pillow) | gratis |
| `archival` | arsip berlisensi bebas (misal Wikimedia Commons) | gratis, wajib atribusi |
| `ai_image` + Ken Burns | provider gambar | murah |
| `ai_video` (hero) | provider video | mahal — dibatasi N per episode (default 3) |

### 9.2 Pipeline render FFmpeg

```
per shot: normalisasi (scale/crop 1080×1920, 30 fps, durasi pas)
          └─ ai_image → zoompan (Ken Burns)
gabung:   xfade antar shot
audio:    voice + musik (sidechaincompress = ducking) → loudnorm −14 LUFS
teks:     subtitle .ass (burn-in) dari timing TTS + label AI
output:   master (H.264 CRF ~20, AAC 192k) + preview (540p, target ≤ 50 MB)
```

- `render/` menghasilkan **timeline** (data murni), lalu `infra/ffmpeg` mengubahnya jadi perintah. Timeline mudah dites tanpa menjalankan FFmpeg.
- Test render memakai klip kecil (resolusi & durasi kecil) supaya CI cepat.

### 9.3 Mock provider

| Mock | Perilaku |
|---|---|
| `MockLLM` | Respons deterministik dari fixture/template sesuai tugas; bisa disetel untuk gagal/JSON rusak |
| `MockImage` | Gambar warna solid + teks prompt (Pillow/FFmpeg) |
| `MockVideo` | Klip `testsrc`/warna + teks, meniru status `queued → in_progress → completed` |
| `MockTTS` | Audio tone/hening dengan durasi = jumlah kata ÷ 2,5 + timing per kalimat |
| `MockSources` | Dossier fixture per topik contoh |
| `MockDirector` | Menjalankan alur standar tanpa Hermes |

Semua mock melaporkan **biaya simulasi** dari `pricing.yaml`, jadi guard budget benar-benar teruji.

## 10. Penyimpanan File

```
data/
├── studio.db
└── episodes/<episode_id>/
    ├── research/      dossier.json, sources.json
    ├── factcheck/     claims.json
    ├── script/        v1.json, v2.json
    ├── storyboard/    v1.json
    ├── assets/        shot_001.png, shot_003.mp4, …
    ├── audio/         voice.wav, timing.json
    ├── render/        master.mp4, preview.mp4, subtitles.ass
    └── export/        (paket ekspor final)
```

`data/` tidak masuk git. Path di DB disimpan relatif terhadap `data/`.

## 11. Konfigurasi & Secret

- `pydantic-settings` membaca `.env` + `config/studio.yaml`.
- Default aman: `PAID_PROVIDERS_ENABLED=false`, semua provider = `mock`.
- Mengganti provider ke versi asli butuh **dua** hal: flag global aktif **dan** flag provider aktif. Kalau salah satu mati → pakai mock (atau gagal keras, sesuai mode).
- Secret: `TELEGRAM_STUDIO_BOT_TOKEN`, `OPENAI_API_KEY`, `HIGGSFIELD_API_KEY_ID`, `HIGGSFIELD_API_KEY_SECRET`, `TELEGRAM_ALLOWED_USER_IDS`. Tidak pernah di-log (redaksi di `structlog` processor).

## 12. Keamanan

- Allowlist user Telegram di Studio Bot **dan** di Hermes (`TELEGRAM_ALLOWED_USERS`).
- Konten riset dari web dibungkus sebagai data (delimiter jelas) dan tidak pernah dieksekusi sebagai instruksi.
- Hermes: matikan toolset terminal/file/eksekusi kode untuk profil Director; allowlist tool MCP.
- MCP server studio hanya membuka tool di §5.4.
- Panggilan keluar hanya ke host yang dikenal (allowlist host di HTTP client).

## 13. Keputusan Arsitektur (ringkas — akan dipecah jadi ADR)

| # | Keputusan | Alasan |
|---|---|---|
| ADR-0001 | Modular monolith, bukan microservice | 1 owner, 1 VPS kecil, biaya rendah |
| ADR-0002 | SQLite + stdlib `sqlite3` + migrasi SQL | Nol biaya, simpel, cukup untuk beban 1 owner |
| ADR-0003 | Approval di luar jalur LLM | Prinsip "manusia pegang kunci" |
| ADR-0004 | Hermes ↔ Studio lewat MCP stdio | Batas jelas, Hermes bisa diganti tanpa ubah domain |
| ADR-0005 | Dua bot Telegram (menunggu spike) | Hindari konflik polling & pisahkan approval |
| ADR-0006 | Mock provider sebagai default | Aturan "tanpa API berbayar" di tahap awal |
| ADR-0007 | Uang sebagai integer + ledger reservasi | Mencegah kebocoran & error pembulatan |
| ADR-0008 | Antrean job di SQLite, bukan Redis/Celery | Tanpa infrastruktur tambahan |
