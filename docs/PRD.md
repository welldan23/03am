# PRD — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.1 — menunggu review |
| Pemilik produk | Owner 03:AM (1 orang) |
| Tanggal | 2026-10-25 |
| Dokumen terkait | [ARCHITECTURE.md](ARCHITECTURE.md) · [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) · [RISKS.md](RISKS.md) |

> 03:AM adalah project baru, **terpisah total dari VORSA**. Tidak ada kode, database, bot, atau konfigurasi yang dipakai bersama.

---

## 1. Ringkasan

03:AM adalah studio produksi dokumenter AI yang **semi-otonom** dan dikendalikan lewat **Telegram**. Studio ini membuat video dokumenter pendek bergaya cinematic, **berbahasa Indonesia**, durasi **30–180 detik**, dengan tema:

- sejarah
- geopolitik
- sains
- geografi
- misteri

AI mengerjakan bagian berat (cari topik, riset, cek fakta, tulis naskah, susun storyboard, bikin aset, sulih suara, render). Manusia tetap jadi **pemimpin redaksi dan pemegang dompet**: setiap pengeluaran dan setiap hasil akhir **wajib disetujui manusia**.

**Hermes Agent** (open-source, Nous Research) berperan sebagai **AI Director**: teman ngobrol yang mengarahkan produksi, menjelaskan progres, dan menerjemahkan permintaan revisi. Tapi Director **tidak punya wewenang** menyetujui biaya atau hasil akhir.

## 2. Masalah & Peluang

- Bikin dokumenter pendek yang akurat itu makan waktu: riset, verifikasi, naskah, visual, voice-over, editing.
- Tool AI yang ada terpisah-pisah dan biayanya gampang bocor (generate video berulang tanpa kontrol).
- Konten sejarah/geopolitik rawan salah fakta dan sensitif → butuh cek fakta dan persetujuan editorial yang jelas.

03:AM menyatukan semua langkah itu dalam satu alur yang **bisa diaudit**, **hemat**, dan **dikontrol manusia**.

## 3. Tujuan (Goals)

| ID | Tujuan | Ukuran keberhasilan |
|---|---|---|
| G1 | Produksi end-to-end dari Telegram | 1 episode bisa dibuat dari ide → file ekspor tanpa buka tool lain |
| G2 | Biaya terkendali | Total biaya operasional production ≤ **Rp500.000/bulan** termasuk VPS; **0 rupiah** keluar tanpa persetujuan |
| G3 | Akurasi | 100% klaim faktual di naskah punya status cek fakta + sumber tercatat |
| G4 | Kualitas cinematic | Video 9:16 1080×1920, subtitle, voice-over jelas, loudness konsisten (−14 LUFS) |
| G5 | Waktu manusia kecil | Waktu aktif manusia per episode ≤ 20 menit (baca, revisi, approve) |
| G6 | Tahan gagal | Proses bisa dilanjutkan setelah crash/restart tanpa bayar ulang aset yang sudah jadi |

## 4. Bukan Tujuan (Non-goals)

- ❌ Auto-publish ke Instagram (atau platform lain). Ekspor hanya menghasilkan paket file untuk di-upload manual.
- ❌ Deployment production pada tahap ini.
- ❌ Pemakaian API berbayar pada tahap awal (semua integrasi pakai **mock provider**).
- ❌ Multi-tenant / SaaS / banyak tim.
- ❌ Web dashboard (MVP cukup Telegram + CLI).
- ❌ Video panjang > 180 detik.
- ❌ Bahasa selain Indonesia (untuk narasi).
- ❌ Voice cloning orang sungguhan atau deepfake tokoh nyata.

## 5. Pengguna

