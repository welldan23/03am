# Arsitektur — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.4 — bot Telegram, Studio Controller, outbox notifikasi (Fase 3) |
| Gaya | Modular monolith, ports & adapters (hexagonal) |
| Dokumen terkait | [PRD.md](PRD.md) · [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) · [RISKS.md](RISKS.md) · [ADR](adr/README.md) |

---

## 1. Prinsip Utama

1. **Manusia pegang kunci.** Approval (topik, editorial, biaya, final), aktivasi anggaran, dan otorisasi belanja hanya bisa dilakukan lewat jalur deterministik oleh owner yang ada di allowlist: tombol Telegram atau CLI. **AI tidak pernah bisa approve**, sekalipun diminta.
2. **SQLite adalah sumber kebenaran.** Status episode ada di database studio, bukan di memori Hermes atau di chat.
3. **Semua dunia luar lewat port.** LLM, video, gambar, TTS, sumber riset, Telegram, dan Hermes diakses lewat interface (port). Tiap port punya **adapter mock** yang jadi default.
4. **Uang dijaga di satu tempat.** Semua belanja (termasuk token Hermes) lewat `BudgetGuard`: reservasi dulu, baru panggil.
5. **Satu proses, banyak modul.** Bukan microservice. Batas modul ditegakkan oleh `import-linter`, bukan oleh jaringan.
6. **Idempoten & bisa dilanjutkan.** Setiap langkah adalah job dengan idempotency key; restart tidak mengulang yang sudah sukses.
7. **Kecil dan murah.** Harus muat di VPS 2 vCPU / 4 GB bersama Hermes.

## 2. Gambaran Sistem (Context)

```
                         Telegram (1 bot: "Studio Bot")
                                     │  hanya Studio yang polling (ADR-0005)
┌────────────────────────────────────┼──────────── 03:AM Studio (Python) ─────────────────┐
│                                    ▼                                                    │
│   interfaces/telegram ── callback tombol ──▶ StudioController (kode sekali pakai)      │
│          │            ── perintah /status /budget ──▶ StudioController                  │
│          └─ teks bebas ──▶ IntentParser (Fase 3: aturan; Fase 5: Hermes) ──┐            │
│                                                                         │               │
│   interfaces/cli ──▶ application services                               ▼               │
│   interfaces/mcp ◀── MCP stdio (tool allowlist, tanpa approval) ── Hermes Agent         │
│          │                                                       (tanpa token bot,      │
│          ▼                                                        tanpa API key)        │
│   modules/controller ──▶ workflow · episodes · approvals · budget · artifacts · …       │
│   notification_outbox (trigger DB) ──▶ dispatcher ──▶ Telegram                          │
│          │                                                              │ LLM request   │
│          ▼                                                              ▼               │
│   providers (port) ──▶ mock (default) │ asli (mati)      llm-gateway (metering, ADR-0009)│
│          │                                                              │               │
│   infra: SQLite (WAL) · job queue · file storage · FFmpeg               │               │
└──────────┼──────────────────────────────────────────────────────────────┼───────────────┘
           ▼                                                              ▼
   Higgsfield · TTS · sumber riset                           OpenAI API (satu-satunya key)
   (DIMATIKAN — mock dulu)                                   (DIMATIKAN — mock dulu)
```

## 3. Stack Teknologi

| Area | Pilihan | Alasan |
|---|---|---|
| Bahasa | Python 3.12+ (dites di 3.12 dan 3.13) | Sesuai target |
| Paket & env | `uv` + `pyproject.toml` | Cepat, lockfile reproducible |
| Model data | Pydantic v2, pydantic-settings | Validasi config & output LLM |
| Database | SQLite (stdlib `sqlite3`), WAL, migrasi SQL bernomor | Nol biaya, simpel |
| Concurrency | **Core sinkron**; interface async (Telegram, gateway) memanggil core lewat `asyncio.to_thread` | Core mudah dites; transaksi SQLite jelas |
| CLI | `argparse` (stdlib) | Tanpa dependensi tambahan |
| Telegram | `aiogram` 3.x (Fase 3) | Async, inline keyboard |
| HTTP | `httpx` + `tenacity` (Fase 5–6) | Standar, mudah di-mock (`respx`) |
| MCP server | SDK resmi `mcp`, transport stdio (Fase 5) | Jembatan ke Hermes |
| Video | FFmpeg ≥ 6 via `subprocess` (Fase 4) | Kontrol penuh |
| Log | `structlog` (JSON, redaksi secret) | Log terstruktur |
| Test | `pytest`, `hypothesis`, `pytest-socket` | Test tanpa jaringan |
| Kualitas | `ruff`, `mypy --strict`, `import-linter` | Menjaga batas modul |
| ID | ULID (implementasi kecil di `shared/ids.py`) | Urut waktu |

