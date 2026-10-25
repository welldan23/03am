# PRD — 03:AM · AI Documentary Studio

| | |
|---|---|
| Status | Draft v0.2 — revisi anggaran, satu bot Telegram, benchmark render, token Hermes |
| Pemilik produk | Owner 03:AM (1 orang) |
| Tanggal | 2026-10-25 |
| Dokumen terkait | [ARCHITECTURE.md](ARCHITECTURE.md) · [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) · [RISKS.md](RISKS.md) · [ADR](adr/README.md) |

> 03:AM adalah project baru, **terpisah total dari VORSA**. Tidak ada kode, database, bot, atau konfigurasi yang dipakai bersama.

---

## 1. Ringkasan

03:AM adalah studio produksi dokumenter AI yang **semi-otonom** dan dikendalikan lewat **Telegram**. Studio ini membuat video dokumenter pendek bergaya cinematic, **berbahasa Indonesia**, durasi **30–180 detik**, dengan tema:

- sejarah
- geopolitik
- sains
- geografi
- misteri

Di dalam lima kategori episode itu, topik dipetakan ke **8 kategori topik**: sejarah dunia, geografi, geopolitik, sains & teknologi, misteri sejarah, peradaban kuno, fenomena alam, dan fakta unik.

Ada tiga **format** episode:

| Format | Durasi | Default | Cocok untuk |
|---|---|---|---|
| **Quick Files** | 30–45 detik | 40 detik | satu fakta mengejutkan + konteks singkat |
| **The Archives** | 75–90 detik | 80 detik | satu kisah utuh dengan konflik dan penjelasan |
| **Deep Files** | 120–180 detik | 135 detik | topik berlapis, banyak sumber, ada perdebatan |

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
| G2 | Biaya terkendali | Total biaya operasional production ≤ **Rp500.000/bulan** termasuk VPS, LLM (termasuk Hermes), TTS, dan video; **0 rupiah** keluar tanpa persetujuan |
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
- **FR-TG-07 (P1)** Ngobrol bebas dengan AI Director (Hermes) **di bot yang sama**: teks bebas diteruskan ke Director, sedangkan tombol approval dan perintah ditangani Studio secara deterministik (ADR-0005). Contoh: "hook-nya bikin lebih misterius".
- **FR-TG-09 (P0)** Hanya ada **satu** bot Telegram, dan hanya proses Studio yang melakukan polling. Hermes tidak diberi token bot.
- **FR-TG-08 (P1)** Ringkasan harian: episode berjalan + sisa budget.

### 7.2 Topic discovery

- **FR-TD-01 (P0)** Hasilkan 3–5 kandidat topik per permintaan, sesuai kategori.
- **FR-TD-02 (P0)** Tiap kandidat punya label risiko sensitivitas (`rendah`/`sedang`/`tinggi`) + alasannya, tingkat keterverifikasian, kategori topik, dan saran format.
- **FR-TD-03 (P1)** Cegah topik duplikat dengan episode lama (pencocokan judul/kata kunci).
- **FR-TD-04 (P2)** Saran topik terjadwal (misal tiap Senin) — tetap menunggu pilihan manusia.

### 7.3 Research & fact checking

- **FR-RS-01 (P0)** Semua sumber tercatat: URL, judul, penerbit, tanggal akses, jenis sumber.
- **FR-RS-02 (P0)** Konten dari sumber diperlakukan sebagai **data**, bukan instruksi (anti prompt-injection). Sumber yang berisi pola instruksi tersembunyi dikarantina dan tidak dihitung sebagai bukti.
- **FR-RS-03 (P0)** Output AI **bukan** sumber. Kutipan bukti harus ada persis di teks sumber; kutipan, URL, nama peneliti, atau referensi yang dikarang ditolak.
- **FR-RS-04 (P0)** Sumber dinilai kualitasnya (tier 1 arsip/jurnal … tier 5 blog/forum). Artikel yang mengutip sumber lain tidak dihitung sebagai sumber independen.
- **FR-FC-01 (P0)** Ekstrak klaim faktual dari naskah (tanggal, angka, nama, hubungan sebab-akibat).
- **FR-FC-02 (P0)** Klaim kritis butuh ≥ 2 sumber independen agar `terverifikasi`.
- **FR-FC-02a (P0)** Setiap klaim masuk satu kategori: **fakta terverifikasi**, **interpretasi**, **hipotesis**, **diperdebatkan**, atau **belum terverifikasi**. Riset dengan < 3 fakta terverifikasi tidak lanjut ke naskah.
- **FR-FC-03 (P0)** Naskah **tidak boleh** memakai klaim `belum terverifikasi`. Naskah yang melanggar tidak bisa masuk G1, kecuali owner override secara eksplisit dengan alasan (tercatat di audit log dan terlihat di kartu G1). Klaim yang belum terverifikasi boleh tetap ada di brief sebagai pertanyaan terbuka.
- **FR-FC-04 (P0)** Klaim `diperdebatkan` wajib ditulis dengan bahasa yang jujur ("menurut sebagian sejarawan…").