| Persona | Peran | Kebutuhan |
|---|---|---|
| **Owner / Pemimpin Redaksi** | Satu orang, pemegang keputusan | Pilih topik, approve naskah, approve biaya, approve hasil akhir, lihat sisa budget |
| **Reviewer (opsional)** | Bantu baca naskah | Kasih catatan revisi; **tidak** bisa approve biaya |
| **AI Director (Hermes)** | Agen AI | Mengarahkan alur, memanggil tool studio, merangkum, menerima revisi bahasa natural |

Akses Telegram dibatasi **allowlist user ID**. Pengguna di luar allowlist diabaikan.

## 6. Alur Kerja Produksi

```
 ┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌────────┐   ┌────────────┐
 │1 Topic       │──▶│2 Research│──▶│3 Fact check  │──▶│4 Script│──▶│5 Storyboard│
 │  discovery   │   └──────────┘   └──────────────┘   └────────┘   └─────┬──────┘
 └──────┬───────┘                                                        │
   [G0 pilih topik]                                                      ▼
                                                          ┌─────────────────────────┐
                                                          │6 EDITORIAL APPROVAL  [G1]│
                                                          └────────────┬────────────┘
                                                                       ▼
                                                          ┌─────────────────────────┐
                                                          │7 COST APPROVAL       [G2]│
                                                          └────────────┬────────────┘
                                                                       ▼
 ┌──────────┐   ┌───────────────────────┐   ┌─────────┐   ┌──────┐   ┌─────────────────┐
 │12 Export │◀──│11 FINAL APPROVAL  [G3]│◀──│10 Render│◀──│9 TTS │◀──│8 Asset generation│
 └──────────┘   └───────────────────────┘   └─────────┘   └──────┘   └─────────────────┘
```

Setiap gate (G0–G3) bisa menghasilkan: **Setuju**, **Minta revisi** (balik ke tahap tertentu dengan catatan), atau **Tolak** (episode ditutup).

### 6.1 Rincian tiap tahap

| # | Tahap | Input | Output | Siapa |
|---|---|---|---|---|
| 1 | **Topic discovery** | Kategori (opsional), ide bebas dari owner, kalender peristiwa | 3–5 kandidat topik: judul kerja, angle/hook, alasan menarik, tingkat risiko sensitivitas, estimasi durasi | AI → owner memilih (**G0**) |
| 2 | **Research** | Topik terpilih | Dossier: ringkasan, timeline, tokoh/tempat, daftar sumber (URL, judul, tanggal akses, tingkat kepercayaan) | AI |
| 3 | **Fact checking** | Dossier | Daftar klaim + status `terverifikasi` / `diperdebatkan` / `belum terverifikasi`, minimal 2 sumber independen untuk klaim kritis | AI |
| 4 | **Script** | Dossier + hasil cek fakta + durasi target | Naskah narasi Bahasa Indonesia (hook 0–3 detik, isi, penutup), jumlah kata sesuai durasi (~2,5 kata/detik, dikalibrasi nanti), judul, caption | AI |
| 5 | **Storyboard** | Naskah | Daftar shot: durasi, potongan narasi, jenis visual (`ai_video`, `ai_image`, `archival`, `map`, `text_card`), prompt visual, gerakan kamera, teks layar | AI |
| 6 | **Editorial approval (G1)** | Naskah + storyboard + laporan cek fakta | Keputusan owner | **Manusia** |
| 7 | **Cost approval (G2)** | Estimasi biaya per item + sisa budget bulan ini | Keputusan owner + batas maksimum biaya | **Manusia** |
| 8 | **Asset generation** | Storyboard + approval biaya | Gambar/video per shot, disimpan lokal + checksum | AI (provider) |
| 9 | **TTS** | Naskah final | File voice-over + timing per kalimat (untuk subtitle) | AI (provider) |
| 10 | **Rendering** | Aset + voice + musik + subtitle | Video master + preview kecil | FFmpeg |
| 11 | **Final approval (G3)** | Preview video + ringkasan biaya aktual | Keputusan owner | **Manusia** |
| 12 | **Export** | Video yang disetujui | Paket ekspor (lihat §7.8) | Sistem |