## 4. Struktur Repository (Modular Monolith)

Yang bertanda ✅ sudah ada (Fase 1–2). Sisanya rencana.

```
03am/
├── CLAUDE.md · README.md · pyproject.toml · uv.lock · .env.example     ✅
├── .github/workflows/ci.yml                                             ✅
├── docs/  PRD · ARCHITECTURE · DEVELOPMENT_PLAN · RISKS · adr/          ✅
├── config/
│   ├── budget.yaml              # kurs, VPS, alokasi, batas               ✅
│   ├── pricing.yaml             # harga per unit (placeholder)           ✅
│   ├── llm.yaml                 # tier, max output, timeout per task     ✅
│   ├── editorial.yaml           # aturan riset, WPM, format, editorial   ✅
│   └── styles/                  # style bible per kategori                (Fase 4)
├── hermes/                      # config contoh + skill Director          (Fase 5)
├── src/studio/
│   ├── __main__.py              # `python -m studio`                      ✅
│   ├── bootstrap.py             # composition root                        ✅
│   ├── shared/                  # ids, clock, money, errors, actors,      ✅
│   │                            # config, logging
│   ├── infra/
│   │   ├── db/                  # koneksi, transaksi, migrator, migrations/*.sql  ✅
│   │   ├── jobs/                # antrean, worker, Lease (dua fase)        ✅
│   │   ├── storage/ · ffmpeg/                                             (Fase 4)
│   ├── modules/
│   │   ├── audit/               # audit log append-only                    ✅
│   │   ├── episodes/            # agregat Episode + state machine          ✅
│   │   ├── artifacts/           # konten berversi + hash                   ✅
│   │   ├── approvals/           # gate G0–G3, version-aware, token         ✅
│   │   ├── budget/              # rencana, harga, estimasi, ledger, guard  ✅
│   │   ├── calls/               # MeteredCaller + LLMClient (provider_calls) ✅
│   │   ├── research/            # discovery, riset, sumber, fact checker   ✅
│   │   ├── scripting/           # naskah 3 format, timing, editorial gate  ✅
│   │   ├── workflow/            # orkestrator, ContentStages, placeholder  ✅
│   │   ├── controller/          # StudioController, kode tombol, state chat ✅
│   │   ├── notifications/       # outbox notifikasi (diisi trigger DB)     ✅
│   │   ├── storyboard · assets · voice · render · export                  (Fase 4)
│   ├── prompts/                 # template prompt per task (.md)           ✅
│   ├── providers/
│   │   ├── llm/ · sources/      # port + mock + fixtures/                  ✅
│   │   ├── tickets.py           # SpendTicket (HMAC) dari MeteredCaller    ✅
│   │   └── image · video · tts                                            (Fase 4+)
│   ├── director/   DirectorPort + MockDirector                            (Fase 5)
│   └── interfaces/
│       ├── cli/                                                           ✅
│       ├── telegram/            # aiogram adapter, engine, intent, render  ✅
│       └── mcp/ · llm_gateway/                                            (Fase 5)
└── tests/  unit/ · integration/                                           ✅
           contract/ · e2e/                                                (Fase 4+)
```

### 4.1 Isi standar satu modul

```
modules/approvals/
├── __init__.py      # API publik modul (yang boleh di-import modul lain)
├── models.py        # entity & value object
├── service.py       # use case
└── repository.py    # akses tabel milik modul ini saja
```

### 4.2 Aturan dependensi (ditegakkan `import-linter`)

```
interfaces ─▶ bootstrap ─▶ controller ─▶ workflow ─▶ scripting ─▶ research ─▶ calls
           ─▶ {episodes | approvals | budget | artifacts | notifications} ─▶ audit
           ─▶ {infra | providers} ─▶ shared
```

- Lapisan atas boleh memakai lapisan bawah, tidak sebaliknya.
- `episodes`, `approvals`, `budget`, dan `artifacts` **saling independen**. Koordinasi antar-modul hanya terjadi di `workflow`.
- Modul import API publik modul lain (`from studio.modules.budget import BudgetGuard`), bukan `repository.py`-nya.
- Adapter konkret hanya dirakit di `bootstrap.py`. Kontrak `forbidden` melarang `modules`/`interfaces` meng-import `studio.providers.*.mock`.
- Provider hanya dipanggil lewat `modules.calls.MeteredCaller` (reserve → panggil dengan tiket → commit). `App` tidak mengekspos provider mentah.
- `interfaces/mcp` (Fase 5) tidak boleh membuka aksi approve/reject/budget/ekspor.
- `interfaces/telegram` hanya memanggil `StudioController`; tidak ada akses langsung ke modul domain.

