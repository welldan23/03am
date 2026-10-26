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
| 1 | Inti domain | State machine, approval, budget, ledger, job queue, audit, CLI | ✅ selesai + audit teknis ([laporan](reviews/phase-1-audit.md)), disetujui owner |
| 2 | Research & script engine (mock LLM) | Discovery → research → fact check → naskah 3 format → editorial gate | ✅ selesai ([laporan](reviews/phase-2-implementation.md)), disetujui owner |
| 3 | Telegram Studio Bot (1 bot) | Approval G0–G3 lewat tombol, percakapan, notifikasi, budget | ✅ selesai ([laporan](reviews/phase-3-implementation.md)) — **menunggu persetujuan owner** |
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
- [x] AC0.3 CI hijau di GitHub (Python 3.12 & 3.13, run pertama 2b7469b).
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
- [x] AC1.11 `BudgetGuard.reserve` menolak (masing-masing dites): mode real saat kill switch mati, mode real saat syarat aktivasi berbayar belum terpenuhi, rencana tidak valid, periode tidak aktif, otorisasi dicabut/milik periode atau episode lain/kurang, alokasi kategori kurang. Setiap penolakan tercatat di audit. (Cek total bulanan juga ada sebagai lapisan cadangan.)
- [x] AC1.12 Property test (hypothesis): pemakaian (committed + reserved) tidak pernah melewati alokasi kategori maupun batas otorisasi.
- [x] AC1.13 Setiap estimasi & entri ledger menyimpan kurs dan versi harga; uang selalu integer (test AST: tidak ada `float` di modul budget).
- [x] AC1.14 Pemakaian Hermes (percakapan, tool call, retry) tercatat dengan `source=hermes`, memotong alokasi `openai` yang sama dengan Studio, dan ditolak saat habis.
- [x] AC1.15 Approve G2 ditolak kalau batas produksi melebihi sisa alokasi.

*Job queue & workflow*
- [x] AC1.16 Worker crash di tengah job: setelah lease habis job diambil ulang, dan efeknya (artefak, ledger, transisi) tidak terjadi dua kali.
- [x] AC1.17 Worker yang lease-nya sudah diambil worker lain **atau sudah kedaluwarsa** tidak bisa menandai job selesai atau gagal (fencing token). *(Bug kedaluwarsa ditemukan & diperbaiki saat audit.)*
- [x] AC1.18 Error berulang → backoff → `FAILED`; `retry` melanjutkan dari status yang gagal. Error budget langsung `FAILED` tanpa retry.
- [x] AC1.19 Job yang usang (episode sudah direvisi/dibatalkan) ditandai `obsolete` tanpa efek.
- [x] AC1.20 Revisi di G3 ke `SCRIPTING` menggantikan approval G1 & G2, mencabut otorisasi produksi, dan mengembalikan episode ke `SCRIPTING`.
- [x] AC1.21 Lewat CLI saja, episode bisa dibawa dari `DRAFT` sampai `EXPORTED` dengan handler placeholder. Semua biaya tercatat sebagai `simulated`, dan biaya `real` = Rp0.
- [x] AC1.22 `PAID_PROVIDERS_ENABLED=true` membuat aplikasi menolak start.

*Tambahan dari audit teknis (lihat [laporan audit](reviews/phase-1-audit.md))*
- [x] AC1.23 Klaim job bersamaan dari banyak koneksi tidak pernah membagikan satu job dua kali; worker yang di-restart dengan ID sama tertolak oleh fencing token.
- [x] AC1.24 Reservasi anggaran bersamaan dari banyak koneksi tidak bisa melewati alokasi; idempotency key yang sama dari banyak koneksi hanya tercatat sekali; key yang sama untuk belanja berbeda ditolak.
- [x] AC1.25 Overrun tercatat (`overrun` + audit `budget.overrun`) dan menahan belanja berikutnya.
- [x] AC1.26 Database menolak keluar dari gate tanpa keputusan owner yang tercatat, dan menolak otorisasi belanja yang tidak lahir dari approval G0/G2 yang sah.
- [x] AC1.27 Keputusan approval bersamaan (klik ganda dari banyak koneksi) dieksekusi tepat sekali: satu transisi, satu job, satu otorisasi.
- [x] AC1.28 Hermes hanya bisa belanja `openai` lewat otorisasi operasional; semua purpose (`conversation`, `tool_call`, `retry`, `background`) memotong alokasi yang sama dengan Studio.
- [x] AC1.29 CLI tidak bisa menyamar sebagai owner kanal lain.

