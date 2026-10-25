# Audit Teknis Fase 1 — 03:AM

| | |
|---|---|
| Tanggal | 2026-10-25 |
| Branch | `claude/phase-1-core` |
| Basis audit | commit `0919e3a` (hasil Fase 1 sebelum audit) |
| Lingkup | job queue, budget guard, approval G0–G3, quality gates, acceptance criteria Fase 1 |
| Di luar lingkup | Fase 2+ (tidak disentuh), API berbayar, deployment, publikasi |

Aturan yang dipakai: sebuah AC hanya dianggap terpenuhi kalau **perilakunya dibuktikan oleh test** yang lulus, bukan sekadar karena class/fungsinya ada. Selain itu, setiap perbaikan diuji balik dengan *mutation check*: perbaikannya sengaja dirusak, lalu dipastikan ada test yang gagal.

---

## 1. Ringkasan

- **12 bug/celah diperbaiki**: 3 tingkat tinggi, 5 sedang, 4 rendah (rinciannya di §3).
- **Test**: 137 → **198**, semua lulus di Python 3.12 dan 3.13. Coverage pernyataan **96%**.
- **Mutation check**: 9 mutasi sengaja dibuat pada perbaikan audit, dan **semuanya tertangkap** test.
- **Batasan tetap dijaga**: anggaran Rp500.000 dan kurs 17.850 tidak diubah. Tidak ada kode Fase 2, API berbayar, deploy, atau publikasi.

## 2. Hasil Quality Gates

| Gate | Perintah | Hasil |
|---|---|---|
| Lint | `uv run ruff check .` | All checks passed |
| Format | `uv run ruff format --check .` | 73 file sudah terformat |
| Typecheck | `uv run mypy` (strict, `src/`) | Success, 44 file, 0 isu |
| Batas modul | `uv run lint-imports` | 1 kontrak dijaga, 0 dilanggar |
| Test | `uv run pytest -v` | **198 passed, 0 failed, 0 skipped** |
| Test Python 3.13 | `uv run --python 3.13 … pytest` | 198 passed |
| Coverage | `coverage run -m pytest` (alat sementara, tidak jadi dependensi) | 96% (2262 pernyataan, 93 tidak tercakup) |
| GitHub Actions | workflow `CI`, matrix 3.12/3.13 | lihat §7 (diverifikasi setelah push, tidak diklaim di muka) |

## 3. Bug & Celah yang Diperbaiki