## 5. Interface: Telegram & Hermes

Keputusan: **satu bot Telegram milik Studio** ([ADR-0005](adr/0005-satu-bot-telegram.md)).

### 5.1 Ringkasan

- Hanya proses Studio yang polling token bot. Gateway Telegram Hermes **tidak diaktifkan**, jadi konflik polling (409) tidak mungkin terjadi.
- Update Telegram dibagi deterministik:
  - **callback tombol** → `StudioController` → `approvals`/`workflow` (tidak pernah ke LLM);
  - **perintah** → `StudioController`;
  - **teks bebas** → `IntentParser` → `StudioController`. Fase 3 memakai parser berbasis aturan; Fase 5 parser ini bisa digantikan/dilengkapi Hermes headless (`DirectorPort`).

### 5.1a Implementasi Fase 3 ([ADR-0012](adr/0012-antarmuka-telegram-dan-outbox.md), panduan: [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md))

```
Telegram ─▶ aiogram (long polling) ─▶ adapter (Update → Inbound)
        ─▶ StudioBot: chat pribadi? → owner allowlist (from_user.id)? → dedupe update_id
        ─▶ CoreRunner (1 thread untuk semua akses DB bot)
        ─▶ ConversationEngine (sinkron; state di ui_conversations)
              ├─ teks  ─▶ IntentParser (aturan) ─▶ StudioController
              └─ tombol ─▶ callbacks (≤ 64 byte) ─▶ StudioController.press(kode sekali pakai)
        ─▶ Reply (send/edit/answer) ─▶ Transport (aiogram, retry/rate limit) ─▶ Telegram
worker (thread/proses lain, koneksi DB sendiri) ─▶ trigger DB ─▶ notification_outbox
        ─▶ NotificationDispatcher (di luar transaksi, delivered_to per penerima) ─▶ Telegram
```

- **Keamanan:** hanya chat pribadi; identitas dari user ID numerik di `STUDIO_OWNER_IDS` (`telegram:<id>`); non-owner tidak mendapat data apa pun dan dicatat (`telegram.unauthorized`, dibatasi); controller memeriksa owner lagi di setiap metode; kode tombol sekali pakai, terikat actor, kedaluwarsa, hangus per kartu; keputusan approval tidak pernah dari teks bebas; token bot `SecretStr` + filter sensor log.
- **Reliability:** `retry_after` dihormati (singkat ditunggu, panjang dijadwalkan ulang di outbox); timeout/jaringan → backoff; diblokir user → gagal permanen; "message is not modified" diabaikan; pesan > 4096 karakter dipecah per baris (tombol di potongan terakhir); SQLite busy → coba ulang 3×, lalu pesan ramah; error tak terduga → pesan umum tanpa traceback; satu poller per folder data (kunci file); shutdown rapi lewat sinyal.
- Hermes memanggil Studio lewat **MCP stdio** dengan allowlist tool.
- Hermes tidak memegang API key OpenAI. LLM Hermes lewat **gateway metering** Studio ([ADR-0009](adr/0009-metering-token-llm.md)).
- Rencana cadangan (kalau mode headless Hermes tidak layak): dua bot dengan token berbeda. Syarat keamanan dan metering tetap sama.

### 5.2 Peran Hermes sebagai AI Director

Hermes **boleh**: membuat episode, meminta kandidat topik, menjalankan tahap berikutnya (enqueue job), membaca status/artefak/estimasi, mengajukan revisi (menghasilkan versi baru), merangkum untuk owner.

Hermes **tidak boleh** (tidak diekspos sama sekali): approve/reject/revisi di gate, mengaktifkan periode anggaran, mengubah batas atau kill switch, memanggil provider berbayar langsung, ekspor/publikasi.

Pertahanan berlapis:
1. Tool approval/budget tidak ada di MCP server Studio.
2. `mcp_servers.studio.tools.include` di config Hermes berisi allowlist eksplisit.
3. Service `approvals` & `budget` memeriksa `Actor`: hanya `owner` yang ada di `STUDIO_OWNER_IDS`. Actor `director`/`system` selalu ditolak (sudah dites di Fase 1).
4. Toolset berbahaya Hermes (terminal, tulis file, eksekusi kode) dimatikan; kalau perlu Hermes jalan di backend Docker.

