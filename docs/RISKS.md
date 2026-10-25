# Risiko Integrasi — Hermes Agent & Higgsfield

| | |
|---|---|
| Status | Draft v0.2 — diperbarui untuk ADR-0005, ADR-0009, ADR-0010 |
| Skala | Dampak & Peluang: **T**inggi / **S**edang / **R**endah |
| Dokumen terkait | [ARCHITECTURE.md](ARCHITECTURE.md) · [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) |

> Fakta tentang Hermes dan Higgsfield di bawah diambil dari dokumentasi publik per Oktober 2026. Hal yang belum pasti ditandai **[verifikasi]** dan akan dicek lewat spike sebelum dipakai.

---

## 1. Hermes Agent (AI Director)

Yang sudah diketahui: Hermes Agent adalah agen open-source (MIT) dari Nous Research. Dia aplikasi utuh: punya CLI, gateway messaging (termasuk Telegram), memori, skills, cron, dan bisa memakai MCP server (`mcp_servers` di `~/.hermes/config.yaml`, transport stdio/HTTP, filter `tools.include/exclude`). Akses Telegram diatur lewat `TELEGRAM_ALLOWED_USERS` / DM pairing. Ada mode approval perintah (`smart`/`manual`/`off`) dan backend container (Docker, dll).

| ID | Risiko | Dampak | Peluang | Mitigasi | Cara verifikasi |
|---|---|---|---|---|---|
| **H-01** | **Hermes itu aplikasi, bukan library.** Menanamkannya langsung ke kode studio rapuh dan susah dites. | T | T | Hubungkan **hanya lewat MCP** (studio = MCP server). Domain studio tidak tahu Hermes ada. `DirectorPort` + `MockDirector` untuk test. | Spike Fase 0: Hermes memanggil 1 tool MCP dummy |
| **H-02** | **Project bergerak cepat** → perubahan config/CLI/perilaku antar versi. | S | T | Pin versi Hermes; catat versi di `docs/spikes/`; contract test terhadap kontrak MCP kita (bukan terhadap internal Hermes). | Cek changelog sebelum upgrade |
| **H-03** | **Konflik bot Telegram.** Satu token bot hanya bisa di-poll satu proses (error 409). | T | ~~T~~ R | **ADR-0005:** satu bot milik Studio; gateway Telegram Hermes tidak diaktifkan dan Hermes tidak pernah diberi token bot, sehingga konflik tidak mungkin terjadi. Studio memakai lock satu poller. | Spike Fase 5: Hermes jalan tanpa gateway |
| **H-04** | **Biaya token Hermes tidak terkontrol.** Loop agen, putaran tool call, retry, ringkasan memori, dan perbaikan skill otomatis semuanya memakai LLM. | T | S | **ADR-0009:** Hermes tidak memegang API key; semua request lewat gateway metering Studio → `BudgetGuard` (`source=hermes`, `purpose` per jenis). Request ditolak saat alokasi OpenAI Rp60.000 atau otorisasi operasional habis. `max_tokens` dipaksa. Model tier murah. Batas project OpenAI jadi pengaman kedua. | Spike Fase 5 + AC5.3/AC5.4; ledger sudah dites di Fase 1 (AC1.14) |
| **H-05** | **LLM mencoba approve / melompati gate.** | T | S | Tool approval tidak diekspos di MCP; service `approvals` cek `actor`; state machine menolak transisi ilegal. | Test: `MockDirector` "nakal" yang mencoba approve → harus gagal |
| **H-06** | **Prompt injection dari konten riset.** Teks web bisa menyuruh agen menjalankan perintah. | T | S | Matikan toolset terminal/file/eksekusi kode untuk Director; jalankan Hermes di backend Docker; konten sumber dibungkus sebagai data; allowlist tool MCP. | Test dengan fixture sumber berisi instruksi jahat |
| **H-07** | **Status ganda.** Memori Hermes bisa "ingat" status lama dan bertentangan dengan DB. | S | T | SQLite = sumber kebenaran; setiap tool MCP mengembalikan status terkini; skill Director wajib cek `studio_get_episode` sebelum bertindak. | Test E2E dengan status berubah di luar Hermes |
| **H-08** | **Skill berubah sendiri.** Hermes bisa membuat/mengedit skill otomatis → perilaku Director melenceng. | S | S | Skill `documentary-director` disimpan di repo; perubahan otomatis direview; matikan auto-edit bila ada opsinya **[verifikasi]**. | Diff skill tiap minggu |
| **H-09** | **Footprint memori di VPS 4 GB.** Hermes + studio + FFmpeg render bersamaan. | S | S | Ukur RAM di spike; render dibatasi 1 job sekaligus; swap kecil; jadwalkan render. | Spike: ukur RSS Hermes idle & aktif |
| **H-10** | **Approval command Hermes timeout (default 300 detik = ditolak)** dan mode headless default `deny`. | R | S | Studio tidak bergantung pada approval Hermes; tool MCP tidak butuh approval perintah shell. | Baca config di spike |
| **H-11** | **Uji di cloud dev tanpa VPS.** Proses perlu jalan terus. | R | T | Uji Hermes headless di container sesi singkat; produksi ditunda sampai VPS. | — |
| **H-13** | **Mode headless Hermes tidak stabil / berubah** (ADR-0005 bergantung padanya). | S | S | `DirectorPort` + contract test; pin versi; rencana cadangan dua bot dengan token berbeda. | Spike Fase 5 |
| **H-12** | **Dukungan provider OpenAI** dan format tool-calling dengan model pilihan **[verifikasi]**. | S | R | Uji di spike dengan endpoint OpenAI-compatible lokal (mock server) dulu, tanpa biaya. | Spike |