### 7.4 Script & storyboard

- **FR-SC-01 (P0)** Durasi target mengikuti format (Quick Files / The Archives / Deep Files); durasi narasi dihitung dari jumlah kata ÷ kecepatan baca (default 150 kata/menit, bisa diatur).
- **FR-SC-01a (P0)** Struktur naskah wajib: hook → konteks → konflik/pertanyaan → penjelasan → penutup. Setiap kalimat faktual merujuk ke klaim di brief.
- **FR-SC-01b (P0)** Editorial gate otomatis sebelum G1: memeriksa rujukan klaim, angka, bahasa untuk klaim yang diperdebatkan/hipotesis, panjang, gaya sensasional, kutipan panjang, dan salinan teks sumber. Gagal → AI merevisi sekali → kalau masih gagal, episode berhenti dengan laporan revisi. **AI tidak bisa approve G1.**
- **FR-SC-02 (P0)** Naskah berversi; revisi membuat versi baru, versi lama tetap tersimpan.
- **FR-SB-01 (P0)** Total durasi shot = durasi narasi ± 1 detik.
- **FR-SB-02 (P0)** Durasi shot video AI di-"snap" ke durasi yang didukung model (misal 5/10 detik).
- **FR-SB-03 (P0)** Strategi visual hemat: default `ai_image` + gerakan kamera (Ken Burns); `ai_video` hanya untuk shot "hero" (dibatasi per episode).
- **FR-SB-04 (P1)** Style bible per kategori (palet warna, mood, lensa) supaya visual konsisten.

### 7.5 Biaya & persetujuan

- **FR-CO-01 (P0)** Estimasi biaya per item (LLM, gambar, video, TTS) dalam **integer Rupiah**. Setiap estimasi dan transaksi menyimpan **kurs yang dipakai** dan versi tabel harga.
- **FR-CO-02 (P0)** Panggilan provider berbayar **mustahil** terjadi tanpa otorisasi belanja aktif yang lahir dari keputusan manusia (aktivasi periode, G0, atau G2 — lihat ADR-0010).
- **FR-CO-03 (P0)** Batas berlapis: per otorisasi, per kategori per bulan (`higgsfield`, `openai`, `tts`), dan total yang bisa dibelanjakan per bulan. Pengeluaran baru yang melebihi sisa anggaran **ditolak**.
- **FR-CO-04 (P0)** Ledger biaya: reservasi → realisasi → pelepasan sisa.
- **FR-CO-05 (P0)** Kill switch global: `PAID_PROVIDERS_ENABLED=false` (default).
- **FR-CO-06 (P0)** Mock provider tetap mengeluarkan "biaya simulasi" (dicatat terpisah dari biaya nyata) supaya alur biaya teruji tanpa uang sungguhan.
- **FR-CO-07 (P1)** Laporan biaya bulanan: per episode, per kategori, per sumber (`studio`/`hermes`).
- **FR-CO-08 (P0)** **Seluruh** konsumsi OpenAI dihitung, termasuk Hermes: percakapan, setiap putaran tool call, retry, dan proses latar belakang (`background`: ringkasan, memori, skill, cron). Hermes tidak memegang API key; semua panggilan lewat gateway metering Studio (ADR-0009).
- **FR-CO-09 (P0)** Kurs, biaya VPS, dan alokasi ada di `config/budget.yaml` (tidak di-hardcode). Kalau biaya VPS aktual berbeda dari rencana, alokasi **wajib dihitung ulang dan disetujui** sebelum API berbayar bisa diaktifkan.
- **FR-CO-10 (P0)** Cadangan tidak bisa dibelanjakan langsung. Memakai cadangan berarti owner mengubah alokasi.

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
| NFR-04 | Performa | **Benchmark awal** (bukan jaminan): render video 180 detik selesai ≤ 10 menit di VPS 2 vCPU / 4 GB RAM. Hasil diukur dan dicatat; kalau meleset, profil render (preset, resolusi preview) disesuaikan |
| NFR-05 | Sumber daya | Seluruh stack (studio + Hermes) jalan di VPS 4 GB RAM |
| NFR-06 | Testability | Semua test jalan **tanpa internet** dan **tanpa API key** |
| NFR-07 | Observability | Log terstruktur (JSON), ID episode & job di setiap baris log |
| NFR-08 | Portabilitas | Python 3.12+, FFmpeg ≥ 6, SQLite ≥ 3.40, Linux |
| NFR-09 | Data | Backup SQLite + folder episode bisa dilakukan dengan 1 perintah |

