# Laporan Implementasi Fase 2 — Research & Documentary Script Engine

| | |
|---|---|
| Tanggal | 2026-10-25 |
| Branch | `claude/phase-2-research` (basis: `claude/phase-1-core` @ `ae5cc22`) |
| Status | Selesai, **menunggu persetujuan owner** sebelum Fase 3 |
| Biaya nyata | Rp0 — semua provider mock, tidak ada panggilan jaringan |

Ringkasnya: pipeline **Topik → Rencana Riset → Bukti → Verifikasi Sumber → Ekstraksi Fakta → Brief → Naskah → Editorial Gate → G1** sekarang jalan penuh dengan mock. Semua keputusan kualitas (cek fakta, editorial gate) dibuat oleh **kode deterministik**, bukan oleh AI. AI tidak bisa approve apa pun.

---

## 1. Arsitektur Baru

### 1.1 TD-01 selesai: eksekusi job dua fase ([ADR-0011](../adr/0011-eksekusi-job-dua-fase.md))

Masalah Fase 1: handler job jalan **di dalam** transaksi SQLite, jadi kalau handler memanggil LLM, seluruh database terkunci selama panggilan itu.

Sekarang:

```
worker ── claim job (tx singkat) ──▶ handler(job, lease)          ← di luar transaksi
                                      │
                                      ├─ MeteredCaller.call()      ← tiap langkah DB = tx singkat sendiri
                                      │    1. cek provider_calls (pakai ulang / tolak unknown)
                                      │    2. BudgetGuard.reserve + catat in_flight
                                      │    3. panggil provider + SpendTicket   ← TANPA transaksi
                                      │    4. commit biaya aktual + settle
                                      │
                                      └─ lease.finish(work)        ← 1 tx singkat:
                                           tulis artefak + transisi + complete(fencing token)
```

- `Lease.heartbeat()` memperpanjang lease di antara langkah; `Lease.require_outside_transaction()` menolak I/O yang tak sengaja dipanggil di dalam transaksi.
- Hasil tahap diterima di `WorkflowService._accept` hanya kalau status + versi episode masih sama. Kalau episode sudah direvisi/dibatalkan → job `OBSOLETE`.
- Handler lama yang hanya menulis DB dibungkus `atomic()` (perilaku Fase 1 tetap).

### 1.2 Tabel `provider_calls` (migrasi `0004`)

Satu baris per panggilan provider: `idempotency_key` (UNIQUE), status `in_flight / succeeded / failed / unknown`, `attempt`, estimasi token input, `max_output_tokens`, estimasi biaya, otorisasi, ledger entry, respons, token & biaya aktual. Trigger: baris `succeeded`/`unknown` final, tidak bisa dihapus.

| Kejadian | Status | Biaya | Diulang otomatis? |
|---|---|---|---|
| Sukses | `succeeded` | biaya aktual | Tidak perlu — job yang diulang **memakai ulang** respons |
| Provider tidak tersedia / menolak | `failed` | reservasi di-release | Ya (retry job biasa, attempt baru) |
| Timeout setelah terkirim | `unknown` | dicatat sebesar reservasi | **Tidak** — owner yang memutuskan |
| Worker mati di tengah panggilan | `unknown` (saat recovery) | dicatat sebesar reservasi | **Tidak** (kecuali provider menjamin `idempotent_replay`) |
| Hasil datang dari worker basi | ditolak (`LeaseLostError`) | tidak dobel | — |

### 1.3 Lapisan modul baru (dicek `import-linter`)

```
interfaces ─▶ bootstrap ─▶ workflow ─▶ scripting ─▶ research ─▶ calls
           ─▶ {episodes | approvals | budget | artifacts} ─▶ audit ─▶ {infra | providers} ─▶ shared
```

- Kontrak `forbidden`: `modules/` dan `interfaces/` tidak boleh import `studio.providers.*.mock`. Mock hanya dirakit di `bootstrap.py`.
- `App` tidak mengekspos provider mentah. Satu-satunya jalan ke provider: `LLMClient` → `MeteredCaller` → `BudgetGuard`. Mock menolak panggilan tanpa `SpendTicket` (HMAC) yang sah.

### 1.4 Research engine