## 7. Kebutuhan Fungsional

Prioritas: **P0** = wajib MVP, **P1** = penting setelah MVP, **P2** = nanti.

### 7.1 Telegram interface

- **FR-TG-01 (P0)** Hanya user ID di allowlist yang bisa memakai bot.
- **FR-TG-02 (P0)** Perintah dasar: `/start`, `/new` (episode baru), `/status`, `/episodes`, `/budget`, `/cancel <id>`, `/help`.
- **FR-TG-03 (P0)** Setiap gate approval tampil sebagai pesan ringkas + tombol inline `✅ Setuju` / `✏️ Revisi` / `❌ Tolak`.
- **FR-TG-04 (P0)** Tombol approval **sekali pakai** dan terikat ke versi konten (kalau naskah berubah, tombol lama mati).
- **FR-TG-05 (P0)** Notifikasi progres tiap tahap selesai/gagal.
- **FR-TG-06 (P0)** Kirim preview video (≤ 50 MB, batas upload Bot API) dan dokumen naskah/storyboard/laporan fakta.
- **FR-TG-07 (P1)** Ngobrol bebas dengan AI Director (Hermes) untuk revisi: "hook-nya bikin lebih misterius".
- **FR-TG-08 (P1)** Ringkasan harian: episode berjalan + sisa budget.

### 7.2 Topic discovery

- **FR-TD-01 (P0)** Hasilkan 3–5 kandidat topik per permintaan, sesuai kategori.
- **FR-TD-02 (P0)** Tiap kandidat punya label risiko sensitivitas (`rendah`/`sedang`/`tinggi`) + alasannya.
- **FR-TD-03 (P1)** Cegah topik duplikat dengan episode lama (pencocokan judul/kata kunci).
- **FR-TD-04 (P2)** Saran topik terjadwal (misal tiap Senin) — tetap menunggu pilihan manusia.

### 7.3 Research & fact checking

- **FR-RS-01 (P0)** Semua sumber tercatat: URL, judul, penerbit, tanggal akses, jenis sumber.
- **FR-RS-02 (P0)** Konten dari sumber diperlakukan sebagai **data**, bukan instruksi (anti prompt-injection).
- **FR-FC-01 (P0)** Ekstrak klaim faktual dari naskah (tanggal, angka, nama, hubungan sebab-akibat).
- **FR-FC-02 (P0)** Klaim kritis butuh ≥ 2 sumber independen agar `terverifikasi`.
- **FR-FC-03 (P0)** Episode **tidak bisa** masuk G1 kalau masih ada klaim kritis `belum terverifikasi`, kecuali owner override secara eksplisit (tercatat di audit log).
- **FR-FC-04 (P0)** Klaim `diperdebatkan` wajib ditulis dengan bahasa yang jujur ("menurut sebagian sejarawan…").

### 7.4 Script & storyboard

- **FR-SC-01 (P0)** Durasi target 30–180 detik; jumlah kata dihitung otomatis.
- **FR-SC-02 (P0)** Naskah berversi; revisi membuat versi baru, versi lama tetap tersimpan.
- **FR-SB-01 (P0)** Total durasi shot = durasi narasi ± 1 detik.
- **FR-SB-02 (P0)** Durasi shot video AI di-"snap" ke durasi yang didukung model (misal 5/10 detik).
- **FR-SB-03 (P0)** Strategi visual hemat: default `ai_image` + gerakan kamera (Ken Burns); `ai_video` hanya untuk shot "hero" (dibatasi per episode).
- **FR-SB-04 (P1)** Style bible per kategori (palet warna, mood, lensa) supaya visual konsisten.

### 7.5 Biaya & persetujuan

