# Rencana Pengembangan — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.2 — Fase 0+1 dikerjakan bersama; spike Hermes dipindah ke awal Fase 5 |
| Dokumen terkait | [PRD.md](PRD.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [RISKS.md](RISKS.md) · [ADR](adr/README.md) |

## Aturan Main Semua Fase

- Development di Claude Code Cloud. **Tidak ada deployment production.**
- **Tidak ada API berbayar** sampai owner memberi izin tertulis (lihat Fase 6).
- Semua integrasi luar memakai **mock** sebagai default.
- Tiap fase selesai = semua acceptance criteria (AC) lulus + CI hijau + dokumen terkait diperbarui + direview owner.
- Fase berikut baru dimulai setelah owner menyetujui fase sebelumnya.
- Tidak ada merge ke branch lain tanpa persetujuan owner.

## Peta Fase

| Fase | Nama | Hasil utama | Status |
|---|---|---|---|
| 0 | Fondasi | Tooling, CI, `shared/` | ✅ selesai (bersama Fase 1) |
| 1 | Inti domain | State machine, approval, budget, ledger, job queue, audit, CLI | ✅ selesai — **menunggu review owner** |
| 2 | Pipeline konten (mock LLM) | Discovery → research → fact check → script → storyboard | Belum dimulai |
| 3 | Telegram Studio Bot (1 bot) | Approval G0–G3 lewat tombol, status, budget | Belum |
| 4 | Aset, TTS, render, ekspor (mock) | MP4 utuh dari aset mock + paket ekspor + benchmark render | Belum |
| 5 | Hermes AI Director | Spike → gateway metering → MCP server → Director di bot yang sama | Belum |
| 6 | Adapter provider asli (default mati) | Adapter OpenAI, Higgsfield, TTS + contract test | Belum |
| 7 | Kesiapan production (tanpa deploy) | Runbook VPS, backup, monitoring, hardening | Belum |

MVP = Fase 0–5 selesai: satu episode bisa dibuat lengkap lewat Telegram dengan mock, biaya nyata Rp0.

---

## Fase 0 — Fondasi

**Pekerjaan**
- `pyproject.toml` (uv), struktur folder (ARCHITECTURE §4), `python -m studio`.
- Tooling: ruff, mypy (strict untuk `src/`), pytest + `pytest-socket` + hypothesis, import-linter.
- `shared/`: config, logging (redaksi secret), ids (ULID), clock, money, actors, errors.
- `.env.example`, `.gitignore`, README, CI GitHub Actions (Python 3.12 & 3.13).

**Acceptance Criteria**
- [x] AC0.1 `uv sync` lalu `uv run pytest` lulus (Python 3.12 dan 3.13).
- [x] AC0.2 `ruff check`, `ruff format --check`, `mypy src`, dan `lint-imports` semua lulus.
- [ ] AC0.3 CI hijau di GitHub untuk commit terakhir (workflow sudah dibuat, menunggu run pertama).
- [x] AC0.4 Test yang mencoba akses jaringan otomatis gagal (ada test negatif).
- [x] AC0.5 Logger tidak pernah mencetak nilai dengan nama kunci mengandung `token`, `key`, `secret`, `password` (ada test).
- [x] AC0.6 `python -m studio --help` jalan.
- [x] AC0.7 Tidak ada API key berbayar yang dibuat atau dipakai.

---

## Fase 1 — Inti Domain

**Pekerjaan**
- `infra/db`: koneksi SQLite (WAL, `foreign_keys`, `busy_timeout`), transaksi reentrant (savepoint), migrator SQL dengan checksum.
- `modules/audit`: audit log append-only.
- `modules/episodes`: agregat + tabel transisi + optimistic locking.
- `modules/artifacts`: konten berversi + hash.
- `modules/approvals`: gate G0–G3, `subject_hash`, token sekali pakai, cek actor, kedaluwarsa.
- `modules/budget`: `BudgetPlan` dari `config/budget.yaml`, tabel harga, estimator, periode, otorisasi, ledger, `BudgetGuard`, usulan realokasi VPS.
- `infra/jobs`: antrean dengan lease, backoff, dead-letter, idempotency key.
- `modules/workflow`: orkestrasi + handler placeholder (artefak contoh + biaya simulasi).
- `interfaces/cli`: perintah owner untuk menguji semuanya.

**Acceptance Criteria**

*State machine & audit*
- [x] AC1.1 Semua transisi legal di tabel transisi dites; transisi ilegal melempar `IllegalTransition`.
- [x] AC1.2 Setiap transisi menulis tepat satu entri audit `episode.transition` (actor, waktu UTC, status lama/baru, versi).
- [x] AC1.3 Audit log append-only: `UPDATE`/`DELETE` ditolak database.
- [x] AC1.4 Migrasi: WAL & foreign keys aktif; dijalankan ulang tidak mengubah apa pun; file migrasi yang diubah setelah diterapkan terdeteksi.

*Approval*
- [x] AC1.5 Approval dengan `subject_hash` atau versi episode yang sudah berubah ditolak dan jadi `superseded`.
- [x] AC1.6 Token approval yang sudah dipakai, sudah diganti, atau kedaluwarsa ditolak.
- [x] AC1.7 Actor `director`/`system`, atau owner yang tidak ada di allowlist, **tidak bisa** memutuskan gate mana pun atau mengaktifkan anggaran.
- [x] AC1.8 Keputusan ganda pada approval yang sama hanya diproses sekali.

*Anggaran*
- [x] AC1.9 `config/budget.yaml` bawaan valid: kurs 17.850, VPS = Rp169.575, total = Rp500.000. Kurs bisa diubah lewat config, dan rencana yang melewati batas membuat semua reservasi ditolak.
- [x] AC1.10 VPS aktual ≠ rencana → rencana "perlu dihitung ulang" dan aktivasi berbayar ditolak. Usulan realokasi memakai cadangan dulu dan totalnya tidak melewati batas.
- [x] AC1.11 `BudgetGuard.reserve` menolak (masing-masing dites): mode real saat kill switch mati, rencana tidak valid, periode tidak aktif, otorisasi tidak aktif/kurang, alokasi kategori kurang, total kurang. Setiap penolakan tercatat di audit.
- [x] AC1.12 Property test (hypothesis): pemakaian (committed + reserved) tidak pernah melewati alokasi kategori maupun batas otorisasi.
- [x] AC1.13 Setiap estimasi & entri ledger menyimpan kurs dan versi harga; uang selalu integer (test AST: tidak ada `float` di modul budget).
- [x] AC1.14 Pemakaian Hermes (percakapan, tool call, retry) tercatat dengan `source=hermes`, memotong alokasi `openai` yang sama dengan Studio, dan ditolak saat habis.
- [x] AC1.15 Approve G2 ditolak kalau batas produksi melebihi sisa alokasi.

*Job queue & workflow*
- [x] AC1.16 Worker crash di tengah job: setelah lease habis job diambil ulang, dan efeknya (artefak, ledger, transisi) tidak terjadi dua kali.
- [x] AC1.17 Worker yang lease-nya sudah diambil worker lain tidak bisa menandai job selesai.
- [x] AC1.18 Error berulang → backoff → `FAILED`; `retry` melanjutkan dari status yang gagal. Error budget langsung `FAILED` tanpa retry.
- [x] AC1.19 Job yang usang (episode sudah direvisi/dibatalkan) ditandai `obsolete` tanpa efek.
- [x] AC1.20 Revisi di G3 ke `SCRIPTING` menggantikan approval G1 & G2, mencabut otorisasi produksi, dan mengembalikan episode ke `SCRIPTING`.
- [x] AC1.21 Lewat CLI saja, episode bisa dibawa dari `DRAFT` sampai `EXPORTED` dengan handler placeholder. Semua biaya tercatat sebagai `simulated`, dan biaya `real` = Rp0.
- [x] AC1.22 `PAID_PROVIDERS_ENABLED=true` membuat aplikasi menolak start.

---

## Fase 2 — Pipeline Konten (Mock LLM)

**Pekerjaan**
- `providers/llm`: `LLMPort`, `MockLLM`, `LLMRouter` (tier `fast`/`smart`, cache, validasi Pydantic, retry JSON) — semua lewat `BudgetGuard`.
- `providers/sources`: `SourcePort`, `MockSources` (3 topik contoh).
- `prompts/` versi pertama (Bahasa Indonesia), style bible di `config/styles/`.
- Modul `discovery`, `research`, `factcheck`, `scripting`, `storyboard` menggantikan handler placeholder.

**Acceptance Criteria**
- [ ] AC2.1 Discovery menghasilkan 3–5 kandidat valid dengan label risiko.
- [ ] AC2.2 Dossier menyimpan sumber lengkap (URL, judul, penerbit, tanggal akses).
- [ ] AC2.3 Klaim kritis dengan < 2 sumber independen berstatus `belum terverifikasi`.
- [ ] AC2.4 Episode dengan klaim kritis `belum terverifikasi` tidak bisa masuk `AWAITING_EDITORIAL`, kecuali ada override owner yang tercatat.
- [ ] AC2.5 Jumlah kata naskah untuk target 30/60/180 detik ada dalam ±10% dari `durasi × 2,5`.
- [ ] AC2.6 Total durasi storyboard = durasi narasi ± 1 detik; durasi `ai_video` di-snap ke nilai yang didukung.
- [ ] AC2.7 Jumlah shot `ai_video` ≤ batas per episode.
- [ ] AC2.8 JSON rusak di-retry 1× lalu job `FAILED` dengan pesan jelas.
- [ ] AC2.9 Router memilih tier sesuai tabel; panggilan identik diambil dari cache tanpa biaya tambahan.
- [ ] AC2.10 Fixture sumber berisi instruksi jahat tidak mengubah perilaku pipeline.
- [ ] AC2.11 Biaya pra-produksi per episode tidak melewati batas otorisasi G0.

---

## Fase 3 — Telegram Studio Bot (satu bot)

**Pekerjaan**
- `interfaces/telegram` (aiogram 3): auth allowlist, perintah, kartu approval + tombol (token sekali pakai), form revisi, notifikasi.
- Router update deterministik: callback → approvals, perintah → service, teks bebas → `DirectorPort` (sementara `MockDirector`).
- Startup memastikan hanya ada satu poller untuk token tersebut (lock file / cek `getWebhookInfo`).

**Acceptance Criteria**
- [ ] AC3.1 Pesan dari user di luar allowlist diabaikan dan tercatat di log.
- [ ] AC3.2 Kartu G0 menampilkan kandidat topik + batas biaya pra-produksi; memilih satu menjalankan riset.
- [ ] AC3.3 Kartu G1 menampilkan ringkasan naskah, jumlah shot, dan ringkasan cek fakta; dokumen lengkap dilampirkan.
- [ ] AC3.4 Kartu G2 menampilkan estimasi per kategori, total Rupiah, kurs, sisa anggaran per kategori, dan batas maksimum.
- [ ] AC3.5 Tombol lama (konten berubah / token terpakai) membalas "kedaluwarsa" tanpa efek.
- [ ] AC3.6 Klik ganda hanya diproses sekali.
- [ ] AC3.7 Callback tombol tidak pernah diteruskan ke Director (test router).
- [ ] AC3.8 `/budget` menampilkan pemakaian bulan ini: simulasi vs nyata, Studio vs Hermes.
- [ ] AC3.9 Bot tetap responsif saat worker menjalankan job panjang.

---

## Fase 4 — Aset, TTS, Render & Ekspor (Mock)

**Pekerjaan**
- `providers/image|video|tts`: port + mock. `MockVideo` meniru status async.
- `modules/assets`, `voice`, `render`, `export`.
- Skrip benchmark render (`scripts/bench_render.py`) + `docs/benchmarks/`.

**Acceptance Criteria**
- [ ] AC4.1 Episode mock 30 detik dan 180 detik ter-render menjadi MP4 1080×1920, 30 fps, H.264/AAC (dicek `ffprobe`).
- [ ] AC4.2 Durasi video = durasi voice ± 0,5 detik.
- [ ] AC4.3 Loudness −14 LUFS ± 1.
- [ ] AC4.4 Tidak ada baris subtitle > 42 karakter.
- [ ] AC4.5 Preview ≤ 50 MB untuk video 180 detik.
- [ ] AC4.6 Tiap panggilan aset lewat `BudgetGuard` (mode simulasi).
- [ ] AC4.7 Worker di-kill saat `MockVideo` `in_progress`: polling dilanjutkan dengan `request_id` yang sama.
- [ ] AC4.8 Regenerasi 1 shot tidak memanggil ulang shot lain.
- [ ] AC4.9 Ekspor hanya untuk `FINAL_APPROVED`; paket lengkap dan `manifest.json` valid.
- [ ] AC4.10 Test E2E `DRAFT → EXPORTED` dengan mock lulus di CI < 3 menit.
- [ ] AC4.11 Tidak ada kode upload ke platform sosial.
- [ ] AC4.12 **Benchmark** render 180 detik dijalankan dengan batas 2 CPU, lalu hasilnya dicatat (waktu, preset, RAM). Target ≤ 10 menit adalah **acuan awal**, bukan syarat lulus. Kalau meleset, dicatat bersama rencana penyetelan.

---

## Fase 5 — Hermes sebagai AI Director

**Pekerjaan**
1. **Spike Hermes** (`docs/spikes/hermes.md`): install versi yang di-pin; uji mode headless (single-query/API lokal) tanpa gateway Telegram; uji MCP stdio + `tools.include`; matikan toolset berbahaya; arahkan `base_url` ke endpoint mock; ukur RAM & token per giliran.
2. `interfaces/llm_gateway`: gateway OpenAI-compatible lokal dengan metering (ADR-0009), awalnya meneruskan ke `MockLLM`.
3. `interfaces/mcp`: MCP server stdio (ARCHITECTURE §5.3).
4. `director/`: `DirectorPort`, `MockDirector`, `HermesDirector` (headless).
5. `hermes/config.example.yaml` + `hermes/skills/documentary-director/SKILL.md`.

**Acceptance Criteria**
- [ ] AC5.1 Spike menjawab: versi, mode headless yang dipakai, cara pasang MCP & allowlist, cara matikan toolset berbahaya, RAM, dan token per giliran. Hasilnya menentukan ADR-0005 tetap (satu bot) atau pindah ke rencana cadangan.
- [ ] AC5.2 Hermes tidak menerima token bot Telegram maupun API key OpenAI (cek config + test startup).
- [ ] AC5.3 Setiap request LLM Hermes (percakapan, tool call, retry, internal) melewati gateway dan tercatat di ledger dengan `source=hermes`. Request saat budget habis ditolak gateway tanpa diteruskan.
- [ ] AC5.4 Gateway memaksa batas `max_tokens` dan meng-commit biaya dari `usage`. Timeout setelah request terkirim di-commit sebesar reservasi.
- [ ] AC5.5 MCP server lulus contract test; tidak ada tool approve/reject/budget/ekspor.
- [ ] AC5.6 `MockDirector` "nakal" yang mencoba melewati gate gagal.
- [ ] AC5.7 Teks bebas di Studio Bot dijawab Director; tombol approval tetap ditangani Studio; tidak ada error 409.
- [ ] AC5.8 Konsumsi token Hermes per episode diukur; proyeksi bulanan dimasukkan ke PRD §9 dan muat dalam alokasi OpenAI Rp60.000.

---

## Fase 6 — Adapter Provider Asli (Default Mati)

**Pekerjaan**
- Adapter OpenAI (dipakai gateway), Higgsfield (gambar/video), TTS terpilih + contract test dengan fixture rekaman.
- Spike Higgsfield (baca dokumentasi saja): endpoint, durasi/rasio, upload, ToS.
- Verifikasi ulang `pricing.yaml` dan kurs.
- **Hitung ulang alokasi** dengan biaya VPS aktual (`studio budget recalc`) dan minta persetujuan owner.
- Gate izin berbayar: `docs/spikes/paid-smoke-test.md` (rencana, batas biaya, tanda setuju owner).

**Acceptance Criteria**
- [ ] AC6.1 Dengan `PAID_PROVIDERS_ENABLED=false`, adapter asli tidak pernah terpanggil.
- [ ] AC6.2 Adapter Higgsfield: auth benar, submit → simpan `request_id` → polling backoff → download → checksum; `failed`/`blocked`/timeout ditangani.
- [ ] AC6.3 Adapter OpenAI: structured output divalidasi; token & biaya tercatat.
- [ ] AC6.4 Semaphore konkuren + backoff untuk 429/5xx.
- [ ] AC6.5 Host keluar dibatasi allowlist.
- [ ] AC6.6 `pricing.yaml` terverifikasi < 30 hari; estimator menolak tabel yang lebih tua.
- [ ] AC6.7 Aktivasi berbayar ditolak sampai `vps.actual_usd` terisi, sama dengan `planned_usd`, dan rencana valid.
- [ ] AC6.8 Uji berbayar (kalau diizinkan) tidak melewati batas yang disetujui.

---

## Fase 7 — Kesiapan Production (Tanpa Deploy)

**Acceptance Criteria**
- [ ] AC7.1 Runbook bisa diikuti dari nol di container bersih.
- [ ] AC7.2 Backup lalu restore menghasilkan DB & file identik (checksum).
- [ ] AC7.3 RAM studio + Hermes + 1 render ≤ 3,5 GB (diukur).
- [ ] AC7.4 Benchmark render 180 detik diulang di spesifikasi VPS target, dan hasilnya dibandingkan dengan acuan 10 menit (**bukan jaminan**).
- [ ] AC7.5 Proyeksi biaya bulanan (VPS aktual + API) ≤ Rp500.000 dan config sesuai.
- [ ] AC7.6 Checklist keamanan lulus.
- [ ] AC7.7 Deployment **tidak dilakukan** sampai ada perintah terpisah dari owner.

---

## Definition of Done (semua fase)

- Kode mengikuti `CLAUDE.md`.
- Test baru untuk setiap perilaku baru; semua test offline.
- ruff, mypy, import-linter, pytest hijau.
- Dokumen terkait diperbarui.
- Tidak ada secret di git, tidak ada panggilan berbayar.