| Langkah | Siapa | Output |
|---|---|---|
| Topic discovery | LLM (`fast`, otorisasi operasional) | 5 `TopicCandidate` (8 kategori topik, sensitivitas, keterverifikasian, saran format) → **G0 owner** |
| Research plan | LLM (`fast`) | `ResearchPlan`: pertanyaan, kata kunci, jenis sumber |
| Ambil sumber | `SourceProvider` (fixture) | `SourceDocument` — **bukan** dari LLM |
| Verifikasi sumber | kode | `SourceRecord`: tier 1–5, skor, kelompok independen (union-find `origin` + `derived_from`), tanggal akses, karantina injeksi |
| Ekstraksi bukti | LLM (`fast`) per sumber | `EvidenceRecord` (kutipan + stance + klaim) |
| Analisis klaim | LLM (`smart`) | `ClaimRecord` mentah |
| Fact check | **kode** (`FactChecker`) | `ResearchBrief` + `ResearchQualityReport` |

Aturan `FactChecker` (semuanya di `config/editorial.yaml`):
- Kutipan harus ada **persis** di teks sumber (setelah normalisasi spasi). Sumber/bukti/URL yang tidak terdaftar → ditolak.
- Sumber yang terbit sebelum peristiwanya tidak dihitung. Sumber karantina tidak dihitung.
- Klaim `critical` butuh ≥ 2 kelompok independen, `supporting` ≥ 1; tier terbaik harus ≤ 3. Sumber tier 5 tidak dihitung dan tidak bisa membantah.
- Ada pembantah (tier ≤ 4) → **diperdebatkan**. Hipotesis dan interpretasi dipisahkan dari fakta.
- < 3 fakta terverifikasi → riset gagal, episode `FAILED` dari `FACT_CHECKING`.

Anti prompt-injection: teks sumber dipindai pola (`abaikan semua instruksi`, `you are now`, `approve the editorial gate`, tag `<system>`, …). Kalimat yang cocok diganti `[DIHAPUS: …]` sebelum masuk prompt, sumbernya dikarantina, buktinya tidak diteruskan ke analisis klaim. Semua data masuk prompt dibungkus `<<<DATA … DATA>>>` dengan instruksi sistem bahwa isinya bukan instruksi.

### 1.5 Script engine & editorial gate

| Format | Rentang | Default |
|---|---|---|
| Quick Files | 30–45 s | 40 s |
| The Archives | 75–90 s | 80 s |
| Deep Files | 120–180 s | 135 s |

- Naskah wajib 5 segmen berurutan: **hook → context → conflict → explanation → closing**, tiap kalimat membawa `claim_refs`, tiap segmen punya arahan visual, plus catatan pelafalan.
- Durasi = jumlah kata ÷ WPM (default 150, bisa diubah) + jeda 0,4 s antarsegmen.
- **EditorialGate** (deterministik), 12 aturan blocking + 6 warning (rinciannya di ARCHITECTURE §7.2).
- Gagal → 1× auto-revisi (`script_revision`) → masih gagal → `FAILED` dari `SCRIPTING` + artefak `editorial_report` berisi instruksi revisi.
- Review LLM (`script_quality_review`) cuma menambah catatan; field `approve`/`passed` dari LLM **diabaikan** (diuji).
- **Override** hanya owner (`episode override-editorial --reason …`, alasan ≥ 10 karakter). Override tercatat di audit dan ikut tampil di subjek kartu G1. G1 tetap harus di-approve owner.

---

## 2. File yang Berubah

88 file (65 baru, 23 diubah), +6.853 / −232 baris.

**Infra**
- `src/studio/infra/jobs/lease.py` *(baru)* — `Lease`, `JobOutcome`, `JobExecutionError`.
- `src/studio/infra/jobs/worker.py`, `queue.py`, `__init__.py` — handler `(job, lease)`, `heartbeat`, `atomic()`.
- `src/studio/infra/db/migrations/0004_provider_calls.sql` *(baru)* — tabel `provider_calls`, kolom `episodes.format`, trigger.