### 5.3 Kontrak MCP (draft, Fase 5)

| Tool | Efek | Catatan |
|---|---|---|
| `studio_create_episode(category, duration_s, idea?)` | buat episode `DRAFT` | idempoten per `client_request_id` |
| `studio_start_episode(episode_id)` | `DRAFT → DISCOVERING` | |
| `studio_get_episode(episode_id)` | ringkasan + status | read-only |
| `studio_list_episodes(status?)` | daftar episode | read-only |
| `studio_get_artifact(episode_id, kind)` | baca artefak | read-only |
| `studio_suggest_revision(episode_id, notes)` | simpan catatan revisi untuk owner | tidak mengubah status |
| `studio_budget_summary()` | sisa budget | read-only |

## 6. Model Domain

### 6.1 Agregat `Episode` & state machine

Status kerja (job berjalan) ditulis dengan huruf biasa, gate (menunggu manusia) diberi tanda `[Gx]`:

```
DRAFT ─start─▶ DISCOVERING ─▶ AWAITING_TOPIC [G0]
                                   │ approve
                                   ▼
RESEARCHING ─▶ FACT_CHECKING ─▶ SCRIPTING ─▶ STORYBOARDING ─▶ AWAITING_EDITORIAL [G1]
                                                                   │ approve
                                                                   ▼
                                    ESTIMATING_COST ─▶ AWAITING_COST [G2]
                                                           │ approve
                                                           ▼
GENERATING_ASSETS ─▶ GENERATING_VOICE ─▶ RENDERING ─▶ AWAITING_FINAL [G3]
                                                           │ approve
                                                           ▼
                                                  EXPORTING ─▶ EXPORTED (final)

Di gate:          revise ─▶ kembali ke status kerja sebelumnya   reject ─▶ REJECTED (final)
Status kerja:     fail ─▶ FAILED ─retry─▶ status kerja yang gagal tadi
Non-final:        cancel ─▶ CANCELLED (final)
```

Target revisi yang sah:

| Gate | Boleh kembali ke |
|---|---|
| G0 `AWAITING_TOPIC` | `DISCOVERING` |
| G1 `AWAITING_EDITORIAL` | `RESEARCHING` … `STORYBOARDING` |
| G2 `AWAITING_COST` | `RESEARCHING` … `ESTIMATING_COST` |
| G3 `AWAITING_FINAL` | `RESEARCHING` … `RENDERING` |

Aturan:
- Semua transisi ada di **satu tabel transisi** (`modules/episodes/state.py`). Transisi ilegal = `IllegalTransition`.
- Tiap transisi menaikkan `episode.version` (dipakai untuk optimistic locking) dan ditulis ke audit log.
- Revisi ke tahap X **menggantikan** (supersede) semua approval dari gate yang posisinya setelah X, dan mencabut otorisasi belanja yang lahir dari approval tersebut. Contoh: revisi dari G3 ke `SCRIPTING` menggantikan approval G1 & G2 sekaligus mencabut otorisasi produksi. Approval G0 tetap berlaku.

### 6.2 Artefak berversi

- Tabel `artifacts(episode_id, kind, version, content_json, content_hash)`. Jenis: `topics`, `research`, `factcheck`, `script`, `storyboard`, `cost_estimate`, `render`, `export`.
- Konten baru selalu jadi **versi baru**. Versi lama tidak pernah ditimpa.
- `content_hash` = SHA-256 dari JSON kanonik.

### 6.3 Approval (version-aware)

- Tiap gate punya subjek, yaitu daftar artefak yang disetujui: G0 `topics`; G1 `research, factcheck, script, storyboard`; G2 `script, storyboard, cost_estimate`; G3 `script, storyboard, cost_estimate, render`. Subjek juga mencakup batas belanja (G0: batas pra-produksi, G2: batas produksi).
- `subject_hash` = hash dari `{gate, episode_id, versi + hash tiap artefak, batas belanja}`.
- Approval menyimpan `episode_version` dan `subject_hash` saat dibuat. Saat diputuskan, keduanya dihitung ulang. Kalau beda, approval jadi `superseded` dan keputusan ditolak (`StaleApproval`).
- Status: `pending → approved | rejected | revision_requested | superseded | expired`. Hanya boleh ada satu `pending` per episode+gate (unique index parsial).
- Keputusan pakai `UPDATE … WHERE status='pending'`, sehingga klik ganda hanya diproses sekali.
- **Token sekali pakai** untuk tombol Telegram: `issue_token()` membuat token acak, yang disimpan hanya hash-nya. Token lama otomatis mati saat token baru dibuat atau approval diputuskan. CLI memakai ID approval dengan actor owner.
- Approval kedaluwarsa setelah `approval_ttl_hours`. Owner bisa membuat ulang (`reissue`) dengan subjek terbaru.