---

## Fase 2 — Research & Documentary Script Engine (Mock LLM)

**Pekerjaan** (selesai — detail di [laporan implementasi](reviews/phase-2-implementation.md))
- TD-01: eksekusi job dua fase (`Lease`, `heartbeat`, `finish`, `atomic`) — [ADR-0011](adr/0011-eksekusi-job-dua-fase.md).
- `modules/calls`: `MeteredCaller` + tabel `provider_calls` (idempotency, status `unknown`, tiket belanja) dan `LLMClient` (prompt file, `wrap_data`, validasi Pydantic, retry JSON 1×).
- `providers/llm` (`MockLLMProvider` berbasis fixture, bisa disuntik fault) dan `providers/sources` (`FixtureSourceLibrary`, 3 topik).
- `modules/research`: discovery, research plan, ekstraksi bukti, penilaian sumber (tier, skor, kelompok independen), anti prompt-injection, `FactChecker` deterministik → `ResearchBrief` + `ResearchQualityReport`.
- `modules/scripting`: format Quick Files / The Archives / Deep Files, timing dari WPM, `EditorialGate` deterministik, auto-revisi 1×, laporan revisi, override owner.
- CLI: `episode new --format`, `pipeline run`, `research show`, `script show`, `llm calls`, `episode override-editorial`.
- Storyboard sengaja **belum** dibuat (masih placeholder yang diturunkan dari segmen naskah) → Fase 4.

**Acceptance Criteria** (bukti = nama test)
- [x] AC2.1 Discovery menghasilkan 3–5 kandidat valid dengan label sensitivitas & keterverifikasian, dibayar dari otorisasi operasional. — `test_discovery_offers_labelled_candidates_before_g0`
- [x] AC2.2 Dossier menyimpan sumber lengkap (URL, judul, penerbit, tanggal publikasi, **tanggal akses**, asal fixture). — `test_krakatau_claims_are_classified_and_traceable`
- [x] AC2.3 Klaim kritis dengan < 2 kelompok sumber independen berstatus `belum terverifikasi` (artikel turunan tidak dihitung independen). — `test_critical_claim_needs_two_independent_groups`, `test_derived_and_same_origin_sources_are_not_independent`
- [x] AC2.4 *(dipertegas)* Klaim `belum terverifikasi` tidak boleh dipakai di naskah: editorial gate memblokir, episode tidak masuk `AWAITING_EDITORIAL` kecuali owner override dengan alasan tercatat. — `test_blocking_rules[unverified]`, `test_script_failing_twice_produces_revision_report`, `test_owner_override_moves_failed_script_to_g1`
- [x] AC2.5 *(diganti brief Fase 2)* Naskah ketiga format masuk rentangnya (30–45 / 75–90 / 120–180 s); timing dihitung dari WPM yang configurable; melebihi target +10% = blocking. — `test_scripts_fit_format_and_reach_editorial_gate`, `test_timing_uses_configured_words_per_minute`, `test_too_long_for_target_or_format_is_blocking`
- [ ] AC2.6 Total durasi storyboard = durasi narasi ± 1 detik; durasi `ai_video` di-snap. — **dipindah ke Fase 4** (storyboard engine belum dibuat).
- [x] AC2.7 Jumlah shot `ai_video` ≤ batas per episode (di storyboard placeholder). — `test_storyboard_is_derived_from_script_segments`
- [x] AC2.8 JSON rusak di-retry 1× (tercatat sebagai panggilan terpisah) lalu job `FAILED` dengan pesan jelas. — `test_invalid_json_retry_is_metered_separately`, `test_invalid_json_twice_fails_episode_with_clear_message`
- [x] AC2.9 Tiap task memakai tier dari `config/llm.yaml`; panggilan dengan key yang sama dipakai ulang tanpa biaya tambahan. — `test_each_task_is_routed_to_its_configured_tier`, `test_stale_worker_result_is_not_accepted_but_cost_is_reused`
- [x] AC2.10 Sumber fixture berisi instruksi jahat dikarantina dan tidak mengubah perilaku pipeline (tidak bisa approve, tidak masuk analisis klaim). — `test_prompt_injection_source_is_neutralized`, `test_all_prompts_wrap_untrusted_data`
- [x] AC2.11 Biaya pra-produksi per episode tidak melewati batas otorisasi G0 (Rp5.000); melebihi → `FAILED` + audit `budget.denied`. — `test_every_llm_operation_has_full_cost_trail`, `test_budget_denial_fails_episode_without_retry`