**Providers** *(semua baru)*
- `src/studio/providers/errors.py`, `tickets.py`, `llm/ports.py`, `llm/mock.py`, `sources/ports.py`, `sources/mock.py`.
- `src/studio/providers/fixtures/` — 17 file YAML: sumber 3 topik (Krakatau 1883: 10 sumber termasuk 1 sumber injeksi; Naskah Voynich: 5; Garis Wallace: 4) dan respons LLM per task. Semua URL `https://fixture.03am.invalid/…`, semua penerbit bertanda "(FIXTURE)".

**Modul baru**
- `src/studio/modules/calls/` — `MeteredCaller`, `LLMClient`, `PromptLibrary`, `wrap_data`, repository `provider_calls`.
- `src/studio/modules/research/` — model, config, teks, injeksi, penilaian sumber, `FactChecker`, `ResearchEngine`.
- `src/studio/modules/scripting/` — config format, model naskah, timing, `EditorialGate`, `ScriptEngine`.
- `src/studio/modules/workflow/stages.py` — `ContentStages` (tahap konten di luar transaksi).
- `src/studio/prompts/*.md` — `_system.md` + 7 template task.

**Modul yang diubah**
- `workflow/service.py` — `handle_stage_job` dua fase, `_accept`, `override_editorial`, `create_episode(format=…)`, subjek G1 memuat `editorial_report`.
- `workflow/placeholders.py` — discover/research/factcheck/script dihapus; storyboard diturunkan dari segmen naskah.
- `episodes/*` — `DocumentaryFormat`, kolom `format`. `artifacts/__init__.py` — `EDITORIAL_REPORT`, `EDITORIAL_OVERRIDE`.
- `bootstrap.py` — merakit calls/research/scripting; provider mentah tidak diekspos.
- `shared/config.py` — path `llm.yaml` & `editorial.yaml`.
- `interfaces/cli/main.py` — `episode new --format`, `episode override-editorial`, `pipeline run`, `research show`, `script show`, `llm calls`.

**Config**: `config/llm.yaml`, `config/editorial.yaml` *(baru)*; `pyproject.toml` (lapisan + kontrak import-linter).

**Test**: baru `test_lease.py`, `test_metered_calls.py`, `test_research_pipeline.py`, `test_script_pipeline.py`, `test_research_rules.py`, `test_editorial_rules.py`; diubah `conftest.py`, `test_cli.py`, `test_jobs.py`, `test_workflow.py`.

**Dokumen**: `CLAUDE.md`, `docs/ARCHITECTURE.md` (v0.3), `docs/DEVELOPMENT_PLAN.md` (AC2.x + bukti), `docs/PRD.md` (8 kategori topik, 3 format, aturan riset & editorial), `docs/adr/0011-eksekusi-job-dua-fase.md` *(baru)*, catatan TD-01 di `phase-1-audit.md`, laporan ini.

---

## 3. Hasil Quality Gates (lokal)

| Gate | Perintah | Hasil |
|---|---|---|
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 119 files already formatted |
| Typecheck | `uv run mypy src` (strict) | no issues found in 74 source files |
| Batas modul | `uv run lint-imports` | 2 kept, 0 broken |
| Test (Python 3.12.3) | `uv run pytest -v` | **287 passed, 0 failed, 0 skipped, 0 error** |
| Test (Python 3.13) | `uv run --python 3.13 pytest -q` | 287 passed |

287 = 198 test regresi Fase 1 (semua tetap lulus) + 89 test baru:

| File | Test |
|---|---|
| `tests/unit/test_editorial_rules.py` | 25 |
| `tests/unit/test_research_rules.py` | 17 |
| `tests/integration/test_metered_calls.py` | 14 |
| `tests/integration/test_script_pipeline.py` | 12 |
| `tests/integration/test_lease.py` | 9 |
| `tests/integration/test_research_pipeline.py` | 9 |
| `tests/integration/test_cli.py` (tambahan) | 3 |

Empat test Fase 1 yang mengunci perilaku placeholder lama (judul topik contoh, titik crash, titik penolakan budget, error transient) diadaptasi ke pipeline baru dengan **jaminan yang sama** (crash setelah provider dibayar tetap tidak dobel bayar; penolakan budget tetap `FAILED` tanpa retry; error transient tetap di-retry dengan backoff).

### 3.1 Mutation check (apakah test benar-benar menangkap bug)