- **FR-CO-01 (P0)** Estimasi biaya per item (LLM, gambar, video, TTS) dalam **Rupiah**, dengan kurs dan tanggal harga tercatat.
- **FR-CO-02 (P0)** Panggilan provider berbayar **mustahil** terjadi tanpa approval biaya yang masih berlaku.
- **FR-CO-03 (P0)** Batas: per episode, per bulan (hard cap), dan per provider. Lewat batas = berhenti + minta approval baru.
- **FR-CO-04 (P0)** Ledger biaya: reservasi → realisasi → pelepasan sisa.
- **FR-CO-05 (P0)** Kill switch global: `PAID_PROVIDERS_ENABLED=false` (default).
- **FR-CO-06 (P0)** Mock provider tetap mengeluarkan "biaya simulasi" supaya alur biaya teruji tanpa uang sungguhan.
- **FR-CO-07 (P1)** Laporan biaya bulanan: per episode, per provider.

### 7.6 Asset generation & TTS

- **FR-AS-01 (P0)** Aset disimpan lokal begitu jadi (provider seperti Higgsfield hanya menyimpan output ±7 hari).
- **FR-AS-02 (P0)** Regenerasi satu shot tanpa mengulang shot lain.
- **FR-AS-03 (P0)** Batas retry per shot (default 2) supaya tidak boros.
- **FR-AS-04 (P0)** Dilarang membuat wajah/kemiripan tokoh nyata dengan AI; gunakan siluet, arsip berlisensi, atau ilustrasi.
- **FR-TTS-01 (P0)** Voice-over Bahasa Indonesia + timing untuk subtitle.

### 7.7 Rendering

- **FR-RD-01 (P0)** Output utama 9:16, 1080×1920, 30 fps, H.264 + AAC.
- **FR-RD-02 (P0)** Subtitle Bahasa Indonesia ter-burn-in, pemenggalan baris rapi.
- **FR-RD-03 (P0)** Musik latar dengan ducking otomatis saat narasi; loudness −14 LUFS.
- **FR-RD-04 (P0)** Label "Dibuat dengan bantuan AI" (posisi dapat dikonfigurasi).
- **FR-RD-05 (P0)** Preview kecil (≤ 50 MB) untuk dikirim ke Telegram.
- **FR-RD-06 (P2)** Varian 16:9.

### 7.8 Export

- **FR-EX-01 (P0)** Hanya episode berstatus `FINAL_APPROVED` yang bisa diekspor.
- **FR-EX-02 (P0)** Paket ekspor berisi:
  - `video_master.mp4`, `video_preview.mp4`
  - `subtitles.srt`
  - `caption.txt` (caption + hashtag siap tempel)
  - `sources.md` (daftar sumber)
  - `thumbnail.jpg`
  - `manifest.json` (versi naskah, model yang dipakai, biaya aktual, jejak approval)
- **FR-EX-03 (P0)** **Tidak ada** upload otomatis ke platform mana pun.

### 7.9 Audit

- **FR-AU-01 (P0)** Setiap perubahan status, approval, override, dan panggilan provider tercatat (siapa, kapan, apa, berapa).

## 8. Kebutuhan Non-Fungsional

| ID | Kategori | Kebutuhan |
|---|---|---|
| NFR-01 | Biaya | Total ≤ Rp500.000/bulan (lihat §9) |
| NFR-02 | Keamanan | Secret hanya dari env; tidak pernah masuk log, git, atau prompt |
| NFR-03 | Keandalan | Job idempoten; restart tidak mengulang panggilan berbayar yang sudah sukses |
| NFR-04 | Performa | Render 180 detik ≤ 10 menit di VPS 2 vCPU / 4 GB RAM |
| NFR-05 | Sumber daya | Seluruh stack (studio + Hermes) jalan di VPS 4 GB RAM |
| NFR-06 | Testability | Semua test jalan **tanpa internet** dan **tanpa API key** |
| NFR-07 | Observability | Log terstruktur (JSON), ID episode & job di setiap baris log |
| NFR-08 | Portabilitas | Python 3.12+, FFmpeg ≥ 6, SQLite ≥ 3.40, Linux |
| NFR-09 | Data | Backup SQLite + folder episode bisa dilakukan dengan 1 perintah |