*Tambahan dari brief Fase 2*
- [x] AC2.12 Provider tidak pernah dipanggil saat SQLite write lock dipegang; handler berjalan di luar transaksi. — `test_provider_is_never_called_while_sqlite_write_lock_is_held`, `test_handler_runs_outside_any_transaction`, `test_external_work_inside_transaction_is_refused`
- [x] AC2.13 Timeout atau worker mati di tengah panggilan → `unknown`, biaya dicatat sebesar reservasi, **tidak** diulang otomatis. — `test_timeout_is_unknown_outcome_and_never_blindly_retried`, `test_crash_during_call_is_not_replayed_blindly`
- [x] AC2.14 Hasil dari worker basi (lease habis/diambil alih, episode berubah) tidak diterima. — `test_stale_worker_result_is_not_accepted`, `test_takeover_during_call_marks_unknown_and_stale_result_is_dropped`, `test_result_is_rejected_when_episode_changes_during_external_work`
- [x] AC2.15 Setiap operasi LLM punya estimasi token/biaya, otorisasi, idempotency key, dan ledger entry; tidak ada jalur provider yang melewati `BudgetGuard`. — `test_every_llm_operation_has_full_cost_trail`, `test_provider_rejects_calls_without_valid_ticket`, `test_no_authorization_means_provider_is_never_called`, `test_app_does_not_expose_raw_provider`
- [x] AC2.16 Kutipan, sumber, dan URL karangan model ditolak. — `test_source_hallucination_is_rejected`, `test_hallucinated_quote_unknown_source_and_url_are_rejected`
- [x] AC2.17 Klaim dikategorikan fakta terverifikasi / interpretasi / hipotesis / diperdebatkan / belum terverifikasi. — `test_hypothesis_and_interpretation_are_kept_separate`, `test_contradiction_makes_claim_disputed_but_tier5_cannot_dispute`, `test_other_topics`
- [x] AC2.18 Editorial gate memblokir pelanggaran fakta, struktur, panjang, sensasional, kutipan panjang, dan salinan teks sumber; gagal → auto-revisi 1× → laporan revisi. — `test_blocking_rules`, `test_failing_script_is_auto_revised_once`
- [x] AC2.19 AI tidak bisa approve G1 atau override editorial; review LLM yang "menyetujui" diabaikan. — `test_owner_override_moves_failed_script_to_g1`, `test_director_cannot_use_pipeline_to_approve_topic`
- [x] AC2.20 Alur Fase 2 bisa dijalankan dari CLI saja; seluruh regression test Fase 1 tetap lulus. — `test_phase2_pipeline_via_cli`, seluruh `tests/`

---

## Fase 3 — Telegram Studio Bot (satu bot)