## 2. Higgsfield API (video & gambar)

Yang sudah diketahui: base URL `https://api.higgsfield.ai`, auth header `Authorization: Key <KEY_ID>:<KEY_SECRET>`. Request bersifat async: POST ke endpoint model → dapat `request_id`, `status_url`, `cancel_url` dengan status awal `queued`, lalu polling atau webhook. Payload berbeda per model. Media input harus URL publik atau di-upload ke storage Higgsfield. Output disimpan minimal ±7 hari. Billing API terpisah dari langganan aplikasi: saldo USD prabayar (min. top-up $5), video dihargai per detik output, gambar per gambar. Ada SDK Python & TypeScript.

| ID | Risiko | Dampak | Peluang | Mitigasi | Cara verifikasi |
|---|---|---|---|---|---|
| **G-01** | **Biaya video mendominasi budget.** Harga per detik × retry bisa menghabiskan alokasi Rp190.000 dengan cepat. | T | T | Strategi visual hemat (`ai_image` + Ken Burns default, maks 3 shot hero); batas retry per shot; ledger reservasi; approval biaya per episode. | Simulasi biaya dengan mock + tabel harga |
| **G-02** | **Harga berubah / berbeda per konfigurasi** (resolusi, audio, durasi). | S | T | `pricing.yaml` per model+konfigurasi dengan `verified_at`; margin estimasi 20%; estimasi ditolak kalau tabel harga > 30 hari tidak diverifikasi. | Cek halaman harga sebelum aktivasi |
| **G-03** | **Payload & katalog model spesifik per model** dan bisa berubah. | S | T | Satu adapter kecil per model di `providers/video/higgsfield.py`; model ID di config; contract test dengan fixture respons rekaman. | Baca docs tiap model yang dipakai |
| **G-04** | **Tidak ada URL publik untuk webhook** (dev di cloud, belum ada VPS). | R | T | Pakai polling dengan backoff + batas waktu; webhook opsional nanti. | — |
| **G-05** | **Job hilang saat restart** → submit ulang = bayar dua kali. | T | S | Simpan `request_id` segera setelah submit (sebelum polling); worker melanjutkan polling, bukan submit ulang; idempotency key per shot. | Test: kill worker di tengah polling |
| **G-06** | **Output kedaluwarsa (±7 hari).** | S | S | Download langsung saat `completed`, simpan checksum; jangan simpan URL sebagai satu-satunya referensi. | Test integrasi mock |
| **G-07** | **Input butuh URL publik / upload.** Gambar referensi lokal tidak bisa dikirim langsung. | S | T | Pakai endpoint upload Higgsfield **[verifikasi]**; jangan upload data pribadi. | Spike adapter (tanpa biaya: baca docs + fixture) |
| **G-08** | **Moderasi konten.** Topik perang, kekerasan, tokoh politik bisa ditolak / hasil disensor. | S | T | Aturan prompt: tanpa wajah tokoh nyata, tanpa gore; fallback otomatis ke `archival`/`text_card`; status `blocked` dicatat terpisah dari `failed`. | Kumpulkan kasus saat uji berbayar terbatas |
| **G-09** | **Hasil jelek tetap dibayar.** | S | T | Review visual hero shot di G3; batas regenerasi; preview gambar dulu sebelum image-to-video (gambar lebih murah). | — |
| **G-10** | **Durasi & rasio terbatas** per model (misal 5/10 detik, rasio tertentu). | S | T | Storyboard men-snap durasi shot ke nilai yang didukung; potong di FFmpeg. | Docs per model |
| **G-11** | **Konsistensi visual antar shot** (gaya, warna, karakter). | S | T | Style bible per kategori; prompt prefix tetap; seed tetap jika didukung **[verifikasi]**; color grading seragam di FFmpeg (LUT). | Uji visual |
| **G-12** | **Batas konkuren/rate limit** (disebut 20 request konkuren). | R | R | Semaphore di adapter (default 2); backoff pada 429. | — |
| **G-13** | **Pembayaran USD & kurs.** Kartu internasional, kurs berubah. | S | S | Kurs di `config/budget.yaml` (asumsi 17.850), disimpan di tiap estimasi & entri ledger; rencana yang melewati Rp500.000 karena kurs naik otomatis tidak valid; cadangan Rp55.425; top-up kecil ($5). | AC1.9 |
| **G-14** | **Hak penggunaan komersial / ToS** belum jelas untuk konten yang di-upload ke Instagram. | T | S | Baca ToS sebelum aktivasi berbayar; catat ringkasannya di `docs/spikes/higgsfield.md`. | Fase 6 gate |
| **G-15** | **Vendor lock-in.** | S | S | Port `VideoProvider` / `ImageProvider` generik; Higgsfield hanya salah satu adapter. | — |