| ID | Tingkat | Area | Masalah | Perbaikan | Bukti test |
|---|---|---|---|---|---|
| **S1** | Tinggi | Job queue | `_assert_lease()` tidak memeriksa `lease_until`, jadi worker yang lease-nya sudah kedaluwarsa tetap bisa `complete()`/`fail()` (terbukti dengan skrip reproduksi). Selain itu tidak ada fencing, sehingga worker yang di-restart dengan ID sama tidak bisa dibedakan dari pemegang lease sebelumnya. | Migrasi `0002`: kolom `lease_token` yang naik setiap kali klaim. `complete`/`fail` sekarang berupa satu `UPDATE` bersyarat (`status, lease_owner, lease_token, lease_until > now`), tanpa celah *check-then-act*. Reaper ikut menaikkan token. | `test_expired_lease_cannot_complete_even_if_not_reclaimed`, `test_stale_worker_cannot_finish_after_reclaim`, `test_restarted_worker_with_same_id_is_fenced`, `test_slow_handler_past_lease_is_rolled_back_and_redone_once`, `test_concurrent_claims_never_hand_out_a_job_twice` |
| **S2** | Tinggi | Approval | `EpisodeService.transition()` bisa dipanggil langsung (jalur service internal) untuk keluar dari gate tanpa approval apa pun. | Migrasi `0003`: trigger `episodes_gate_exit_requires_decision`. Keluar dari gate wajib punya keputusan owner yang tercatat untuk gate dan versi episode yang sama, dan jenis keputusannya harus cocok dengan arah transisi. | `test_gate_cannot_be_left_without_recorded_decision` (4 gate × 3 arah), `test_decision_of_one_kind_does_not_unlock_another_direction` |
| **S3** | Tinggi | Budget | `authorize_episode()` hanya memeriksa actor owner. Pemanggil internal bisa membuat otorisasi produksi dari approval yang masih `pending`, dengan batas berapa pun. | Trigger: otorisasi episode wajib berasal dari approval G0/G2 berstatus `approved`, batasnya ≤ batas approval, tidak bisa dinaikkan, dan tidak bisa dihidupkan lagi. Otorisasi operasional wajib punya periode aktif. | `test_episode_authorization_requires_approved_matching_approval`, `test_episode_authorization_cannot_exceed_or_be_raised_or_revived` |
| **S4** | Sedang | Budget/Hermes | Hermes bisa belanja memakai otorisasi produksi episode, kategori non-`openai`, atau purpose bebas (biaya *background* bisa lolos tanpa label). | Guard: `source=hermes` wajib kategori `openai` + otorisasi operasional + purpose ∈ `conversation`/`tool_call`/`retry`/`background`. | `test_hermes_cannot_use_episode_budget_or_other_categories`, `test_every_hermes_purpose_is_metered_in_openai_allocation`, `test_studio_and_hermes_share_one_openai_allocation` |
| **S5** | Sedang | Budget | Idempotency key hanya dicocokkan dengan nominal + otorisasi. Key yang sama untuk kategori/sumber/purpose/mode/episode lain diam-diam mengembalikan entri yang salah. Selain itu, `spend()` dengan key yang sudah `released` mengembalikan entri itu seolah-olah biaya sudah tercatat. | `SpendRequest.same_spend_as()` membandingkan semua field. Key yang sudah dilepas → `ConflictError`. | `test_same_key_for_different_spend_is_conflict` (5 varian), `test_released_key_cannot_be_reused`, `test_concurrent_same_key_spends_only_once` |
| **S6** | Sedang | Budget | ID otorisasi yang tidak dikenal memicu `NotFoundError` (bukan penolakan budget), sehingga tidak tercatat di audit. | Diperlakukan sebagai penolakan "otorisasi tidak dikenal" dan dicatat di audit. | `test_denied_without_known_authorization` |
| **S7** | Sedang | CLI | `--actor telegram:<id>` diterima, jadi orang dengan akses shell bisa menyamar sebagai owner Telegram. | CLI hanya menerima owner `cli:<nama>`, dan tetap harus ada di allowlist. | `test_cli_cannot_impersonate_other_channels`, `test_cli_owner_must_still_be_allowlisted` |
| **R1** | Sedang | Worker | Penandaan job `failed` dan hook dead-letter (episode → `FAILED`) ditulis di dua transaksi terpisah. Kalau hook gagal, episode macet di status kerja tanpa job. | Gagal permanen + hook (termasuk jalur `reap_exhausted`) sekarang berada dalam satu transaksi. | `test_dead_letter_hook_is_atomic_with_job_failure` |
| **S8** | Rendah | Audit | Penolakan approve G2 karena anggaran kurang tidak tercatat. Penolakan budget di dalam handler job ikut hilang saat rollback. | G2: dicatat lalu di-raise setelah commit. Job: `on_job_dead` mencatat `job.dead` beserta pesan error, di transaksi yang sama dengan penandaan gagal. | asersi audit di `test_cost_approval_refused_when_budget_insufficient`, `test_budget_denial_fails_episode_without_retry` |
| **S9** | Rendah | Budget | Overrun hanya berupa flag, tanpa event audit. | Audit `budget.overrun` (reservasi, aktual, kelebihan). Sisa anggaran bisa negatif dan menahan belanja berikutnya. | `test_overrun_is_flagged_audited_and_blocks_further_spending` |
| **S10** | Rendah | Ledger | Entri ledger yang sudah selesai masih bisa diubah/dihapus di level DB, dan tipe integer belum dijaga DB. | Trigger: ledger final setelah `committed`/`released`, tidak bisa dihapus, nilai uang wajib `integer`. | `test_settled_ledger_entries_are_final_in_database`, `test_amounts_are_stored_as_sqlite_integers` |
| **R2** | Rendah | CLI | `sqlite3.Error` (misalnya "database is locked") muncul sebagai traceback mentah. | Ditangkap dan dilaporkan sebagai pesan biasa, exit code 1. | `test_database_errors_are_reported_without_traceback` |

### Mutation check (perbaikan dirusak sengaja → test harus gagal)