**Pekerjaan** (selesai — detail di [laporan implementasi](reviews/phase-3-implementation.md), panduan di [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md))
- `modules/controller`: `StudioController` (fasad untuk antarmuka percakapan, cek owner di setiap metode), `ActionCodes` (kode tombol sekali pakai), `ConversationStore`, `UpdateLog` — [ADR-0012](adr/0012-antarmuka-telegram-dan-outbox.md).
- `modules/notifications`: outbox persisten, diisi trigger DB (migrasi `0005`).
- `interfaces/telegram` (aiogram 3.31): adapter, `StudioBot` (gerbang keamanan), `ConversationEngine`, `RuleBasedIntentParser` (port `IntentParser` untuk Hermes nanti), render + pagination, transport dengan retry, dispatcher notifikasi, runner long polling + worker thread + kunci poller tunggal.
- Revisi naskah lewat workflow (REVISE di G1 atau RETRY dengan catatan) → approval digantikan, versi naik, editorial gate ulang.
- CLI: `studio bot check`, `studio bot run`, `studio worker run --loop`.
- `DirectorPort`/Hermes **tidak** dibuat (Fase 5).

**Acceptance Criteria** (bukti = nama test di `tests/telegram/`)
- [x] AC3.1 Pesan dari user di luar allowlist tidak mendapat data apa pun dan tercatat di audit log (`telegram.unauthorized`, dibatasi). — `test_stranger_gets_nothing_and_is_audited`, `test_stranger_cannot_press_owner_buttons`
- [x] AC3.2 Kartu G0 menampilkan kandidat topik + batas biaya pra-produksi; memilih satu menjalankan riset. — `test_create_documentary_with_buttons`, `test_full_flow_to_g1_with_notifications`
- [x] AC3.3 *(dipertegas)* Kartu G1 menampilkan ringkasan naskah, durasi, status editorial gate, dan jumlah catatan; detail naskah & riset lewat tombol. Jumlah shot & lampiran dokumen → Fase 4 (storyboard masih placeholder). — `test_full_flow_to_g1_with_notifications`, `test_research_and_script_review_with_pagination`
- [x] AC3.4 Detail G2 menampilkan estimasi per kategori, total Rupiah, kurs, sisa anggaran per kategori, dan batas maksimum (label simulasi). — `test_g2_detail_shows_estimate_per_category_fx_and_remaining`
- [x] AC3.5 Tombol lama (konten berubah / kode terpakai / kedaluwarsa) ditolak tanpa efek. — `test_old_card_is_refused_after_content_is_revised`, `test_card_button_replay_is_refused`, `test_action_code_expires_after_ttl`
- [x] AC3.6 Klik ganda (termasuk dari banyak koneksi bersamaan) hanya diproses sekali. — `test_concurrent_double_click_executes_once`, `test_duplicate_telegram_update_is_processed_once`
- [x] AC3.7 Callback tombol tidak pernah diteruskan ke pemahaman teks (calon Director). — `test_callbacks_never_reach_the_text_intent_parser`, `test_decisions_are_never_taken_from_free_text`
- [x] AC3.8 `/budget` menampilkan pemakaian bulan ini: simulasi vs nyata, per sumber, kurs dari config. — `test_budget_dashboard_shows_plan_from_config`, `test_exchange_rate_comes_from_config_not_code`
- [x] AC3.9 Bot tetap responsif saat worker menjalankan job panjang. — `test_bot_stays_responsive_while_worker_runs_a_long_job`