### 6.4 Anggaran, otorisasi & ledger

Detail keputusan: [ADR-0010](adr/0010-rencana-anggaran-dan-otorisasi.md).

```
config/budget.yaml ──▶ BudgetPlan (validasi: VPS + alokasi ≤ Rp500.000)
        │ owner: `studio budget activate`
        ▼
budget_periods (snapshot alokasi + kurs)  ──▶ otorisasi `operational`
G0 approve ──▶ otorisasi `preproduction` (per episode)
G2 approve ──▶ otorisasi `production`    (per episode, = batas di kartu G2)

BudgetGuard.reserve(SpendRequest)
  ✔ idempotency key sudah ada? → kembalikan entri lama
  ✔ mode real: kill switch aktif + syarat aktivasi berbayar terpenuhi
  ✔ rencana valid  ✔ periode aktif  ✔ otorisasi aktif & cukup
  ✔ sisa alokasi kategori cukup  ✔ sisa total yang bisa dibelanjakan cukup
      │ lolos → LedgerEntry RESERVED (simpan kurs & versi harga)
      ▼
panggilan provider ─▶ sukses: COMMITTED (biaya aktual; tandai overrun bila > reservasi)
                   └▶ gagal: RELEASED   · hasil tak jelas: commit sebesar reservasi
```

- Rupiah = `int`, USD = `int` mikro-dolar, kurs = `Decimal`; USD→IDR dibulatkan ke atas.
- Mode `simulated` (mock) dan `real` dihitung terpisah dengan aturan yang sama.
- Ledger mencatat `source` (`studio`/`hermes`) dan `purpose` (Hermes: `conversation`, `tool_call`, `retry`, `background`; Studio: `research`, `script`, …).
- Approve G2 ditolak kalau batas produksi melebihi sisa alokasi kategori yang relevan.

### 6.5 Tabel (Fase 1)

| Tabel | Pemilik | Isi |
|---|---|---|
| `schema_migrations` | infra/db | versi migrasi + checksum |
| `audit_log` | audit | append-only (trigger menolak UPDATE/DELETE) |
| `episodes` | episodes | id, kategori, durasi target, status, `failed_from`, `version` |
| `artifacts` | artifacts | konten berversi + hash |
| `approvals` | approvals | gate, subjek, hash, status, token hash, keputusan |
| `budget_periods` | budget | snapshot rencana per bulan |
| `spend_authorizations` | budget | jenis, batas, status, approval asal |
| `ledger_entries` | budget | reservasi/realisasi, kurs, mode, sumber, tujuan |
| `jobs` | infra/jobs | antrean dengan lease + fencing token (`lease_token`) |
| `provider_calls` | calls | satu baris per panggilan provider: key idempotensi, status, attempt, estimasi token/biaya, otorisasi, ledger, respons, biaya aktual (Fase 2, migrasi `0004`) |
| `ui_processed_updates` | controller | update chat yang sudah diproses (dedupe; Fase 3, migrasi `0005`) |
| `ui_action_codes` | controller | hash kode tombol sekali pakai: actor, aksi, payload (ID saja), kedaluwarsa, dipakai |
| `ui_conversations` | controller | state percakapan per chat (alur buat dokumenter, catatan revisi, episode aktif) |
| `notification_outbox` | notifications | notifikasi persisten; diisi trigger dari `audit_log` & `jobs` di transaksi kejadiannya |

Fase 2 juga menambah kolom `episodes.format` (`quick_files`/`archives`/`deep_files`). Sumber, bukti, dan klaim disimpan sebagai **artefak berversi** (`research`, `factcheck`, `script`, `editorial_report`), bukan tabel sendiri, supaya ikut terikat `subject_hash` approval. Tabel lain (`shots`, `assets`, …) ditambah lewat migrasi baru oleh modul pemiliknya.

## 7. Pipeline & Job

