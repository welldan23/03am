# Panduan Bot Telegram 03:AM (Fase 3)

Bot Telegram adalah **antarmuka utama** 03:AM. Bot hanya meneruskan perintah ke Studio Controller; semua keputusan, state machine, approval, dan anggaran tetap di Studio (SQLite = sumber kebenaran).

> Fase 3: semua AI masih **mock** dan semua biaya **simulasi**. Tidak ada API berbayar, tidak ada deploy, tidak ada publikasi Instagram.

## 1. Setup lokal

Butuh Python 3.12+ dan [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

### 1.1 Buat bot & ambil token

1. Buka [@BotFather](https://t.me/BotFather) di Telegram → `/newbot` → ikuti langkahnya.
2. Salin token (bentuknya `123456789:AA...`) ke `.env` Anda:
   ```
   STUDIO_TELEGRAM_BOT_TOKEN=123456789:AA...
   ```
3. **Jangan** taruh token di file yang di-commit. `.env` sudah ada di `.gitignore`. Token dibaca sebagai `SecretStr` dan disensor otomatis dari log.
4. Disarankan: di BotFather, matikan *Allow Groups* (`/setjoingroups` → Disable). Bot juga mengabaikan grup sendiri.

### 1.2 Cari user ID Telegram Anda (angka)

Bot mengenali owner dari **user ID numerik** (`from_user.id`), **bukan username** (username bisa diganti siapa saja).

Cara termudah:
- kirim pesan ke [@userinfobot](https://t.me/userinfobot), lalu salin angka `Id`; **atau**
- jalankan bot sekali, kirim `/start` dari akun Anda, lalu lihat log: `telegram.unauthorized user_id=123456789` (akun yang belum di allowlist ditolak dan dicatat).

Masukkan ke allowlist owner (boleh lebih dari satu, dipisah koma):
```
STUDIO_OWNER_IDS=cli:owner,telegram:123456789
```

### 1.3 Aktifkan periode anggaran

Discovery topik dibayar dari otorisasi operasional bulan berjalan. Aktifkan sekali per bulan (dari CLI, atau dari menu **💰 Budget → ▶️ Aktifkan periode** di bot):

```bash
uv run studio budget activate
```

### 1.4 Cek konfigurasi (tanpa jaringan)

```bash
uv run studio bot check
```

## 2. Menjalankan bot (long polling)

```bash
uv run studio bot run
```

Satu proses berisi: long polling aiogram, thread inti (semua akses database dari bot), dispatcher notifikasi, dan, secara default, **worker job** di thread terpisah dengan koneksi database sendiri.

- Berhenti: `Ctrl+C` (SIGINT) atau SIGTERM. Polling berhenti, dispatcher & worker diberi sinyal stop, koneksi database dan sesi HTTP ditutup.
- Hanya **satu** proses bot boleh berjalan per folder data (kunci `data/telegram-poller.lock`). Proses kedua ditolak supaya Telegram tidak membalas *409 Conflict*.

### 2.1 Worker terpisah (opsional)

Kalau ingin worker di proses lain (misalnya service systemd terpisah di VPS nanti):

```bash
# .env: STUDIO_TELEGRAM_RUN_WORKER=false
uv run studio bot run            # terminal 1
uv run studio worker run --loop  # terminal 2
```

Notifikasi tetap terkirim: worker menulis kejadian ke outbox SQLite, dispatcher bot mengeceknya setiap `STUDIO_NOTIFY_IDLE_SECONDS` (default 10 detik), dan langsung saat ada aksi di bot.

### 2.2 Mock pipeline tanpa Telegram

Seluruh alur juga bisa dicoba dari CLI (berguna untuk debugging):

```bash
uv run studio episode new --category sejarah --format archives
uv run studio pipeline run <EPISODE_ID>              # sampai G0
uv run studio pipeline run <EPISODE_ID> --topic 1    # owner pilih topik → riset → naskah → G1
uv run studio research show <EPISODE_ID>
uv run studio script show <EPISODE_ID>
```

### 2.3 Nanti di VPS (belum dilakukan di Fase 3)

`StudioBot.handle()` tidak tahu sumber update. Untuk webhook cukup ganti pemasok update (endpoint HTTPS yang meneruskan `Update` ke router aiogram). Perilaku keamanan, dedupe, outbox, dan state percakapan sama.

## 3. Cara pakai

| Perintah | Fungsi |
|---|---|
| `/start`, `/menu` | menu utama |
| `/help` | bantuan + contoh kalimat |
| `/status` | status produksi (episode yang diproses / gagal) |
| `/episodes` | episode aktif |
| `/budget` | dashboard anggaran bulan ini |
| `/cancel` | batalkan langkah percakapan yang sedang berjalan |

Menu: 🎬 Buat Dokumenter · 📂 Episode Aktif · 💡 Ide Topik · 🔎 Review Riset · 📝 Review Naskah · ✅ Approval · ⚙️ Status Produksi · 💰 Budget · 🛠 Pengaturan.

Teks bebas yang dikenali (router berbasis aturan, belum LLM):
- *Cari topik sejarah yang menarik* / *Buat dokumenter tentang Krakatau*
- *Pilih format 90 detik* (90 detik → The Archives; durasi di luar semua format → bot bertanya)
- *Tunjukkan hasil risetnya* · *Ringkas bagian pembuka* · *Apa sumber untuk klaim C-krak-sound?*
- *Naskahnya terlalu kaku, buat lebih natural* → kartu konfirmasi revisi (lewat workflow resmi)
- *Berapa estimasi biaya episode ini?* · *Tampilkan episode yang belum saya approve*

Aturan penting:
- **Keputusan approval hanya lewat tombol kartu.** Teks seperti "setujui saja" tidak pernah mengeksekusi apa pun.
- Kalau maksud ambigu (episode mana, format apa, klaim mana), bot **bertanya balik**, tidak menebak.
- Tombol aksi **sekali pakai** dan punya masa berlaku. Tombol dari kartu lama ditolak setelah konten berubah.

## 4. Contoh percakapan end-to-end

Transcript berikut dihasilkan dari bot asli (engine + controller + SQLite + mock provider) dengan *fake transport*. 👤 = pesan owner, 👆 = tombol yang ditekan, 🤖 = balasan bot, `(edit)` = pesan yang tombolnya ditekan diperbarui.

```text
👤 /start

🤖 🌙 03:AM — AI Documentary Studio
   Halo! Saya asisten studio. Pilih menu di bawah atau ketik saja, misalnya:
   • Cari topik sejarah yang menarik
   • Buat dokumenter tentang Krakatau, format 90 detik
   • Tampilkan episode yang belum saya approve
   
   ⚠️ Fase 3: semua AI & biaya masih simulasi (mock). Tidak ada API berbayar.
   [🎬 Buat Dokumenter] [📂 Episode Aktif] [💡 Ide Topik] [🔎 Review Riset] [📝 Review Naskah] [✅ Approval] [⚙️ Status Produksi] [💰 Budget] [🛠 Pengaturan]

👤 Cari topik sejarah yang menarik.

🤖 🎬 🏛 Sejarah
   Pilih format dokumenter:
   [⚡ Quick Files (30–45 dtk)] [🗂 The Archives (75–90 dtk)] [🔬 Deep Files (120–180 dtk)] [Batal]

👤 Pilih format 90 detik.

🤖 ❓ Buat dokumenter ini?
   The Archives · 90 detik · kategori sejarah
   [✅ Ya, lanjutkan] [Batal]

👆 [Ya, lanjutkan]

🤖 (edit) ✅ Episode dibuat. Studio sedang mencari kandidat topik…
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …

🤖 💡 Topik siap dipilih. G0 menunggu approval Anda.
   🗳 G0 · Pilih topik
   Episode (belum berjudul) #QH8F8V · versi 3
   Batas belanja yang disetujui: Rp5.000 (simulasi)
   
   1. Dentuman Krakatau 1883
   fenomena_alam · sensitivitas rendah · keterverifikasian tinggi
   Bagaimana satu gunung di Selat Sunda bisa terdengar sampai tengah Samudra Hindia?
   2. Naskah Voynich: Buku yang Belum Bisa Dibaca
   misteri_sejarah · sensitivitas rendah · keterverifikasian sedang
   Apa yang kita ketahui pasti tentang naskah yang tak seorang pun bisa baca?
   3. Garis Tak Kasatmata di antara Bali dan Lombok
   geografi · sensitivitas rendah · keterverifikasian tinggi
   Mengapa hewan di dua pulau bertetangga bisa begitu berbeda?
   4. Banda dan Perebutan Pala
   sejarah_dunia · sensitivitas sedang · keterverifikasian sedang
   Mengapa segenggam pala pernah lebih berharga dari emas?
   5. Garis Laut di Natuna
   geopolitik · sensitivitas tinggi · keterverifikasian sedang
   Siapa yang menentukan di mana laut sebuah negara berakhir?
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ 1] [✅ 2] [✅ 3] [✅ 4] [✅ 5] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👆 [✅ 1]

🤖 (edit) ✅ Topik dipilih: Dentuman Krakatau 1883. Riset dimulai.
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …

🤖 🔎 Riset dimulai — Dentuman Krakatau 1883 #QH8F8V
   [📁 Episode]

🤖 ✅ ResearchBrief selesai — Dentuman Krakatau 1883 #QH8F8V
   8 fakta terverifikasi. Naskah sedang ditulis…
   [🔎 Lihat riset] [📁 Episode]

🤖 📝 Naskah selesai — Dentuman Krakatau 1883 #QH8F8V
   79.6 dtk · 194 kata. Menyiapkan kartu G1…
   [📝 Lihat naskah] [📁 Episode]

🤖 📝 Naskah siap direview. G1 menunggu approval Anda.
   🗳 G1 · Persetujuan editorial
   Episode Dentuman Krakatau 1883 #QH8F8V · versi 8
   Naskah: Dentuman yang Terdengar Ribuan Kilometer · 79.6 dtk (target 90) · editorial gate LULUS · 7 catatan
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ Approve] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👤 Tunjukkan hasil risetnya.

🤖 🔎 ResearchBrief — Dentuman Krakatau 1883
   Episode #QH8F8V · Menunggu approval editorial (G1)
   Tujuan: Menyusun kronologi dan dampak letusan Krakatau 1883 dari sumber yang dapat diverifikasi.
   Sensitivitas: rendah — Bencana alam historis; korban jiwa disampaikan dengan hormat dan sesuai arsip.
   Mutu riset: ✅ LULUS (8 fakta terverifikasi, minimal 3)
   Klaim: 8 fakta terverifikasi · 2 diperdebatkan · 1 belum terverifikasi · 0 interpretasi & hipotesis
   Sumber: 9 (tier 1: 2, tier 2: 3, tier 3: 1, tier 4: 2, tier 5: 2)
   Catatan fact-check: 5 (3 peringatan)
   [✅ 8] [⚖️ 2] [❔ 1] [💭 0] [📚 Sumber (9)] [⚠️ Catatan (5)] [🔗 Sumber per klaim] [📝 Naskah] [📁 Episode] [🏠 Menu]

👆 [⚖️ 2]

🤖 (edit) ⚖️ Diperdebatkan (2) — Dentuman Krakatau 1883
   
   1. Korban tewas letusan Krakatau mencapai lebih dari 120.000 orang.
      📎 KRK-S5 (t5) · dibantah KRK-S2 (t2)
      C-krak-deaths-120k
      didukung 1 sumber, dibantah KRK-S2
   
   2. Langit merah setelah letusan Krakatau mengilhami lukisan The Scream karya Edvard Munch.
      📎 KRK-S7 (t1) · dibantah KRK-S9 (t2)
      C-krak-scream
      didukung 1 sumber, dibantah KRK-S9
   [🔗 9] [🔗 10] [⬅️ Ringkasan riset] [🏠 Menu]

👤 Apa sumber untuk klaim C-krak-sound?

🤖 🔗 Sumber klaim C-krak-sound
   Dentuman letusan Krakatau dilaporkan terdengar di Pulau Rodrigues, sekitar 4.800 kilometer dari sumbernya.
   Kategori: Fakta terverifikasi · 2 kelompok sumber independen
   2 kelompok sumber independen, tier terbaik 2
   
   📚 KRK-S3 (mendukung) · tier 2 · skor 85
   Gelombang Suara dan Tekanan Udara dari Letusan Krakatau — Lembaga Geofisika (FIXTURE)
   https://fixture.03am.invalid/geofisika/krakatau-gelombang-suara
   
   📚 KRK-S4 (mendukung) · tier 4 · skor 55
   Krakatau dan Langit Merah di Eropa — Majalah Sains Populer (FIXTURE)
   https://fixture.03am.invalid/majalah/krakatau-langit-merah
   
   ❝Dentuman letusan juga dilaporkan terdengar di Pulau Rodrigues.❞ — KRK-S4
   
   ❝Dentuman letusan Krakatau dilaporkan terdengar di Pulau Rodrigues, sekitar 4.800 kilometer dari sumbernya.❞ — KRK-S3
   [🔗 Klaim lain] [⬅️ Ringkasan riset] [🏠 Menu]

👤 Ringkas bagian pembuka.

🤖 📝 Hook (1/5) · 0.0–9.2 dtk · 22 kata
   🎥 Laut lepas saat fajar; peta Samudra Hindia dengan titik Pulau Rodrigues.
   
   • Pada pagi 27 Agustus 1883, sebuah dentuman terdengar di Pulau Rodrigues, di tengah Samudra Hindia.
     ↳ C-krak-peak-date, C-krak-sound
   
   • Sumber suara itu berjarak sekitar 4.800 kilometer.
     ↳ C-krak-sound
   [Context ▶️] [⬅️ Ringkasan naskah] [🏠 Menu]

👤 Berapa estimasi biaya episode ini?

🤖 💸 Biaya episode Dentuman Krakatau 1883 #QH8F8V
   Terpakai: Rp444 (simulasi) · Rp0 (real)
   Pra-produksi (riset & naskah): Rp419 dari batas Rp5.000
   Panggilan LLM tercatat: 15
   Estimasi produksi: belum dihitung (dibuat setelah G1 disetujui).
   
   ⚠️ Semua angka Fase 3 adalah biaya simulasi dari mock provider.
   [📁 Episode] [🏠 Menu]

👤 Naskahnya terlalu kaku, buat lebih natural.

🤖 ❓ Kirim revisi naskah?
   Revisi naskah — approval G1 yang menunggu akan dibatalkan, naskah ditulis ulang, lalu diperiksa editorial gate lagi.
   Catatan: Naskahnya terlalu kaku, buat lebih natural.
   Episode: Dentuman Krakatau 1883 #QH8F8V
   [✅ Ya, lanjutkan] [Batal]

👆 [Ya, lanjutkan]

🤖 (edit) ✅ Revisi naskah dikirim. Naskah ditulis ulang lalu dicek ulang.
   [📁 Episode] [🏠 Menu]

   … worker memproses job, dispatcher mengirim notifikasi …

🤖 📝 Naskah selesai — Dentuman Krakatau 1883 #QH8F8V
   79.6 dtk · 194 kata. Menyiapkan kartu G1…
   [📝 Lihat naskah] [📁 Episode]

🤖 📝 Naskah siap direview. G1 menunggu approval Anda.
   🗳 G1 · Persetujuan editorial
   Episode Dentuman Krakatau 1883 #QH8F8V · versi 11
   Naskah: Dentuman yang Terdengar Ribuan Kilometer · 79.6 dtk (target 90) · editorial gate LULUS · 7 catatan
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ Approve] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👤 Tampilkan episode yang belum saya approve.

🤖 ✅ Menunggu keputusan Anda (1)
   • G1 · Persetujuan editorial — Dentuman Krakatau 1883 #QH8F8V
     kedaluwarsa 06 Nov 02:00 UTC
   [🗳 G1 · Dentuman Krakatau 1883] [🏠 Menu]

👤 setujui saja

🤖 🔒 Untuk keamanan, approval hanya bisa diputuskan lewat tombol di kartu approval. Ini daftar yang sedang menunggu:
   
   ✅ Menunggu keputusan Anda (1)
   • G1 · Persetujuan editorial — Dentuman Krakatau 1883 #QH8F8V
     kedaluwarsa 06 Nov 02:00 UTC
   [🗳 G1 · Dentuman Krakatau 1883] [🏠 Menu]

👆 [🗳 G1]

🤖 (edit) 🗳 G1 · Persetujuan editorial
   Episode Dentuman Krakatau 1883 #QH8F8V · versi 11
   Naskah: Dentuman yang Terdengar Ribuan Kilometer · 79.6 dtk (target 90) · editorial gate LULUS · 7 catatan
   
   Tombol berlaku sampai 03 Nov 08:00 UTC · sekali pakai
   [✅ Approve] [❌ Reject] [✏️ Request Revision] [🔍 Detail]

👆 [Approve]

🤖 (edit) ✅ Disetujui. Episode → ESTIMATING_COST.
   [📁 Episode] [🏠 Menu]
```

## 5. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `studio bot run` → "STUDIO_TELEGRAM_BOT_TOKEN belum diisi" | Isi token di `.env` atau environment. Cek dengan `studio bot check`. |
| Bot membalas "Maaf, bot ini privat." | User ID Anda belum ada di `STUDIO_OWNER_IDS` (format `telegram:<angka>`). Lihat log `telegram.unauthorized user_id=…`. |
| Bot diam di grup | Disengaja: bot hanya melayani chat pribadi. |
| "bot lain sudah berjalan memakai data yang sama" | Ada proses bot lain. Hentikan dulu; kunci ada di `data/telegram-poller.lock` (dilepas otomatis kalau proses mati). |
| Telegram error 409 Conflict | Token yang sama dipakai di mesin lain atau ada webhook aktif. Hentikan poller lain / hapus webhook di BotFather. |
| "Periode anggaran bulan ini belum diaktifkan" | `uv run studio budget activate` atau menu Budget → Aktifkan periode. |
| "Tombol ini sudah kedaluwarsa / sudah dipakai" | Wajar untuk tombol lama. Buka ✅ Approval untuk kartu baru. Approval yang kedaluwarsa bisa diterbitkan ulang dari sana. |
| "Database studio sedang sibuk" | Proses lain memegang lock SQLite > 5 detik. Coba lagi; bot sudah mencoba ulang otomatis 3×. |
| Notifikasi tidak muncul | Pastikan Anda pernah mengirim `/start` ke bot (Telegram melarang bot memulai chat). Cek tabel `notification_outbox` (`status`, `last_error`). Notifikasi yang gagal permanen berstatus `dead`. |
| Ingin melihat apa yang terjadi | `uv run studio episode history <ID>` (audit log), `uv run studio jobs list`. |
| Bot mati di tengah memproses pesan/tombol | Tidak perlu apa-apa: saat start, bot memproses ulang update yang belum di-commit dan mengirim balasan yang tertunda (tabel `ui_inbox` & `ui_reply_outbox`). Aksi yang sudah di-commit tidak dijalankan dua kali. |
| Menerima pesan bot dua kali setelah bot crash | Batas Bot API (tidak ada idempotency key untuk `sendMessage`). Tombol di pesan dobel adalah tombol yang sama dan tetap hanya berlaku sekali. Lihat ADR-0013. |
| Pesan dijawab "Database studio sedang sibuk" | Update sudah dicoba ulang otomatis sampai `STUDIO_UPDATE_MAX_ATTEMPTS` kali tanpa berhasil; tidak ada aksi yang dijalankan. Kirim ulang perintahnya. |