## 9. Model Biaya (perkiraan awal — wajib diverifikasi di Fase 6)

Asumsi: kurs **Rp16.500/USD** (disimpan di config, bukan di kode). Semua harga provider **harus dicek ulang** sebelum API berbayar diaktifkan.

| Pos | Alokasi / bulan | Catatan |
|---|---|---|
| VPS (2 vCPU, 4 GB) | ≤ Rp150.000 | Belum dibeli; tidak ada deploy di tahap ini |
| OpenAI (studio + Hermes) | ≤ Rp100.000 (~$6) | Hybrid routing: model murah untuk tugas ringan, model kuat hanya untuk naskah & cek fakta |
| Higgsfield (gambar + video) | ≤ Rp200.000 (~$12) | Video dihargai per detik; mayoritas shot pakai gambar diam + gerak kamera |
| TTS | ≤ Rp30.000 | Opsi gratis/lokal dievaluasi dulu |
| Cadangan | ≥ Rp20.000 | Untuk fluktuasi kurs & retry |
| **Total** | **≤ Rp500.000** | Hard cap di sistem diset sedikit di bawah ini |

Gambaran kasar: dengan tarif video sekitar $0,04–0,07/detik (angka publik 2026, belum diverifikasi), $12 ≈ 170–290 detik video AI per bulan. Kalau tiap episode memakai 3 shot hero × 5 detik, ada ruang untuk **±8–12 episode/bulan** setelah dikurangi biaya gambar. Target awal: **8 episode/bulan, rata-rata ≤ Rp35.000/episode** (di luar VPS).

## 10. Batasan

- Development di **Claude Code Cloud**; container sementara, tanpa server publik (tidak ada webhook masuk).
- Belum ada VPS → bot Telegram hanya dijalankan sesekali untuk uji coba, bukan 24/7.
- Tidak ada API berbayar; semua integrasi eksternal memakai mock sampai owner memutuskan lain.
- Tidak ada auto-publish Instagram.

## 11. Konten, Etika & Legal

- Label AI di video dan caption.
- Tidak ada deepfake / suara tiruan tokoh nyata.
- Topik geopolitik sensitif (konflik aktif, SARA) diberi label risiko `tinggi` dan butuh catatan editorial eksplisit di G1.
- Lisensi aset arsip (misal Wikimedia Commons) dicatat dan atribusinya masuk `sources.md`.
- Musik latar hanya dari sumber bebas royalti dengan lisensi tercatat.
- Syarat penggunaan komersial setiap provider dicek sebelum aktivasi berbayar.

## 12. Metrik Keberhasilan MVP

| Metrik | Target |
|---|---|
| Episode end-to-end dengan mock (tanpa biaya) | 100% sukses di test E2E |
| Pengeluaran tanpa approval | 0 |
| Klaim tanpa status cek fakta | 0 |
| Render sukses | ≥ 95% |
| Waktu aktif manusia per episode | ≤ 20 menit |
| Biaya rata-rata per episode (setelah aktivasi) | ≤ Rp35.000 |

## 13. Pertanyaan Terbuka (butuh keputusan owner)

1. **Satu bot atau dua bot Telegram?** Hermes punya gateway Telegram sendiri. Rekomendasi: dua bot (Studio Bot untuk approval yang pasti/deterministik, Director Bot untuk ngobrol dengan Hermes). Detail di ARCHITECTURE §5.
2. **Provider TTS**: OpenAI TTS (berbayar, murah) vs opsi lokal/gratis — kualitas Bahasa Indonesia perlu diuji.
3. **Sumber musik latar** bebas royalti yang dipakai.
4. **Nama/branding** di video: watermark "03:AM" di pojok atau tidak?
5. **Reviewer kedua**: perlu sekarang atau nanti?
6. **Format tambahan** 16:9 untuk YouTube: masuk roadmap atau tidak?