- `jobs(id, type, episode_id, payload, status, attempts, max_attempts, run_after, lease_owner, lease_until, lease_token, idempotency_key UNIQUE, last_error)`.
- Worker mengambil job dengan **lease**. Job `running` yang lease-nya habis (worker crash) diambil ulang.
- Setiap klaim menaikkan **fencing token** `lease_token`. `complete`/`fail` adalah satu `UPDATE` bersyarat: `status='running' AND lease_owner=? AND lease_token=? AND lease_until > now`. Worker yang lease-nya kedaluwarsa, diambil worker lain, atau di-restart dengan ID sama tidak bisa menyelesaikan job (`LeaseLostError`).
- **Eksekusi dua fase** ([ADR-0011](adr/0011-eksekusi-job-dua-fase.md), menyelesaikan TD-01): handler `(job, lease)` berjalan **di luar** transaksi. I/O ke provider lewat `MeteredCaller` (setiap langkah DB-nya transaksi singkat sendiri). Hasil ditulis lewat `lease.finish(work)`: satu transaksi singkat yang menulis hasil sekaligus `complete` dengan cek fencing. Lease hilang = rollback hasil, biaya yang sudah ditagih tetap ada di ledger.
- Job yang diulang memakai ulang hasil panggilan provider yang sudah sukses (key idempotensi sama). Panggilan yang hasilnya tidak diketahui (timeout / worker mati di tengah) **tidak** diulang otomatis.
- Handler yang hanya menulis DB dibungkus `atomic()` (perilaku Fase 1).
- Payload job stage membawa `expected_status` + `expected_version`. Kalau episode sudah berubah (revisi/batal), job ditandai `obsolete` tanpa efek.
- Error biasa → retry dengan backoff eksponensial sampai `max_attempts`, lalu episode `FAILED`. Error non-retryable (misalnya budget habis) → langsung `FAILED`.
- Tahap konten (`DISCOVERING`, `RESEARCHING`, `FACT_CHECKING`, `SCRIPTING`) dijalankan `ContentStages` (Fase 2). Tahap setelah G1 masih **placeholder** (storyboard diturunkan dari segmen naskah; estimasi biaya, aset, render simulasi) sampai Fase 4.

### 7.1 Research pipeline (Fase 2)

```
DISCOVERING  topic_discovery ─▶ 5 TopicCandidate ─▶ G0 (owner pilih --choice)
RESEARCHING  research_plan ─▶ SourceProvider (fixture) ─▶ scan injeksi + sanitasi
             ─▶ evidence_extraction per sumber ─▶ claim_analysis
             ─▶ artefak `research` (dossier: plan, sumber, teks, bukti, klaim mentah)
FACT_CHECKING FactChecker (deterministik, tanpa LLM) ─▶ ResearchBrief + ResearchQualityReport
```

- **Otorisasi:** discovery memakai otorisasi operasional (sebelum G0); riset, fact check, dan naskah memakai otorisasi pra-produksi yang lahir dari approve G0 (batas Rp5.000/episode).
- **Sumber** dinilai tier 1–5 (arsip/jurnal → blog/forum) + skor. Sumber yang terbit sebelum peristiwa tidak dihitung. Kelompok independensi dihitung dengan union-find atas `origin` + `derived_from` (artikel yang mengutip sumber lain = satu kelompok).
- **Anti prompt-injection:** teks sumber dipindai pola injeksi (`config/editorial.yaml`). Sumber yang cocok dikarantina (`INJECTION_SUSPECTED`): teksnya disensor sebelum masuk prompt, buktinya tidak dihitung, dan tidak diteruskan ke analisis klaim. Semua data masuk prompt lewat `wrap_data` (`<<<DATA … DATA>>>`) dengan instruksi sistem bahwa isinya bukan instruksi.
- **FactChecker:** kutipan bukti harus ada persis di teks sumber (setelah normalisasi spasi); sumber/URL yang tidak terdaftar ditolak. Klaim `critical` butuh ≥2 kelompok independen, `supporting` ≥1, dengan tier terbaik ≤3. Ada bukti pembantah dari sumber tier ≤4 → `disputed`. Kategori akhir: `verified_fact`, `interpretation`, `hypothesis`, `disputed`, `unverified`. Kurang dari 3 fakta terverifikasi → laporan gagal, episode `FAILED` dari `FACT_CHECKING`.
- Output LLM **tidak pernah** dianggap sumber.

### 7.2 Script engine & editorial gate (Fase 2)

| Format | Rentang | Default |
|---|---|---|
| Quick Files | 30–45 s | 40 s |
| The Archives | 75–90 s | 80 s |
| Deep Files | 120–180 s | 135 s |