## 9. Model Biaya

Semua angka di bawah ada di `config/budget.yaml` dan bisa diubah tanpa mengubah kode. Rupiah dicatat sebagai **integer**; konversi USD → IDR dibulatkan ke atas.

**Asumsi kurs perencanaan: USD/IDR = 17.850** (`fx.usd_idr`, dengan tanggal & sumber).

| Pos | USD | Rupiah / bulan | Catatan |
|---|---|---|---|
| VPS (referensi) | 9,50 | **169.575** | `vps.planned_usd`. VPS belum dibeli; biaya aktual diisi di `vps.actual_usd` |
| Higgsfield (gambar + video) | — | **190.000** | Video dihargai per detik; mayoritas shot pakai gambar diam + gerak kamera |
| OpenAI API (**termasuk Hermes**) | — | **60.000** | Percakapan, tool call, retry, dan proses internal Hermes ikut dihitung |
| TTS | — | **25.000** | Opsi gratis/lokal tetap dievaluasi dulu |
| Cadangan | — | **55.425** | Untuk fluktuasi kurs & selisih harga; **tidak bisa dibelanjakan langsung** |
| **Total** | | **500.000** | = `monthly_budget_idr` |

Aturan:
1. `ceil(VPS_USD × kurs) + Σ alokasi ≤ Rp500.000`. Kalau lewat (misalnya kurs naik), rencana tidak valid dan semua belanja baru ditolak sampai owner menyesuaikan alokasi.
2. Kalau biaya VPS aktual berbeda dari rencana, jalankan `studio budget recalc --vps-usd <aktual>`. Hasilnya **usulan** (selisih diambil dari cadangan dulu, kalau kurang baru dari alokasi lain secara proporsional) yang harus disetujui owner. API berbayar tidak bisa diaktifkan sebelum ini selesai.
3. Belanja bulanan butuh periode yang diaktifkan owner. Periode menyimpan snapshot alokasi & kurs.
4. Batas tambahan (bisa diubah di config):
   - otorisasi operasional (percakapan Hermes + discovery): Rp20.000/bulan, bagian dari alokasi OpenAI;
   - pra-produksi per episode (riset s/d storyboard): Rp5.000;
   - margin approval produksi (G2): 20% di atas estimasi.

Gambaran kasar (harga provider **belum diverifikasi**, dicek ulang di Fase 6): dengan tarif video sekitar $0,04–0,07/detik, Rp190.000 (≈ $10,6) setara ±150–265 detik video AI per bulan. Kalau tiap episode memakai 3 shot hero × 5 detik plus gambar diam, ada ruang untuk **±6–10 episode/bulan**. Target awal: **6–8 episode/bulan, rata-rata ≤ Rp30.000/episode** (di luar VPS).

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
| Biaya rata-rata per episode (setelah aktivasi) | ≤ Rp30.000 |

## 13. Pertanyaan Terbuka (butuh keputusan owner)

1. ~~Satu bot atau dua bot Telegram?~~ **Diputuskan: satu bot milik Studio** (ADR-0005). Dua bot jadi rencana cadangan kalau spike Hermes gagal.
2. **Provider TTS**: OpenAI TTS (berbayar, murah) vs opsi lokal/gratis — kualitas Bahasa Indonesia perlu diuji.
3. **Sumber musik latar** bebas royalti yang dipakai.
4. **Nama/branding** di video: watermark "03:AM" di pojok atau tidak?
5. **Reviewer kedua**: perlu sekarang atau nanti?
6. **Format tambahan** 16:9 untuk YouTube: masuk roadmap atau tidak?
