# Rencana Pengembangan — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.1 — menunggu review |
| Dokumen terkait | [PRD.md](PRD.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [RISKS.md](RISKS.md) |

## Aturan Main Semua Fase

- Development di Claude Code Cloud. **Tidak ada deployment production.**
- **Tidak ada API berbayar** sampai owner memberi izin tertulis (lihat Fase 6).
- Semua integrasi luar memakai **mock** sebagai default.
- Tiap fase selesai = semua acceptance criteria (AC) lulus + CI hijau + dokumen terkait diperbarui + direview owner.
- Fase dikerjakan berurutan. Fase berikut baru dimulai setelah owner menyetujui fase sebelumnya.

## Peta Fase

| Fase | Nama | Hasil utama | Butuh biaya? |
|---|---|---|---|
| 0 | Fondasi & spike | Repo skeleton, CI, spike Hermes (lokal, tanpa biaya) | Tidak |
| 1 | Inti domain | Episode + state machine, approval, budget ledger, job queue, CLI | Tidak |
| 2 | Pipeline konten (mock LLM) | Discovery → research → fact check → script → storyboard | Tidak |
| 3 | Telegram Studio Bot | Approval G0–G3 lewat tombol, status, budget | Tidak (bot Telegram gratis) |
| 4 | Aset, TTS, render, ekspor (mock) | Video MP4 utuh dari aset mock + paket ekspor | Tidak |
| 5 | Hermes AI Director | MCP server studio + skill Director + Director Bot | Tidak (LLM Hermes diarahkan ke endpoint mock) |
| 6 | Adapter provider asli (dimatikan) | Adapter OpenAI, Higgsfield, TTS + contract test | Tidak; uji berbayar **hanya** dengan izin owner |
| 7 | Kesiapan production (tanpa deploy) | Runbook VPS, backup, monitoring, hardening | Tidak |

Status MVP = Fase 0–5 selesai: satu episode bisa dibuat lengkap lewat Telegram dengan mock, biaya nyata Rp0.

---

## Fase 0 — Fondasi & Spike

**Tujuan:** proyek siap dikerjakan dengan disiplin sejak hari pertama, dan asumsi terbesar (Hermes) sudah diuji.

**Pekerjaan**
- `pyproject.toml` (uv), struktur folder sesuai ARCHITECTURE §4, `src/studio/__main__.py`.
- Tooling: ruff, mypy, pytest (+ `pytest-socket` untuk blokir jaringan), import-linter.
- `shared/`: config (pydantic-settings), logging (structlog + redaksi secret), ids (ULID), clock, money.
- `.env.example`, `.gitignore` (`data/`, `.env`), README.
- CI GitHub Actions: lint, format check, typecheck, test.
- **Spike Hermes** (`docs/spikes/hermes.md`): install di container, sambungkan ke MCP server dummy (1 tool `ping`), arahkan LLM ke endpoint OpenAI-compatible **mock lokal**, catat versi, RAM, cara matikan toolset berbahaya, cara allowlist tool MCP, dan apakah dua bot Telegram berjalan bersamaan tanpa konflik.
- **Spike Higgsfield (baca saja)** (`docs/spikes/higgsfield.md`): catat endpoint model kandidat, payload, durasi/rasio yang didukung, alur upload, harga, ToS — **tanpa** membuat API key berbayar.
- ADR-0001 s/d ADR-0008 ditulis singkat di `docs/adr/`.

**Acceptance Criteria**
- [ ] AC0.1 `uv sync` lalu `uv run pytest` lulus di mesin bersih (Python 3.12 dan 3.13).
- [ ] AC0.2 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`, `uv run lint-imports` semua lulus.
- [ ] AC0.3 CI hijau di GitHub untuk commit terakhir.
- [ ] AC0.4 Test yang mencoba akses jaringan otomatis gagal (dibuktikan dengan satu test negatif).
- [ ] AC0.5 Logger tidak pernah mencetak nilai env yang namanya mengandung `TOKEN`, `KEY`, `SECRET` (ada test).
- [ ] AC0.6 `python -m studio --help` jalan.
- [ ] AC0.7 `docs/spikes/hermes.md` menjawab: versi, cara pasang MCP, cara allowlist tool, cara matikan terminal/file tool, RAM idle, hasil uji dua bot, dan rekomendasi final Opsi A/B.
- [ ] AC0.8 `docs/spikes/higgsfield.md` berisi tabel model kandidat (endpoint, durasi, rasio, harga, `verified_at`) dan ringkasan ToS.
- [ ] AC0.9 Tidak ada API key berbayar yang dibuat atau dipakai.

---

## Fase 1 — Inti Domain

**Tujuan:** tulang punggung yang menjamin aturan bisnis: status, approval, uang, job.

**Pekerjaan**
- `infra/db`: koneksi SQLite (WAL, `busy_timeout`, foreign keys), migrator SQL bernomor, unit of work.
- `modules/episodes`: agregat Episode, tabel transisi, `episode_events`.
- `modules/approvals`: gate G0–G3, `subject_hash`, token sekali pakai, cek `actor`.
- `modules/budget`: `pricing.yaml` loader, estimator, ledger (reserve/commit/release), batas per episode/bulan/provider, kill switch.
- `infra/jobs`: antrean dengan lease, retry + backoff, idempotency key.
- `modules/workflow`: event → enqueue job; gate = berhenti.
- `interfaces/cli`: `studio episode new|show|list`, `studio approve <gate> <episode>`, `studio budget`, `studio worker`.

**Acceptance Criteria**
- [ ] AC1.1 Semua transisi legal di tabel transisi punya test; transisi ilegal melempar `IllegalTransition` (test berbasis tabel).
- [ ] AC1.2 Setiap transisi menulis tepat satu baris `episode_events` dengan actor, waktu UTC, status lama/baru.
- [ ] AC1.3 Approval dengan `subject_hash` lama ditolak setelah konten berubah.
- [ ] AC1.4 Token approval yang sudah dipakai atau kedaluwarsa ditolak.
- [ ] AC1.5 Actor bertipe `director`/`system` **tidak bisa** approve gate mana pun (test).
- [ ] AC1.6 `BudgetGuard.reserve` menolak bila: kill switch mati untuk provider berbayar, tidak ada approval G2 yang valid, sisa approval kurang, batas bulanan terlampaui, atau batas provider terlampaui — masing-masing punya test.
- [ ] AC1.7 Ledger konsisten: total `COMMITTED + RESERVED` tidak pernah > batas (property-based test dengan Hypothesis).
- [ ] AC1.8 Uang selalu integer; tidak ada `float` di modul budget (cek mypy/ruff rule atau test).
- [ ] AC1.9 Worker yang di-kill di tengah job: job diambil ulang setelah lease habis dan tidak dieksekusi dua kali untuk idempotency key yang sama.
- [ ] AC1.10 Revisi naskah setelah `COST_APPROVED` membatalkan approval G2 dan mengembalikan episode ke tahap yang benar.
- [ ] AC1.11 CLI bisa membawa episode dari `DRAFT` sampai `AWAITING_EDITORIAL` dengan handler job dummy.

---

## Fase 2 — Pipeline Konten (Mock LLM)

**Tujuan:** tahap 1–5 workflow menghasilkan artefak yang benar strukturnya, tanpa LLM sungguhan.

**Pekerjaan**
- `providers/llm`: `LLMPort`, `MockLLM`, `LLMRouter` (tier `fast`/`smart`, cache, validasi Pydantic, retry JSON).
- `providers/sources`: `SourcePort`, `MockSources` dengan 3 topik contoh (1 sejarah, 1 sains, 1 misteri).
- `prompts/` versi pertama untuk tiap tahap (Bahasa Indonesia).
- Modul `discovery`, `research`, `factcheck`, `scripting`, `storyboard` + job handler.
- Style bible awal di `config/styles/`.

**Acceptance Criteria**
- [ ] AC2.1 Discovery menghasilkan 3–5 kandidat valid (schema) dengan label risiko.
- [ ] AC2.2 Dossier menyimpan sumber lengkap (URL, judul, penerbit, tanggal akses).
- [ ] AC2.3 Klaim kritis dengan < 2 sumber independen berstatus `belum terverifikasi`.
- [ ] AC2.4 Episode dengan klaim kritis `belum terverifikasi` tidak bisa masuk `AWAITING_EDITORIAL`, kecuali override owner yang tercatat.
- [ ] AC2.5 Naskah untuk target 30/60/180 detik punya jumlah kata dalam rentang ±10% dari `durasi × 2,5`.
- [ ] AC2.6 Total durasi storyboard = durasi narasi ± 1 detik; durasi shot `ai_video` di-snap ke nilai yang didukung config.
- [ ] AC2.7 Jumlah shot `ai_video` ≤ batas per episode (default 3).
- [ ] AC2.8 Output LLM yang rusak (JSON invalid) di-retry 1×, lalu job `FAILED` dengan pesan jelas — tidak crash.
- [ ] AC2.9 Router memilih tier sesuai tabel tugas; panggilan identik kedua kali diambil dari cache (0 biaya simulasi tambahan).
- [ ] AC2.10 Fixture sumber yang berisi "instruksi jahat" tidak mengubah perilaku pipeline (test prompt-injection).
- [ ] AC2.11 Revisi naskah membuat versi baru; versi lama tetap bisa dibaca.

---

## Fase 3 — Telegram Studio Bot

**Tujuan:** owner bisa mengendalikan studio dan memberi approval dari Telegram.

**Pekerjaan**
- `interfaces/telegram` dengan aiogram 3: auth allowlist, perintah (`/start`, `/new`, `/status`, `/episodes`, `/budget`, `/cancel`, `/help`), kartu approval + tombol inline, form revisi, notifikasi progres.
- Semua teks bot di satu file (`texts_id.py`), Bahasa Indonesia santai.
- Pengujian handler dengan update Telegram palsu (tanpa jaringan).
- Uji manual opsional dengan bot token asli (gratis) di sesi cloud singkat.

**Acceptance Criteria**
- [ ] AC3.1 Pesan dari user di luar allowlist diabaikan dan tercatat di log (tanpa membalas isi apa pun).
- [ ] AC3.2 Kartu G0 menampilkan kandidat topik; memilih satu memindahkan episode ke `TOPIC_SELECTED`.
- [ ] AC3.3 Kartu G1 menampilkan ringkasan naskah, jumlah shot, dan ringkasan cek fakta; dokumen lengkap terlampir sebagai file.
- [ ] AC3.4 Kartu G2 menampilkan estimasi per kategori, total Rupiah, kurs, sisa budget bulan ini, dan batas maksimum.
- [ ] AC3.5 Tombol lama (konten sudah berubah atau token terpakai) membalas "kadaluarsa" dan tidak mengubah apa pun.
- [ ] AC3.6 Klik ganda pada tombol yang sama hanya diproses sekali.
- [ ] AC3.7 "Revisi" meminta catatan, lalu membuat versi baru di tahap yang dipilih.
- [ ] AC3.8 `/budget` menampilkan pemakaian bulan ini (simulasi + nyata dipisah).
- [ ] AC3.9 Bot tetap responsif saat worker sedang menjalankan job panjang.

---

## Fase 4 — Aset, TTS, Render & Ekspor (Mock)

**Tujuan:** episode menghasilkan video MP4 sungguhan dari aset mock.

**Pekerjaan**
- `providers/image`, `providers/video`, `providers/tts`: port + mock (lihat ARCHITECTURE §9.3). `MockVideo` meniru status async `queued → in_progress → completed`.
- `modules/assets`: generate per shot lewat `BudgetGuard`, download, checksum, regenerasi per shot.
- `modules/voice`: TTS + timing per kalimat.
- `modules/render`: timeline → `infra/ffmpeg` (Ken Burns, xfade, ducking, loudnorm, subtitle ASS, label AI, preview).
- `modules/export`: paket ekspor (PRD §7.8).
- Asset lokal gratis: `text_card` dan `map` sederhana.

**Acceptance Criteria**
- [ ] AC4.1 Episode mock 30 detik dan 180 detik ter-render menjadi MP4 1080×1920, 30 fps, H.264/AAC (dicek dengan `ffprobe`).
- [ ] AC4.2 Durasi video = durasi voice ± 0,5 detik.
- [ ] AC4.3 Loudness terintegrasi −14 LUFS ± 1 (dicek dengan filter `ebur128`).
- [ ] AC4.4 Subtitle muncul sesuai timing; tidak ada baris > 42 karakter.
- [ ] AC4.5 Preview ≤ 50 MB untuk video 180 detik.
- [ ] AC4.6 Tiap panggilan aset melewati `BudgetGuard` dan tercatat di ledger sebagai biaya simulasi.
- [ ] AC4.7 Worker di-kill saat `MockVideo` berstatus `in_progress`: setelah restart, polling dilanjutkan dengan `request_id` yang sama, tidak submit ulang.
- [ ] AC4.8 Regenerasi 1 shot tidak memanggil ulang shot lain (dibuktikan dari `provider_calls`).
- [ ] AC4.9 Ekspor hanya bisa untuk `FINAL_APPROVED`; paket berisi semua file wajib dan `manifest.json` valid.
- [ ] AC4.10 Test E2E: `DRAFT → EXPORTED` dengan mock penuh dan approval otomatis-test (actor owner palsu) lulus di CI dalam < 3 menit.
- [ ] AC4.11 Tidak ada kode upload ke platform sosial di mana pun (cek grep/test).

---

## Fase 5 — Hermes sebagai AI Director

**Tujuan:** owner bisa ngobrol dengan Director untuk menjalankan dan merevisi produksi, sementara approval tetap di Studio Bot.

**Pekerjaan**
- `interfaces/mcp`: MCP server stdio dengan tool di ARCHITECTURE §5.4 (`python -m studio mcp`).
- `hermes/config.example.yaml`: `mcp_servers.studio` + `tools.include` allowlist, toolset berbahaya dimatikan, allowlist Telegram.
- `hermes/skills/documentary-director/SKILL.md`: peran, gaya bahasa, alur, larangan.
- `director/`: `DirectorPort` + `MockDirector` dengan perilaku setara.
- LLM Hermes diarahkan ke endpoint OpenAI-compatible **mock** selama fase ini.

**Acceptance Criteria**
- [ ] AC5.1 MCP server lulus contract test: tiap tool punya schema input/output, error terstruktur, dan idempoten untuk `client_request_id` yang sama.
- [ ] AC5.2 Tidak ada tool approve/reject/ubah budget/ekspor di daftar tool MCP (test daftar tool).
- [ ] AC5.3 `MockDirector` "nakal" yang mencoba memindahkan episode melewati gate gagal dengan error yang jelas.
- [ ] AC5.4 Hermes (versi yang di-pin) bisa memanggil `studio_create_episode` dan `studio_get_episode` dalam uji manual; hasilnya dicatat di `docs/spikes/hermes.md`.
- [ ] AC5.5 Permintaan revisi lewat Director menghasilkan versi baru dan memunculkan kartu approval baru di Studio Bot.
- [ ] AC5.6 Studio Bot dan Director Bot jalan bersamaan tanpa error 409.
- [ ] AC5.7 Konsumsi token Hermes per episode diukur (via endpoint mock) dan dicatat; proyeksi biaya bulanan masuk PRD §9.

---

## Fase 6 — Adapter Provider Asli (Default Mati)

**Tujuan:** adapter siap pakai, tapi tidak ada uang keluar sampai owner memutuskan.

**Pekerjaan**
- `providers/llm/openai.py`, `providers/image/higgsfield.py`, `providers/video/higgsfield.py`, `providers/tts/<terpilih>.py`.
- Contract test dengan fixture respons rekaman (`respx`), tanpa jaringan.
- Verifikasi ulang `pricing.yaml` (harga, kurs, `verified_at`).
- Spike TTS Bahasa Indonesia (sampel dari opsi gratis/lokal lebih dulu).
- **Gate izin berbayar**: dokumen `docs/spikes/paid-smoke-test.md` berisi rencana uji, batas biaya maksimal (misal Rp25.000), dan tanda setuju owner.

**Acceptance Criteria**
- [ ] AC6.1 Dengan `PAID_PROVIDERS_ENABLED=false`, adapter asli tidak pernah terpanggil walau flag provider aktif (test).
- [ ] AC6.2 Adapter Higgsfield: auth header benar, submit → simpan `request_id` → polling dengan backoff → download → checksum; status `failed`/`blocked`/timeout ditangani (contract test).
- [ ] AC6.3 Adapter OpenAI: structured output divalidasi; token & biaya tercatat per panggilan.
- [ ] AC6.4 Setiap adapter punya semaphore konkuren dan backoff untuk 429/5xx.
- [ ] AC6.5 Host keluar dibatasi allowlist (test request ke host lain ditolak).
- [ ] AC6.6 `pricing.yaml` terverifikasi < 30 hari; estimator menolak tabel yang lebih tua.
- [ ] AC6.7 Uji berbayar (jika diizinkan owner) tidak melebihi batas yang disetujui dan hasilnya dicatat; jika tidak diizinkan, fase tetap dianggap selesai tanpa uji ini.

---

## Fase 7 — Kesiapan Production (Tanpa Deploy)

**Tujuan:** semuanya siap dipindah ke VPS kapan pun owner memutuskan.

**Pekerjaan**
- Runbook VPS (`docs/RUNBOOK.md`): spesifikasi, instalasi, systemd unit untuk studio, worker, Hermes gateway.
- Script backup/restore SQLite + `data/episodes`.
- Health check & laporan harian (Telegram).
- Retensi data: hapus aset mentah episode yang sudah diekspor > N hari.
- Review keamanan (secret, allowlist, toolset Hermes, host keluar).

**Acceptance Criteria**
- [ ] AC7.1 Runbook bisa diikuti dari nol di container bersih sampai studio jalan (diuji di sesi cloud, bukan VPS).
- [ ] AC7.2 Backup lalu restore menghasilkan DB & file identik (checksum).
- [ ] AC7.3 Total RAM studio + Hermes + render 1 job ≤ 3,5 GB (diukur).
- [ ] AC7.4 Render 180 detik ≤ 10 menit pada batas 2 vCPU (diukur dengan `taskset`/cgroup).
- [ ] AC7.5 Proyeksi biaya bulanan (VPS + API) ≤ Rp500.000 dan hard cap di config sesuai.
- [ ] AC7.6 Checklist keamanan lulus dan didokumentasikan.
- [ ] AC7.7 Deployment tetap **tidak dilakukan** sampai owner memberi perintah terpisah.

---

## Definition of Done (berlaku di semua fase)

- Kode mengikuti `CLAUDE.md`.
- Test baru untuk setiap perilaku baru; semua test offline.
- ruff, mypy, import-linter, pytest hijau.
- Dokumen terkait (PRD/ARCHITECTURE/RISKS/ADR) diperbarui bila ada keputusan baru.
- Tidak ada secret di git, tidak ada panggilan berbayar.