- `script_generation` (tier `smart`) menghasilkan `ScriptDraft`: 5 segmen wajib berurutan `hook → context → conflict → explanation → closing`, tiap kalimat membawa `claim_refs`, plus arahan visual dan catatan pelafalan. `build_script` menghitung timing dari jumlah kata ÷ WPM (default 150, configurable) + jeda antarsegmen.
- **EditorialGate** deterministik. Blocking: struktur, rujukan klaim tidak dikenal, klaim `unverified` dipakai, klaim `disputed`/`hypothesis` tanpa kata penanda (hedge), angka tanpa sumber atau tidak cocok dengan klaim, segmen faktual tanpa rujukan, terlalu panjang, sensasional (≥2 istilah), kutipan >20 kata, menyalin ≥15 kata berturut dari sumber, dua klaim yang saling bertentangan sama-sama ditegaskan. Warning: terlalu pendek, mirip sumber ≥10 kata, narasi kurang mirip klaim, kalimat tanpa rujukan, atribusi kabur ("konon", "banyak orang bilang"), satu istilah sensasional.
- Gagal → satu kali auto-revisi (`script_revision`) dengan daftar masalah. Masih gagal → episode `FAILED` dari `SCRIPTING` + artefak `editorial_report` berisi instruksi revisi.
- `script_quality_review` (LLM) hanya menambah catatan advisory; field seperti `approve`/`passed` diabaikan.
- **Override** hanya oleh owner (`override_editorial`, alasan ≥10 karakter, hanya untuk `FAILED` dari `SCRIPTING`): episode lanjut ke G1 dengan laporan bertanda `overridden`, dan override ikut di subjek kartu G1. **AI tidak bisa approve G1**; G1 tetap keputusan owner.
- Untuk provider asli yang async (Higgsfield, Fase 6), panggilan eksternal tidak bisa ikut transaksi. Karena itu `request_id` disimpan di transaksi terpisah sebelum polling.

## 8. Hybrid Model Routing (LLM)

| Tier | Contoh tugas | Karakter |
|---|---|---|
| `fast` | brainstorming topik, ringkas sumber, ekstrak klaim, format JSON, **Hermes** (default) | murah |
| `smart` | menulis naskah, menilai bukti cek fakta, QA akhir | lebih mahal |

- Nama model asli dan harga per 1 juta token ada di `config/pricing.yaml`. Fase 1 memakai nilai **placeholder** yang ditandai belum terverifikasi.
- Semua panggilan, baik dari Studio maupun Hermes, lewat `BudgetGuard` (ADR-0009).
- Tier, `max_output_tokens`, dan timeout per task ada di `config/llm.yaml`. Estimasi input = karakter prompt ÷ `chars_per_token` (4); reservasi = biaya terburuk (input + output maksimum).
- Output wajib JSON tervalidasi Pydantic. JSON tidak valid → satu kali retry dengan key `…:json-retry1` dan purpose `<task>.retry` (dihitung sebagai panggilan terpisah).
- "Cache" = reuse hasil sukses lewat key idempotensi (bukan cache lintas episode). Turun ke tier `fast` saat budget menipis belum dibuat (lihat technical debt Fase 2).

## 9. Asset, Voice & Render (Fase 4)

### 9.1 Strategi visual hemat

| Jenis shot | Sumber | Biaya relatif |
|---|---|---|
| `text_card` / `map` | dibuat lokal | gratis |
| `archival` | arsip berlisensi bebas | gratis, wajib atribusi |
| `ai_image` + Ken Burns | provider gambar | murah |
| `ai_video` (hero) | provider video | mahal — maks. 3 per episode (default) |

### 9.2 Pipeline render FFmpeg

```
per shot: normalisasi (1080×1920, 30 fps) · ai_image → zoompan (Ken Burns)
gabung:   xfade · audio: voice + musik (ducking) → loudnorm −14 LUFS
teks:     subtitle .ass + label AI · output: master + preview (≤ 50 MB)
```

**Performa:** target 180 detik selesai ≤ 10 menit di 2 vCPU adalah **benchmark awal, bukan jaminan**. Fase 4 menyediakan skrip benchmark; hasilnya dicatat di `docs/benchmarks/`. Kalau meleset, yang disetel adalah preset encoder, resolusi preview, dan jumlah filter.

### 9.3 Mock provider

| Mock | Perilaku |
|---|---|
| `MockLLM` | respons deterministik dari fixture; bisa disetel gagal/JSON rusak |
| `MockImage` / `MockVideo` | gambar/klip warna + teks; video meniru `queued → in_progress → completed` |
| `MockTTS` | audio dengan durasi = kata ÷ 2,5 + timing per kalimat |
| `MockSources` | dossier fixture |
| `MockDirector` | alur standar tanpa Hermes |