## 3. Risiko Umum Lain

| ID | Risiko | Mitigasi |
|---|---|---|
| U-01 | Salah fakta pada topik sejarah/geopolitik | Cek fakta ≥2 sumber, G1 wajib, `sources.md` di ekspor |
| U-02 | Topik sensitif (SARA, konflik aktif) | Label risiko di discovery, catatan editorial wajib untuk risiko `tinggi` |
| U-03 | Kualitas TTS Bahasa Indonesia kurang natural | Spike perbandingan beberapa TTS; kamus pelafalan (nama asing) |
| U-04 | Preview > 50 MB (batas upload Bot API) | Preview 540p bitrate rendah; master tidak dikirim lewat Telegram |
| U-05 | Data hilang (container dev sementara) | Commit & push rutin; `data/` hanya untuk dev; backup script nanti di VPS |
| U-06 | Biaya total melewati Rp500.000 | Yang bisa dibelanjakan hanya alokasi variabel (Higgsfield 190.000 + OpenAI 60.000 + TTS 25.000 = Rp275.000). VPS Rp169.575 dan cadangan Rp55.425 tidak bisa dibelanjakan. Validasi rencana, kill switch, dan laporan harian ikut menjaga (ADR-0010) |
| U-08 | Biaya VPS aktual berbeda dari asumsi USD 9,50 | `vps.actual_usd` + `studio budget recalc`; aktivasi berbayar diblokir sampai alokasi disetujui ulang |
| U-09 | Render 180 detik lebih lambat dari 10 menit di VPS kecil | Diperlakukan sebagai benchmark, bukan jaminan; diukur di Fase 4 & 7; setel preset/resolusi; render dibatasi 1 job sekaligus |
| U-07 | Lisensi musik & arsip | Hanya sumber bebas royalti, atribusi otomatis |