| Mutasi | Test yang gagal |
|---|---|
| Cek `lease_until > now` dihapus | 2 |
| Fencing token tidak dinaikkan saat klaim | 4 |
| Trigger gate dimatikan | 5 |
| Hermes boleh memakai otorisasi episode | 1 |
| Idempotency kembali ke versi lama (nominal saja) | 4 |
| Audit overrun dihapus | 1 |
| CLI boleh menyamar | 1 |
| Penolakan G2 tidak diaudit | 1 |
| (audit awal) cek owner di approval dihapus | 7 |

## 4. Verifikasi Poin Audit yang Diminta

**Job queue**: semua terpenuhi.
- Lease kedaluwarsa ditolak saat complete/fail.
- Worker lama ditolak setelah lease diambil worker lain.
- Klaim bersamaan (6 thread, masing-masing dengan koneksi sendiri, 30 job): tidak ada job yang dibagikan dua kali. Diulang 20× tanpa flaky.
- Crash worker: efeknya di-rollback lalu dipulihkan tepat sekali.
- Recovery tetap idempoten (`test_crash_mid_stage_has_no_double_effects`).

**Budget guard**: semua terpenuhi.
- Kurs 17.850 dari config dan tersimpan di setiap entri.
- Rp500.000 sudah termasuk VPS Rp169.575, dan yang bisa dibelanjakan hanya Rp275.000.
- Rupiah berupa integer, dijaga di tiga lapis: tipe Python, test AST, dan trigger DB.
- Reservasi atomik (`BEGIN IMMEDIATE`).
- 6 thread × 10 percobaan → tepat 10 lolos, sama dengan alokasi.
- Overrun tercatat dan diaudit.
- Mode `real` ditolak tanpa kill switch dan syarat aktivasi berbayar.
- Semua purpose Hermes masuk alokasi `openai` yang sama dengan Studio.

**Approval**: semua terpenuhi.
- Hanya owner di allowlist yang bisa memutuskan, termasuk saat allowlist kosong.
- Director, system, dan owner palsu ditolak di 4 gate × 3 keputusan.
- Token hanya sekali pakai, ikut berganti saat diterbitkan ulang, terikat ke satu approval, dan tidak menggantikan cek owner.
- Kartu lama mati setelah revisi atau konten berubah.
- Approval kedaluwarsa ditolak.
- Klik ganda dari 6 koneksi → 1 keputusan, 1 transisi, 1 job. Approve G2 dari 4 koneksi → 1 otorisasi.
- Jalur service internal ditutup oleh trigger DB (S2/S3), dan CLI tidak bisa menyamar (S7).

## 5. Review Acceptance Criteria Fase 0 & 1

✅ = dibuktikan oleh test yang lulus · ⚠️ = terpenuhi dengan catatan · ⏳ = menunggu verifikasi eksternal