Kode sengaja dirusak satu per satu, lalu test dijalankan:

| Mutasi | Test yang gagal |
|---|---|
| Verifikasi kutipan di `FactChecker` dimatikan | 1 |
| Teks sumber tidak disanitasi sebelum masuk prompt | 1 |
| Sumber injeksi tidak dikarantina | 1 |
| Baris `in_flight` di-replay buta setelah crash | 2 |
| `_accept` tidak mengecek versi episode | 1 |
| Cek hedging klaim diperdebatkan dimatikan | 1 |
| Cek angka tanpa sumber dimatikan | 1 |
| Mock tidak memverifikasi tiket belanja | 1 |
| Auto-revisi dimatikan | 1 |

Satu mutasi **tidak** tertangkap: menghapus cek "baris masih `in_flight` + attempt sama" di langkah 4 `MeteredCaller`. Setelah ditelusuri, hasil worker basi tetap tertolak oleh lapisan cadangan (`LedgerStateError` karena ledger entry sudah final, lalu rowcount `settle` = 0, lalu fencing token di `complete`). Jadi bukan celah, tapi pertahanan berlapis; cek itu dipertahankan sebagai lapisan pertama dengan pesan error yang jelas.

### 3.2 Smoke test

Kelima kombinasi topik × format (Krakatau quick/archives/deep, Voynich archives, Wallace quick) sampai `AWAITING_EDITORIAL` dengan biaya simulasi Rp268–Rp497 per episode (batas pra-produksi Rp5.000).

---

## 4. Hasil GitHub Actions