*Tambahan dari brief Fase 3*
- [x] AC3.10 Hanya chat pribadi; identitas dari user ID numerik, bukan username. — `test_group_chats_are_ignored`, `test_identity_is_numeric_user_id_from_allowlist`
- [x] AC3.11 Controller menolak baca/tulis dari non-owner (termasuk Director), bukan hanya bot. — `test_controller_refuses_non_owner_reads_and_writes`
- [x] AC3.12 `callback_data` ≤ 64 byte, tanpa token/rahasia; kode terikat ke owner penerima; callback palsu ditolak. — `test_every_button_fits_callback_limit_and_carries_no_secrets`, `test_action_codes_are_bound_to_the_owner_who_received_them`, `test_forged_callbacks_are_refused`
- [x] AC3.13 Approval kedaluwarsa ditolak dan bot menawarkan terbit ulang. — `test_expired_approval_offers_reissue`
- [x] AC3.14 Revisi naskah lewat workflow resmi (approval digantikan, versi naik, editorial gate ulang). — `test_request_revision_via_buttons`, `test_old_card_is_refused_after_content_is_revised`, `test_failed_script_revision_goes_through_retry`
- [x] AC3.15 Percakapan natural (9 contoh brief) dikenali; maksud ambigu → bot bertanya. — `test_brief_examples_are_routed`, `test_ambiguity_asks_instead_of_guessing`, `test_episode_is_not_guessed_when_several_exist`
- [x] AC3.16 Notifikasi lewat outbox persisten: transaksional, selamat dari restart, tidak dobel ke penerima yang sama, retry/backoff, `retry_after` dihormati. — `tests/telegram/test_notifications.py`
- [x] AC3.17 Error Telegram (rate limit, timeout, jaringan, diblokir, pesan tak bisa diedit), SQLite busy, pesan > 4096 karakter, dan error internal ditangani tanpa traceback. — `tests/telegram/test_reliability.py`
- [x] AC3.18 Hanya satu poller per folder data; worker berhenti dengan rapi. — `test_only_one_poller_per_data_dir`, `test_worker_thread_stops_gracefully`
- [x] AC3.19 Token bot tidak muncul di repr, log structlog, maupun log standar (aiogram). — `test_bot_token_never_appears_in_logs_or_repr`
- [x] AC3.20 Semua test offline dengan fake transport; regresi Fase 1–2 tetap lulus. — seluruh `tests/`

*Hotfix reliability ([audit](reviews/phase-3-reliability-audit.md), [ADR-0013](adr/0013-pemrosesan-update-tahan-crash.md))*
- [x] AC3.21 Update tidak dianggap selesai sebelum aksi bisnis di-commit; aksi bisnis + status + balasan atomik; crash sebelum commit → diproses ulang, setelah commit → tidak dijalankan ulang. — `test_crash_before_commit_is_reprocessed_exactly_once`, `test_crash_after_commit_delivers_reply_without_rerunning_action`
- [x] AC3.22 Balasan yang belum terkirim dipulihkan dari outbox persisten; urutan pesan terjaga; duplikat update/callback tidak menggandakan efek; dua pemroses tidak bisa commit ganda (fencing token). — `tests/telegram/test_crash_recovery.py`

---

## Fase 4 — Aset, TTS, Render & Ekspor (Mock)

**Pekerjaan**
- `providers/image|video|tts`: port + mock. `MockVideo` meniru status async.
- `modules/storyboard` (dari Fase 2): shot list dari segmen naskah, snap durasi `ai_video`.
- `modules/assets`, `voice`, `render`, `export`.
- Skrip benchmark render (`scripts/bench_render.py`) + `docs/benchmarks/`.

**Acceptance Criteria**
- [ ] AC3.3b (dipindah dari Fase 3) Kartu G1 menampilkan jumlah shot storyboard; dokumen naskah/storyboard/laporan fakta dilampirkan sebagai file.
- [ ] AC2.6 (dipindah dari Fase 2) Total durasi storyboard = durasi narasi ± 1 detik; durasi `ai_video` di-snap ke nilai yang didukung.
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
- [ ] AC5.3 Setiap request LLM Hermes (percakapan, tool call, retry, background) melewati gateway dan tercatat di ledger dengan `source=hermes`. Request saat budget habis ditolak gateway tanpa diteruskan.
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