| AC | Status | Bukti / catatan |
|---|---|---|
| AC0.1 uv sync + pytest 3.12 & 3.13 | ✅ | lokal 3.12 & 3.13; CI matrix |
| AC0.2 ruff, format, mypy, lint-imports | ✅ | §2 |
| AC0.3 CI hijau | ✅ | run 40211487662 untuk `534b85e`, 3.12 & 3.13 (§7) |
| AC0.4 jaringan diblokir di test | ✅ | `test_network_is_blocked_in_tests` |
| AC0.5 redaksi secret di log | ✅ | `test_sensitive_keys_are_redacted`, `test_secret_values_from_env_are_scrubbed_everywhere` |
| AC0.6 `python -m studio --help` | ✅ | `test_module_help_runs` |
| AC0.7 tidak ada API key berbayar | ⚠️ | diverifikasi manual (grep repo + tidak ada adapter berbayar), bukan test otomatis |
| AC1.1 tabel transisi | ✅ | `test_transition_table_matches_spec_for_every_combination` (19×8×19) |
| AC1.2 satu transisi = satu audit | ✅ | `test_each_transition_writes_exactly_one_audit_entry`, flow penuh |
| AC1.3 audit append-only | ✅ | `test_audit_log_is_append_only` |
| AC1.4 WAL, FK, migrasi idempoten & checksum | ✅ | `tests/integration/test_db.py` |
| AC1.5 approval stale | ✅ | `test_changed_subject_makes_approval_stale`, `…version…`, `test_card_is_stale_when_content_changes_before_decision` |
| AC1.6 token terpakai/diganti/kedaluwarsa | ✅ | `test_token_is_single_use_and_rotates`, `test_rotated_token_and_expired_token_are_rejected` |
| AC1.7 non-owner tidak bisa memutuskan/aktivasi | ✅ | `test_only_allowlisted_owner_can_decide`, `test_privileged_services_reject_non_owner` |
| AC1.8 keputusan ganda sekali | ✅ | `test_double_decision_processed_once`, `test_concurrent_approvals_execute_once` |
| AC1.9 rencana default, kurs config, rencana invalid menolak | ✅ | `tests/unit/test_budget_plan.py`, `test_denied_when_live_plan_becomes_invalid` |
| AC1.10 VPS aktual ≠ rencana, usulan realokasi | ✅ | `test_vps_actual_*`, `test_reallocation_*` |
| AC1.11 tiap aturan penolakan guard | ✅ | `test_denied_*`, `test_real_mode_*` (cek total bulanan = lapisan cadangan yang tidak bisa dicapai tanpa melewati cek kategori lebih dulu) |
| AC1.12 property test pemakaian ≤ batas | ✅ | `test_usage_never_exceeds_allocation_or_authorization` (sekuensial) + `test_concurrent_requests_cannot_exceed_allocation` (konkuren) |
| AC1.13 kurs & versi harga tersimpan, tanpa float | ✅ | `test_reserve_commit_stores_fx_and_price`, `test_estimate_records_fx_and_pricing_version`, `test_no_float_in_money_code`, `test_amounts_are_stored_as_sqlite_integers` |
| AC1.14 pemakaian Hermes | ✅ | 4 test Hermes di `test_budget_guard.py` |
| AC1.15 approve G2 ditolak bila anggaran kurang | ✅ | `test_cost_approval_refused_when_budget_insufficient` |
| AC1.16 crash tanpa efek ganda | ✅ | `test_crash_mid_stage_has_no_double_effects`, `test_worker_crash_rolls_back_effects_and_recovers_once` |
| AC1.17 worker lama tidak bisa menyelesaikan job | ✅ | **sebelumnya hanya terpenuhi sebagian** (kasus lease kedaluwarsa = bug S1); sekarang dites |
| AC1.18 backoff → FAILED → retry; error budget tanpa retry | ✅ | `test_retry_with_exponential_backoff_then_dead`, `test_transient_failures_then_owner_retry`, `test_budget_denial_fails_episode_without_retry` |
| AC1.19 job usang → obsolete | ✅ | `test_stale_job_is_obsolete_without_effects` |
| AC1.20 revisi di G3 | ✅ | `test_revision_at_final_gate_invalidates_editorial_and_cost`, `test_old_cards_are_dead_after_revision` |
| AC1.21 DRAFT → EXPORTED lewat CLI | ✅ | `test_full_flow_via_cli_only` |
| AC1.22 PAID_PROVIDERS_ENABLED=true menolak start | ✅ | `test_paid_providers_flag_refuses_start` |
| AC1.23–AC1.29 (tambahan audit) | ✅ | lihat §3 & §4 |

**Yang belum terpenuhi:** tidak ada AC Fase 0/1 yang gagal. AC0.7 hanya bisa diverifikasi manual.

## 6. Technical Debt & Risiko yang Tersisa