Run [#5 (id 40216692773)](https://github.com/welldan23/03am/actions/runs/40216692773), event `push`, commit `71797fa`. Dicek lewat GitHub API (daftar job + log), bukan asumsi.

| Job | Lint | Format | Typecheck | Batas modul | Test (offline) | Kesimpulan |
|---|---|---|---|---|---|---|
| `check (3.12)` | ✅ | ✅ | ✅ | ✅ | ✅ `287 passed in 22.82s` | **success** |
| `check (3.13)` | ✅ | ✅ | ✅ | ✅ | ✅ `287 passed in 18.20s` | **success** |

Satu-satunya warning: *"Node.js 20 is deprecated"* untuk `actions/checkout@v4` dan `astral-sh/setup-uv@v6` (TD-13). Warning ini tidak menggagalkan build.

Commit laporan ini (yang hanya mengubah dokumen) memicu run CI baru; hasilnya dilaporkan di ringkasan akhir ke owner.

---

## 5. Contoh Output dari Mock Pipeline

Dijalankan dari CLI saja:

```bash
uv run studio budget activate
uv run studio episode new --category sejarah --format archives
uv run studio pipeline run <EPISODE_ID>
uv run studio pipeline run <EPISODE_ID> --topic 1
uv run studio research show <EPISODE_ID>
uv run studio script show <EPISODE_ID>
uv run studio llm calls <EPISODE_ID>
```

### 5.1 G0 — kandidat topik (owner memilih)

```
Menunggu pilihan topik (G0). Kandidat:
  1. Dentuman Krakatau 1883 [fenomena_alam, sensitivitas rendah]
  2. Naskah Voynich: Buku yang Belum Bisa Dibaca [misteri_sejarah, sensitivitas rendah]
  3. Garis Tak Kasatmata di antara Bali dan Lombok [geografi, sensitivitas rendah]
  4. Banda dan Perebutan Pala [sejarah_dunia, sensitivitas sedang]
  5. Garis Laut di Natuna [geopolitik, sensitivitas tinggi]
Ulangi dengan --topic N untuk menyetujui G0 sebagai owner.
```

Setelah `--topic 1`:

```
Episode 01M5T1EHF2A5GFRSSRXSK7FQBM: AWAITING_EDITORIAL
Menunggu keputusan owner: G1 → approval 01M5T1EJMQF5B0WJ9QJR98HFA6
Biaya LLM (simulasi): Rp444
```

### 5.2 ResearchBrief (`research show`)

```
Topik     : Dentuman Krakatau 1883 [fenomena_alam]
Tujuan    : Menyusun kronologi dan dampak letusan Krakatau 1883 dari sumber yang dapat diverifikasi.
Sensitif  : rendah — Bencana alam historis; korban jiwa disampaikan dengan hormat dan sesuai arsip.
Mutu riset: LULUS (8 fakta terverifikasi, minimal 3)

Fakta terverifikasi (8)
  C-krak-activity-may: Aktivitas Krakatau meningkat sejak Mei 1883.
      sumber KRK-S1 — 1 kelompok sumber independen, tier terbaik 1
  C-krak-peak-date: Puncak letusan Krakatau terjadi pada 26–27 Agustus 1883, dengan ledakan terbesar pada pagi 27 Agustus 1883.
      sumber KRK-S1, KRK-S6 — 2 kelompok sumber independen, tier terbaik 1
  C-krak-location: Krakatau adalah gugusan pulau vulkanik di Selat Sunda, di antara Jawa dan Sumatra.
      sumber KRK-S1, KRK-S6 — 2 kelompok sumber independen, tier terbaik 1
  C-krak-sound: Dentuman letusan Krakatau dilaporkan terdengar di Pulau Rodrigues, sekitar 4.800 kilometer dari sumbernya.
      sumber KRK-S3, KRK-S4 — 2 kelompok sumber independen, tier terbaik 2
  C-krak-tsunami: Tsunami yang dipicu letusan menjadi penyebab utama korban jiwa di pesisir Banten dan Lampung.
      sumber KRK-S1, KRK-S2 — 2 kelompok sumber independen, tier terbaik 1
  C-krak-deaths: Catatan resmi mencatat 36.417 korban jiwa, atau lebih dari 36.000 orang, sebagian besar akibat tsunami.
      sumber KRK-S2, KRK-S6 — 2 kelompok sumber independen, tier terbaik 2
  C-krak-sunsets: Aerosol letusan membuat senja berwarna merah menyala teramati di banyak negara selama berbulan-bulan.
      sumber KRK-S1, KRK-S4, KRK-S7 — 2 kelompok sumber independen, tier terbaik 1
  C-krak-telegraph: Kabar letusan menyebar ke berbagai benua dalam hitungan jam melalui jaringan telegraf.
      sumber KRK-S3, KRK-S4 — 2 kelompok sumber independen, tier terbaik 2

Interpretasi (0)

Hipotesis (0)

Diperdebatkan (2)
  C-krak-deaths-120k: Korban tewas letusan Krakatau mencapai lebih dari 120.000 orang.
      sumber KRK-S5; dibantah KRK-S2 — didukung 1 sumber, dibantah KRK-S2
  C-krak-scream: Langit merah setelah letusan Krakatau mengilhami lukisan The Scream karya Edvard Munch.
      sumber KRK-S7; dibantah KRK-S9 — didukung 1 sumber, dibantah KRK-S9

Belum terverifikasi (1)
  C-krak-temperature: Suhu rata-rata global turun pada tahun setelah letusan.
      sumber KRK-S1, KRK-S8 — 2 sumber pendukung tetapi hanya 1 kelompok independen (perlu 2)

Sumber
  KRK-S1 tier 1 skor 95 [origin:jvn] Jurnal Vulkanologi Nusantara (FIXTURE) — https://fixture.03am.invalid/krakatau/kronologi-vulkanologis (diakses 2026-10-25)
  KRK-S2 tier 2 skor 85 [origin:arsip-kolonial] Arsip Nasional (FIXTURE) — https://fixture.03am.invalid/arsip/krakatau-laporan-resmi (diakses 2026-10-25)
  KRK-S3 tier 2 skor 85 [origin:lgf] Lembaga Geofisika (FIXTURE) — https://fixture.03am.invalid/geofisika/krakatau-gelombang-suara (diakses 2026-10-25)
  KRK-S4 tier 4 skor 55 [origin:jvn] Majalah Sains Populer (FIXTURE) — https://fixture.03am.invalid/majalah/krakatau-langit-merah (diakses 2026-10-25)
  KRK-S5 tier 5 skor 15 [origin:blog-misteri] Blog Misteri (FIXTURE) — https://fixture.03am.invalid/blog/rahasia-kelam-krakatau (diakses 2026-10-25)
  KRK-S6 tier 3 skor 75 [origin:badan-geologi] Badan Geologi (FIXTURE) — https://fixture.03am.invalid/geologi/lembar-informasi-krakatau (diakses 2026-10-25)
  KRK-S7 tier 1 skor 95 [origin:jss] Jurnal Sejarah Seni (FIXTURE) — https://fixture.03am.invalid/sejarah-seni/langit-merah-1883 (diakses 2026-10-25)
  KRK-S8 tier 4 skor 55 [origin:jvn] Portal Berita (FIXTURE) — https://fixture.03am.invalid/berita/dunia-mendingin (diakses 2026-10-25)
  KRK-S9 tier 2 skor 85 [origin:museum-seni] Museum Seni (FIXTURE) — https://fixture.03am.invalid/museum/catatan-kuratorial-the-scream (diakses 2026-10-25)

Catatan mutu
  [warning] INJECTION_SUSPECTED: KRK-S10 berisi pola instruksi tersembunyi; teks dinetralkan & sumber dikarantina
  [info] CONTRADICTION: didukung 1 sumber, dibantah KRK-S2
  [warning] INSUFFICIENT_INDEPENDENCE: 2 sumber pendukung tetapi hanya 1 kelompok independen (perlu 2)
  [warning] CRITICAL_CLAIM_UNVERIFIED: klaim penting C-krak-temperature belum terverifikasi: 2 sumber pendukung tetapi hanya 1 kelompok independen (perlu 2); tidak boleh disajikan sebagai fakta
  [info] CONTRADICTION: didukung 1 sumber, dibantah KRK-S9
```

Yang perlu diperhatikan:
- **KRK-S10** (sumber berisi instruksi tersembunyi) tidak muncul di daftar sumber brief dan tidak dihitung di klaim mana pun.
- Klaim suhu global punya 2 sumber, tapi KRK-S8 adalah turunan KRK-S1 (satu asal `origin:jvn`) → **belum terverifikasi**.
- Angka 120.000 korban dari blog (tier 5) dibantah arsip resmi → **diperdebatkan**.

### 5.3 Naskah The Archives (`script show`)

```
Dentuman yang Terdengar Ribuan Kilometer — The Archives (revisi 0)
Estimasi 79.6s untuk target 80s · 194 kata · 150 kata/menit

[  0.0–  9.2s] HOOK
  Visual: Laut lepas saat fajar; peta Samudra Hindia dengan titik Pulau Rodrigues.
  • Pada pagi 27 Agustus 1883, sebuah dentuman terdengar di Pulau Rodrigues, di tengah Samudra Hindia.  [C-krak-peak-date, C-krak-sound]
  • Sumber suara itu berjarak sekitar 4.800 kilometer.  [C-krak-sound]

[  9.2– 26.0s] CONTEXT
  Visual: Peta Selat Sunda; ilustrasi gugusan pulau vulkanik, tanpa wajah tokoh.
  • Suara itu datang dari Krakatau, gugusan pulau vulkanik di Selat Sunda, di antara Jawa dan Sumatra.  [C-krak-location]
  • Aktivitasnya sudah meningkat sejak Mei, dan puncaknya terjadi pada 26 dan 27 Agustus.  [C-krak-activity-may, C-krak-peak-date]
  • Selama berbulan-bulan, gunung itu memberi tanda bahwa ada sesuatu yang tidak biasa.  [C-krak-activity-may]

[ 26.0– 36.0s] CONFLICT
  Visual: Garis pantai Banten dan Lampung; gelombang besar dalam ilustrasi.
  • Namun ancaman terbesar hari itu tidak datang dari langit.  [C-krak-tsunami]
  • Letusan memicu tsunami yang menyapu pesisir Banten dan Lampung.  [C-krak-tsunami]
  • Lalu, berapa sebenarnya harga yang dibayar?  [—]

[ 36.0– 66.4s] EXPLANATION
  Visual: Halaman arsip bergaya dokumen lama; angka korban ditampilkan tenang, tanpa efek dramatis.
  • Catatan resmi menyebut lebih dari 36.000 orang tewas, sebagian besar karena tsunami.  [C-krak-deaths, C-krak-tsunami]
  • Sebagian tulisan populer menyebut angka yang jauh lebih besar, tetapi angka itu tidak didukung arsip resmi.  [C-krak-deaths-120k]
  • Perbedaan itu mengingatkan kita untuk selalu memeriksa dari mana sebuah angka berasal.  [—]
  • Di atmosfer, aerosol letusan membuat senja di banyak negara tampak merah menyala selama berbulan-bulan.  [C-krak-sunsets]
  • Di Eropa pun, senja merah itu ikut teramati.  [C-krak-sunsets]
  • Berita bencananya pun menyebar ke berbagai benua dalam hitungan jam, lewat jaringan telegraf.  [C-krak-telegraph]

[ 66.4– 79.6s] CLOSING
  Visual: Langit senja merah; siluet ruang galeri, lukisan tidak ditampilkan langsung.
  • Sebagian peneliti menduga langit merah itulah yang mengilhami lukisan The Scream karya Edvard Munch.  [C-krak-scream]
  • Dugaan itu masih diperdebatkan.  [C-krak-scream]
  • Yang pasti, satu letusan di Selat Sunda pernah mengubah warna senja di banyak negara.  [C-krak-sunsets, C-krak-location]

Pelafalan: Rodrigues = ro-DRI-ges; Edvard Munch = ED-vard MUNK; Krakatau = kra-ka-TAU

Editorial gate: LULUS
  [warning] NEAR_VERBATIM: 11 kata berturut-turut mirip KRK-S6; pertimbangkan parafrase
  [warning] CLAIM_NARRATION_MISMATCH: isi kalimat tampak tidak sesuai dengan klaim yang dirujuk
  [warning] CLAIM_NARRATION_MISMATCH: isi kalimat tampak tidak sesuai dengan klaim yang dirujuk
  [warning] CLAIM_NARRATION_MISMATCH: isi kalimat tampak tidak sesuai dengan klaim yang dirujuk
  [warning] UNREFERENCED_SENTENCE: kalimat di segmen faktual tanpa rujukan klaim
  [warning] CLAIM_NARRATION_MISMATCH: isi kalimat tampak tidak sesuai dengan klaim yang dirujuk
```

Klaim yang diperdebatkan (`C-krak-deaths-120k`, `C-krak-scream`) dipakai dengan bahasa jujur ("sebagian tulisan…", "sebagian peneliti menduga…", "masih diperdebatkan"). Klaim suhu global yang belum terverifikasi **tidak** dipakai sama sekali.

### 5.4 Jejak biaya tiap panggilan LLM (`llm calls`)

Format: task, status, mode, estimasi token (input+output maks), reservasi → biaya aktual, otorisasi, ledger, idempotency key.

```
topic_discovery        succeeded simulated est 373+1200 tok    Rp37 →   Rp25  otorisasi W8WH1N ledger FA8KJ8  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:DISCOVERING:2:topic_discovery:main
research_plan          succeeded simulated est 466+800 tok    Rp27 →   Rp10  otorisasi QCGKHN ledger EP3MK8  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:RESEARCHING:4:research_plan:main
evidence_extraction    succeeded simulated est 659+900 tok    Rp31 →   Rp12  otorisasi QCGKHN ledger 8D70Q4  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:RESEARCHING:4:evidence_extraction:KRK-S1
… (9 baris evidence_extraction lain, satu per sumber KRK-S2…S10) …
claim_analysis         succeeded simulated est 1931+2500 tok   Rp426 →  Rp171  otorisasi QCGKHN ledger 029TM7  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:RESEARCHING:4:claim_analysis:main
script_generation      succeeded simulated est 1137+3000 tok   Rp469 →  Rp151  otorisasi QCGKHN ledger B8ND20  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:SCRIPTING:6:script_generation:main
script_quality_review  succeeded simulated est 1535+600 tok    Rp29 →   Rp13  otorisasi QCGKHN ledger R7YP4S  stage:01M5T1EHF2A5GFRSSRXSK7FQBM:SCRIPTING:6:script_quality_review:r0
```

15 panggilan, total Rp444 (simulasi). Discovery dibayar dari otorisasi operasional; semua yang lain dari otorisasi pra-produksi G0 yang sama.

---

## 6. Status Acceptance Criteria

Lihat [DEVELOPMENT_PLAN §Fase 2](../DEVELOPMENT_PLAN.md) — setiap AC diberi nama test buktinya.

- AC2.1–AC2.5, AC2.7–AC2.20: ✅
- **AC2.6** (durasi storyboard ± 1 s, snap `ai_video`): **dipindah ke Fase 4**, karena storyboard engine memang di luar cakupan brief Fase 2. Storyboard sekarang masih placeholder yang diturunkan dari segmen naskah.
- AC2.4 dan AC2.5 dipertegas/diganti sesuai brief Fase 2 (klaim belum terverifikasi dilarang di naskah, bukan di brief; durasi pakai rentang format + WPM).

---

## 7. Technical Debt yang Tersisa

| ID | Tingkat | Masalah | Kapan |
|---|---|---|---|
| TD-02 | Sedang | Heartbeat sudah ada di antara langkah, tapi **tidak** dari dalam satu panggilan provider yang panjang. Timeout provider (`config/llm.yaml`, maks 120 s) harus tetap di bawah lease (300 s). | Fase 4 (render) / Fase 6 |
| TD-14 | Sedang | Setelah status `unknown`, episode berhenti `FAILED`; owner bisa `episode retry` (panggilan baru dengan key baru, jadi bisa jadi bayar dua kali kalau provider ternyata sudah memproses). Belum ada langkah "cek dulu di dashboard provider" atau peringatan eksplisit sebelum retry. | Fase 3 (tombol Telegram) / Fase 6 |
| TD-15 | Sedang | Belum ada provider LLM asli maupun adapter sumber web. Penilaian tier masih dari `source_type` yang dideklarasikan fixture, bukan dari domain nyata. | Fase 6 |
| TD-16 | Sedang | Override owner hanya untuk naskah yang gagal (`SCRIPTING`), belum untuk riset yang gagal (`FACT_CHECKING`). | Keputusan owner |
| TD-17 | Rendah | Heuristik `CLAIM_NARRATION_MISMATCH` (kemiripan kata) banyak menghasilkan warning palsu untuk parafrase yang wajar (4 dari 6 warning di contoh §5.3). Hanya warning, tidak memblokir. | Setelah ada data naskah nyata |
| TD-18 | Rendah | Mock LLM menjawab dari fixture per task/topik; catatan owner dan isi prompt tidak memengaruhi jawabannya. Revisi dari owner hanya terlihat di field `notes`, bukan di isi naskah. | Diterima untuk mock |
| TD-19 | Rendah | Fixture hanya 3 topik siap riset; kandidat 4–5 (Banda, Natuna) belum punya sumber, dan tidak semua kombinasi format punya naskah fixture. | Tambah sesuai kebutuhan |
| TD-20 | Rendah | Kategori episode (5) dan kategori topik (8) dipetakan longgar; belum ada validasi bahwa kandidat cocok dengan kategori episode. | Fase 3 |
| TD-21 | Rendah | Purpose Hermes (`conversation`/`tool_call`/…) belum lewat `MeteredCaller`; itu bagian gateway metering. | Fase 5 |
| TD-22 | Rendah | "Cache" hanya reuse per idempotency key dalam satu episode, bukan cache lintas episode; turun otomatis ke tier `fast` saat budget menipis belum ada. | Fase 6 |
| TD-10 | Rendah | Storyboard, estimasi biaya produksi, dan aset masih placeholder; revisi naskah setelah G2 menagih ulang semua aset simulasi. | Fase 4 |
| TD-13 | Rendah | Warning Node.js 20 di GitHub Actions (`actions/checkout@v4`, `astral-sh/setup-uv@v6`). | Kapan saja |
| TD-12 | Info | Branch default GitHub masih `claude/planning-docs`. | Keputusan owner |

---

## 8. Commit

| Commit | Isi |
|---|---|
| `71797fa` | Seluruh kode, test, fixture, dan dokumen Fase 2 (CI hijau, lihat §4) |
| commit berikutnya | Laporan ini dilengkapi hasil CI (dokumen saja) |

Branch: `claude/phase-2-research`. Belum ada PR dan belum di-merge; menunggu persetujuan owner.