Semua mock mencatat **biaya simulasi** lewat `BudgetGuard` (mode `simulated`).

## 10. Penyimpanan File

```
data/                       (tidak masuk git)
├── studio.db
└── episodes/<episode_id>/{research,factcheck,script,storyboard,assets,audio,render,export}/
```

## 11. Konfigurasi & Secret

- Env (`.env`, prefix `STUDIO_`): `STUDIO_DATA_DIR`, `STUDIO_CONFIG_DIR`, `STUDIO_OWNER_IDS`, `STUDIO_LOG_LEVEL`, `PAID_PROVIDERS_ENABLED` (default `false`).
- File: `config/budget.yaml` (rencana anggaran) dan `config/pricing.yaml` (harga).
- Kalau `PAID_PROVIDERS_ENABLED=true` dan syarat aktivasi berbayar belum terpenuhi, aplikasi **menolak start**. Di Fase 1 belum ada provider asli, jadi nilai `true` selalu ditolak.
- Secret masa depan: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` (hanya dipegang gateway), `HIGGSFIELD_API_KEY_ID/SECRET`. Secret tidak pernah di-log (ada processor redaksi di `structlog`).

## 12. Keamanan

- `STUDIO_OWNER_IDS` (format `cli:<nama>`, `telegram:<id>`) = satu-satunya yang boleh memutuskan gate & mengaktifkan anggaran. Default kosong = tidak ada yang bisa approve.
- Konten riset dari web = data tak tepercaya (dibungkus delimiter, tidak dieksekusi).
- Hermes: tanpa token bot, tanpa API key, toolset berbahaya dimatikan, allowlist tool MCP.
- Audit log append-only di level database (trigger).
- **Invarian keamanan di level database** (migrasi `0003_security_invariants.sql`), sebagai lapisan kedua di bawah pemeriksaan aplikasi:
  - episode tidak bisa keluar dari gate (kecuali dibatalkan) tanpa keputusan owner yang tercatat untuk gate & versi episode yang sama, dan jenis keputusannya harus cocok dengan arah transisi;
  - otorisasi belanja episode hanya bisa dibuat dari approval G0/G2 yang `approved`, batasnya ≤ batas di approval, tidak bisa dinaikkan, dan tidak bisa dihidupkan lagi setelah dicabut;
  - otorisasi operasional butuh periode anggaran aktif;
  - nilai uang di ledger wajib integer; entri ledger yang sudah selesai tidak bisa diubah atau dihapus.
- CLI hanya bisa bertindak sebagai owner `cli:<nama>` (tidak bisa menyamar `telegram:<id>`) dan tetap harus ada di `STUDIO_OWNER_IDS`. Batas keamanan CLI = akses shell ke server.
- Hermes (`source=hermes`) hanya boleh belanja kategori `openai`, dari otorisasi operasional, dengan purpose `conversation`/`tool_call`/`retry`/`background`.

## 13. Keputusan Arsitektur

| # | Keputusan | Status |
|---|---|---|
| ADR-0001 | Modular monolith | Diterima |
| ADR-0002 | SQLite + stdlib `sqlite3` + migrasi SQL (dibundel di package) | Diterima |
| ADR-0003 | Approval di luar jalur LLM | Diterima |
| ADR-0004 | Hermes ↔ Studio lewat MCP stdio | Diterima |
| [ADR-0005](adr/0005-satu-bot-telegram.md) | Satu bot Telegram milik Studio | **Diterima** (menggantikan "dua bot") |
| ADR-0006 | Mock provider sebagai default | Diterima |
| ADR-0007 | Uang sebagai integer + ledger reservasi | Diterima (detail di ADR-0010) |
| ADR-0008 | Antrean job di SQLite | Diterima |
| [ADR-0009](adr/0009-metering-token-llm.md) | Semua token LLM lewat gateway metering | **Diterima** |
| [ADR-0010](adr/0010-rencana-anggaran-dan-otorisasi.md) | Rencana anggaran, kurs, otorisasi belanja | **Diterima** |
| [ADR-0011](adr/0011-eksekusi-job-dua-fase.md) | Eksekusi job dua fase + `provider_calls` | **Diterima** |
| [ADR-0012](adr/0012-antarmuka-telegram-dan-outbox.md) | Studio Controller, kode tombol sekali pakai, outbox notifikasi | **Diterima** |