| ID | Tingkat | Uraian | Kapan ditangani |
|---|---|---|---|
| **TD-01** | **Tinggi untuk Fase 2** | Handler job berjalan di dalam transaksi `BEGIN IMMEDIATE`, jadi selama handler jalan semua penulis lain (approval, CLI, Telegram nanti) menunggu. Aman untuk placeholder Fase 1 yang hanya butuh milidetik, tapi **tidak boleh** dipakai untuk panggilan LLM/provider. Fase 2 wajib memakai pola: reservasi + catat request (commit) → panggil provider di luar transaksi → selesaikan (commit), dengan idempotency key dan fencing token. | Desain awal Fase 2, **sebelum** handler sungguhan dibuat |
| TD-02 | Sedang | Belum ada *heartbeat*/perpanjangan lease. Job yang lebih lama dari lease (default 300 detik) selalu di-rollback dan diulang. Perlu ditambahkan sebelum render di Fase 4. | Fase 4 |
| TD-03 | Sedang | Penulis yang menunggu lebih dari `busy_timeout` (5 detik) mendapat "database is locked". Worker akan mencobanya lagi; CLI melaporkannya dengan rapi. Belum ada retry otomatis di level service. | Fase 3 (Telegram) |
| TD-04 | Rendah | Uji konkurensi memakai banyak thread dengan koneksi terpisah dalam satu proses, belum banyak proses OS. Mekanisme kuncinya sama (file lock SQLite), tapi belum dibuktikan lintas proses. | Fase 3/7 |
| TD-05 | Rendah | Identitas owner di CLI hanya dideklarasikan sendiri (`cli:<nama>`). Batas keamanannya adalah akses shell ke server + isi `.env`. Telegram (Fase 3) akan memakai user ID yang diverifikasi Telegram. | Fase 3, didokumentasikan |
| TD-06 | Rendah | Penolakan budget di dalam handler hanya tercatat lewat `job.dead` (pesan error), bukan entri `budget.denied` tersendiri, karena transaksi handler di-rollback. | Bersamaan dengan TD-01 |
| TD-07 | Rendah | Kedaluwarsa approval dievaluasi saat diputuskan (*lazy*). Approval yang sudah lewat waktu masih terlihat `pending` di daftar sampai ada yang mencoba memutuskannya. | Fase 3 (kartu Telegram menampilkan status) |
| TD-08 | Rendah | Trigger keamanan `0003` sengaja menghubungkan tabel lintas modul (episodes ↔ approvals, spend_authorizations ↔ approvals/budget_periods) sebagai pertahanan berlapis. Mengubah skema approval harus ikut memperbarui trigger ini. | Terdokumentasi di CLAUDE.md |
| TD-09 | Rendah | Harga di `config/pricing.yaml` masih placeholder belum terverifikasi; biaya simulasi hanya indikatif. | Fase 6 |
| TD-10 | Rendah | Revisi setelah G2 menagih ulang semua aset (simulasi). Pemakaian ulang shot yang tidak berubah baru ada di Fase 4. | Fase 4 |
| TD-11 | Rendah | Urutan ULID monoton hanya dijamin dalam satu proses. Antar-proses, urutannya per milidetik. | Diterima |
| TD-12 | Info | `mypy` hanya dijalankan untuk `src/`, tidak untuk `tests/`. Branch default GitHub masih `claude/planning-docs`. | Keputusan owner |
| TD-13 | Rendah | CI memakai `actions/checkout@v4` dan `astral-sh/setup-uv@v6` yang menargetkan Node.js 20 (deprecated; GitHub memaksanya jalan di Node 24). Perlu dinaikkan ke major terbaru setelah versinya diverifikasi. | Sebelum Fase 2 / kapan saja |

## 7. GitHub Actions

Diverifikasi lewat GitHub API setelah push (bukan diasumsikan):

| Run | Commit | Job | Hasil |
|---|---|---|---|
| [#3 — 40211487662](https://github.com/welldan23/03am/actions/runs/40211487662) | `534b85e` (perbaikan audit) | `check (3.12)` | ✅ success — log: `collected 198 items` … `198 passed in 4.89s` |
| | | `check (3.13)` | ✅ success |

Semua step lulus di kedua job: Install (`uv sync --locked`), Lint, Format, Typecheck, Batas modul, Test.

Catatan dari log CI: ada warning *"Node.js 20 is deprecated"* untuk `actions/checkout@v4` dan `astral-sh/setup-uv@v6` (lihat TD-13). Warning ini tidak menggagalkan build.

Commit laporan ini (hanya dokumen) ikut memicu CI. Statusnya dilaporkan terpisah di ringkasan akhir.

## 8. Rekomendasi

**Phase 1 layak ditutup**, dengan dua syarat:

1. ~~CI GitHub Actions hijau untuk commit hasil audit~~ ✅ terpenuhi (§7).
2. **TD-01 jadi keputusan desain pertama Fase 2**, sebelum ada handler yang memanggil LLM/provider (meskipun mock).

Tidak ada temuan tingkat tinggi yang masih terbuka di lingkup Fase 1.
