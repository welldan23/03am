# IoT PERTANIAN INOVATIF: Transformasi Menuju Pertanian Cerdas

Dokumenter edukasi 5 menit tanpa narasi, dengan subtitle Bahasa Indonesia, dibuat
pakai [Remotion](https://www.remotion.dev/) (React + TypeScript).

| Spesifikasi | Nilai |
|---|---|
| Resolusi | 1920×1080 (16:9) |
| Frame rate | 24 fps |
| Durasi | **7.200 frame = 300 detik**, dicek otomatis oleh `npm run verify` |
| Audio | Musik instrumental + efek suara & suasana alam (tanpa suara orang). Siap ditambah voice-over manual |
| Subtitle | Bahasa Indonesia, di-render langsung ke video (burned-in) |

> **Status: 8/8 scene selesai.** Film penuh 5 menit bisa di-preview dan di-render.
> Angka di grafik/dasbor yang bertanda **DATA ILUSTRASI** adalah contoh, bukan pengukuran.

---

## Mulai cepat

```bash
cd iot-agriculture-video
npm install
npm run studio          # buka Remotion Studio di http://localhost:3000
```

Butuh Node.js 18 ke atas (sudah dites dengan Node 22).

## Cara preview

1. Jalankan `npm run studio`, lalu buka `http://localhost:3000`.
2. Di panel kiri ada dua pilihan:
   - **`IoTAgriculture`**: film penuh 5 menit (7.200 frame).
   - **`Per-Scene → Scene1-Intro`** dst.: satu scene saja, lebih ringan dan cocok buat review.
3. Tombol keyboard yang berguna di Studio:
   `Spasi` = play/pause · `←/→` = mundur/maju 1 frame · `Shift + ←/→` = lompat 1 detik ·
   `J/K/L` = mundur/berhenti/maju.
4. Di timeline bawah, setiap *shot* punya nama (`A · Fajar`, `B · Jatiluwih`, …)
   supaya gampang lompat ke bagian yang mau dicek.
5. Kalau preview patah-patah, kecilkan zoom ke 50% di pojok kiri bawah. Untuk melihat
   gerak yang mulus, render klip scene: `npm run render:scene1`.

Frame 0 memang hitam, karena film dibuka dengan *fade-in* dari hitam.

## Perintah

| Perintah | Fungsi |
|---|---|
| `npm run studio` | Buka Remotion Studio (preview) |
| `npm run typecheck` | Cek TypeScript (`tsc --noEmit`, mode strict) |
| `npm run verify` | Cek timeline: total 7.200 frame, scene nyambung sesuai storyboard, aturan baca subtitle, file aset ada |
| `npm run check` | `typecheck` + `verify` sekaligus |
| `npm run still` | Render satu frame PNG ke `out/still.png` |
| `npm run render:scene1` | Render Scene 1 saja → `out/scene1.mp4` |
| `npm run render:preview` | Render film penuh di 960×540 (cepat, buat review) |
| `npm run render` | Render final 1920×1080 H.264 CRF 18 → `out/iot-pertanian.mp4` |
| `npm run search-photos -- "kata kunci" --sheet` | Cari foto berlisensi bebas di Wikimedia Commons + Openverse |
| `npm run fetch-assets` | Unduh foto dari `asset-sources.json`, perkecil ke ukuran wajar, perbarui kredit lisensi |
| `npm run make-sfx` | Buat ulang efek suara sintetis → `public/assets/sfx/*.wav` |
| `npm run voiceover:script` | Buat naskah rekaman (`voiceover/NASKAH-VOICEOVER.md`) + `voiceover/subtitles.srt` |
| `npm run voiceover:scan` | Deteksi rekaman di `public/assets/voiceover/`, cek durasinya, aktifkan ducking musik |
| `npm run lambda:check` | Cek kesiapan render AWS Lambda (offline, gratis) |
| `npm run lambda:render` | Render di AWS Lambda, **default cuma dry-run** (lihat bawah) |

Kalau Chrome tidak bisa diunduh otomatis (misalnya di CI atau container tanpa internet), arahkan
Remotion ke Chromium yang sudah terpasang:

```bash
REMOTION_BROWSER_EXECUTABLE=/path/ke/chrome-headless-shell npm run render:scene1
```

## Struktur

```
iot-agriculture-video/
├─ remotion.config.ts           konfigurasi CLI (format gambar, pixel format, browser opsional)
├─ src/
│  ├─ index.ts                  registerRoot
│  ├─ Root.tsx                  daftar komposisi: film penuh + 1 komposisi per scene
│  ├─ compositions/
│  │  └─ IoTAgriculture.tsx     merakit timeline dari data/scenes.ts (tanpa angka waktu sendiri)
│  ├─ scenes/
│  │  ├─ Scene01Intro.tsx … Scene08Future.tsx   satu file per scene (daftar shot di komentar atas)
│  │  ├─ index.ts               registry scene → komponen (yang belum ada = placeholder)
│  │  └─ types.ts
│  ├─ components/
│  │  ├─ CinematicPhoto.tsx     foto asli + kamera virtual (push-in/pan/tilt) + parallax 2.5D + color grade
│  │  ├─ Shot.tsx               satu shot dengan crossfade / focus-pull
│  │  ├─ SceneShell.tsx         transisi antar-scene (fade, blur-dissolve, dip-to-black, light-wipe)
│  │  ├─ Atmosphere.tsx         kabut berlapis, debu/serbuk sari melayang, pendar matahari
│  │  ├─ FilmLook.tsx           film grain + vinyet (global)
│  │  ├─ IoTNetwork.tsx         node sensor, koneksi, dan paket data yang mengalir
│  │  ├─ TitleSequence.tsx      judul sinematik
│  │  ├─ LocationTag.tsx        label lokasi + koordinat
│  │  ├─ StatCallout.tsx        angka faktual lengkap dengan sumber
│  │  ├─ Subtitles.tsx          trek subtitle
│  │  └─ PlaceholderScene.tsx   penanda scene yang belum dikerjakan
│  ├─ data/
│  │  ├─ video.ts               FPS, resolusi, TOTAL_FRAMES = 7200, panjang transisi
│  │  ├─ scenes.ts              storyboard 8 scene (timecode, judul, jenis transisi)
│  │  ├─ subtitles.ts           semua teks layar (waktu relatif ke awal scene)
│  │  ├─ facts.ts               angka faktual + sumbernya
│  │  ├─ audio.ts               musik latar & level volume
│  │  ├─ sfx.ts                 109 cue efek suara per scene
│  │  ├─ voiceover.ts           rekaman voice-over (dari voiceover.generated.json)
│  │  ├─ assets.ts              akses foto bertipe + kredit
│  │  └─ credits.generated.json dibuat oleh fetch-assets (lisensi, pembuat, URL sumber)
│  ├─ lib/                      time.ts (detik/timecode → frame), camera.ts (matematika kamera)
│  └─ styles/                   theme.ts (warna, font, area aman), grades.ts (preset grading), fonts.ts
├─ public/assets/
│  ├─ images/                   foto CC (Commons / Openverse) + tekstur grain
│  └─ credits/CREDITS.md        tabel atribusi (dibuat otomatis)
└─ scripts/
   ├─ asset-sources.json        daftar foto yang dipakai (judul Commons / id Openverse)
   ├─ search-photos.mjs         pencarian foto + lembar kontak + --pick
   ├─ fetch-assets.mjs          pengunduh + kompres + penolak lisensi yang tidak bebas
   ├─ lib/                      sources.mjs (Commons, Openverse, kebijakan lisensi), image-size.mjs
   ├─ verify-timeline.ts        validator timeline & subtitle
   ├─ voiceover.ts              naskah rekaman, .srt, dan pemindai rekaman
   ├─ make-sfx.mjs              generator efek suara sintetis
   ├─ lambda-preflight.mjs      cek kesiapan Lambda tanpa menghubungi AWS
   └─ lambda-render.mjs        render Lambda (berpengaman, dry-run kecuali disetujui)
```

### Konsepnya: semua diatur lewat data

- **Waktu scene** cuma ada di `src/data/scenes.ts` (format `mm:ss`). Timeline, komposisi
  per-scene, dan validator semuanya membaca dari sini.
- **Transisi** berbentuk satu kata per scene (`transitionIn`). Scene baru *mulai* muncul
  tepat di timecode storyboard, dan scene lama diperpanjang 24 frame (1 detik) di bawahnya
  supaya tidak ada frame kosong. Total durasi tetap 7.200 frame.
- **Subtitle** ditulis relatif ke awal scene. Kalau scene digeser, subtitle ikut bergeser
  dengan sendirinya.
- **Scene baru** cukup dibuat di `src/scenes/`, didaftarkan di `src/scenes/index.ts`, lalu
  `implemented: true` diubah di `scenes.ts`.

## Storyboard

| # | Waktu | Frame | Judul | Transisi masuk | Isi visual |
|---|---|---|---|---|---|
| 1 | 00:00–00:30 | 0–720 | Pengantar: sawah Nusantara | fade dari hitam | 4 foto sawah + sekuens judul + cuplikan jaringan IoT |
| 2 | 00:30–01:10 | 720–1680 | Apa itu Internet of Things? | dip-to-black | Sensor bermunculan di sawah Bali → diagram alur Sensor → Gateway → Cloud → Ponsel → Aksi |
| 3 | 01:10–01:50 | 1680–2640 | Sensor tanah & lingkungan | blur-dissolve | Stasiun sensor surya berlabel → penampang tanah (air meresap ke zona akar) → panel suhu/pH/kelembapan |
| 4 | 01:50–02:30 | 2640–3600 | Irigasi otomatis | light-wipe | Saluran subak → skema katup otomatis 4 petak → irigasi tetes |
| 5 | 02:30–03:10 | 3600–4560 | Drone pertanian | blur-dissolve | Drone menyemprot → HUD survei rute zig-zag → peta kesehatan tanaman |
| 6 | 03:10–03:50 | 4560–5520 | Dasbor pertanian cerdas | light-wipe | Dasbor lengkap, kamera virtual berpindah antar-panel |
| 7 | 03:50–04:30 | 5520–6480 | Manfaat & tantangan | dip-to-black | Daftar manfaat & tantangan di atas foto sawah |
| 8 | 04:30–05:00 | 6480–7200 | Masa depan pertanian cerdas | fade | Hidroponik → pesan penutup → kredit foto → hitam |

### Rincian Scene 1

| Shot | Waktu | Gambar | Gerak kamera |
|---|---|---|---|
| A · Fajar | 00:00–00:05.5 | Sawah saat fajar | Push-in pelan, parallax 2 lapis, kabut bergerak, pendar matahari |
| B · Jatiluwih | 00:05–00:11.5 | Terasering Jatiluwih, Tabanan | Pan lateral + parallax, label lokasi, angka luas sawah |
| C · Tegallalang | 00:11–00:17 | Terasering Tegallalang, Gianyar | Tilt-down + push-in |
| D · Petani | 00:16.5–00:22.5 | Panen padi, Jawa Tengah | Push-in ke subjek, angka rumah tangga tani |
| E · Judul | 00:22–00:30 | Panorama Jatiluwih | Pan pelan + sekuens judul + cuplikan jaringan sensor IoT |

Rincian shot scene lain ada di komentar paling atas tiap file `src/scenes/SceneNN*.tsx`.

### Kejujuran data
- Angka faktual (luas sawah, jumlah rumah tangga tani) punya sumber di `src/data/facts.ts`
  dan ikut tampil di layar serta kredit penutup.
- Angka di sensor, dasbor, telemetri drone, dan peta kesehatan tanaman **dibuat untuk
  menjelaskan cara kerja**, dan selalu diberi label *DATA ILUSTRASI*.
- Scene 7 (manfaat & tantangan) sengaja kualitatif. Tidak ada persentase tanpa sumber.
- Foto yang diambil di luar Indonesia diberi label lokasi aslinya (Kerala, India; Aomori, Jepang).

### Catatan parallax
Efek parallax 2.5D (satu foto dibelah jadi dua lapis) sengaja dibatasi maksimal 3 px. Kalau lebih
dari itu, objek yang melintasi horizon (pohon kelapa, orang) tampak dobel. Rasa kedalaman utamanya
datang dari lapisan kabut, debu, dan cahaya yang bergerak dengan kecepatan berbeda.

## Aset & lisensi

### Cara cari & tambah foto

Sumber foto: **Wikimedia Commons** dan **Openverse** (mesin pencari foto CC yang
menggabungkan Flickr, museum, dan lain-lain). Keduanya **tidak butuh API key**.

```bash
# 1. Cari foto. --sheet membuat lembar kontak .cache/contact-sheet.jpg (thumbnail bernomor)
npm run search-photos -- "agricultural drone spraying" --sheet

# 2. Ambil hasil yang cocok (nomor dari daftar di atas) → otomatis masuk asset-sources.json
npm run search-photos -- --pick 5 --id droneSprayPaddy --file images/s5-drone-spray-paddy.jpg

# 3. Unduh + catat kredit
npm run fetch-assets

# 4. Pakai di scene
#    const img = photo('droneSprayPaddy');
```

Aturan yang dijalankan otomatis:
- **Lisensi**: hanya CC0, Public domain, CC BY, dan CC BY-SA, karena video ini meng-crop,
  men-grade, dan menimpa teks. Lisensi NC/ND atau yang tidak jelas langsung dibuang.
- **Ukuran**: hasil pencarian yang lebarnya di bawah 2400 px dibuang (atur dengan `--min-width`).
  Foto kecil bakal pecah kalau di-zoom di 1080p. Kebanyakan foto Flickr lewat Openverse
  cuma 500–1024 px, jadi jarang lolos.
- **Kompres**: foto yang lebih lebar dari 3200 px diperkecil ke 3200 px. Tinggi minimal
  tetap 1600 px, supaya panorama ultra-lebar tidak blur.
- **Dimensi asli**: lebar/tinggi di kredit dibaca dari file hasil unduhan, bukan dari metadata
  sumber (yang kadang tidak cocok).
- **`npm run verify`** mengecek setiap `photo('...')` di kode benar-benar terdaftar.

Pixabay dan Pexels **tidak bisa diakses** dari lingkungan build cloud ini. Kalau mau
pakai foto atau klip dari sana, unduh manual dari laptop. Lisensi Pixabay/Pexels
membolehkan pemakaian komersial tanpa wajib atribusi, tapi tetap catat link sumbernya.

### Foto yang sudah ada (25)

| Scene | Foto |
|---|---|
| 1 Pengantar | fajar di sawah, Jatiluwih, Tegallalang, petani panen Jawa Tengah, panorama Jatiluwih |
| 3 Sensor | probe suhu tanah, tiang sensor bertenaga surya |
| 4 Irigasi | saluran subak (air terjun kecil & aliran), irigasi tetes Kerala, close-up tetesan |
| 5 Drone | drone menyemprot sawah, drone di atas ladang, drone di sawah, udara sawah Bali, petak sawah dari atas |
| 7 Manfaat & tantangan | bulir padi, petani di terasering, tanah sawah retak, padi di tanah kering, lahan kering |
| 8 Masa depan | petani hidroponik, deretan pakcoy, greenhouse akuaponik, petani dengan latar gunung |

Scene 2 (IoT) dan Scene 6 (dasbor) lebih banyak memakai animasi prosedural di atas foto
sawah yang sudah ada.

Daftar lengkap pembuat + lisensinya: [`public/assets/credits/CREDITS.md`](public/assets/credits/CREDITS.md).

### Kenapa tidak pakai foto dari situs berita (Antara, Kompas, dll.)?

Foto di situs berita **dilindungi hak cipta (all rights reserved)**, bukan berlisensi bebas.
Tampil di internet bukan berarti boleh dipakai ulang. Antara Foto menjual lisensinya secara
komersial, jadi memakainya tanpa izin berisiko *takedown* atau klaim hak cipta. Kalau nanti
lisensinya dibeli, taruh filenya di `public/assets/images/` dan daftarkan seperti foto lain,
dengan kredit sesuai kontrak lisensinya.

### Catatan lisensi & gaya
- **Foto asli, bukan gambar buatan.** Gerak "sinematik" berasal dari kamera virtual (pan,
  push-in, parallax 2.5D, kabut, grading) di atas foto. Tidak ada pemandangan yang dibuat pakai CSS.
- **Grafik teknologi** (jaringan IoT, dasbor, visual sensor, irigasi) sengaja dibuat prosedural.
- **CC BY-SA**: hasil olahan juga harus dibagikan dengan lisensi yang sama. Kredit wajib
  tampil di *end credits* (Scene 8) dan di deskripsi saat diunggah.
- **Footage video**: kalau nanti ada klip berlisensi, taruh di `public/assets/video/` dan pakai
  `<OffthreadVideo>` di shot yang sama. Kamera virtual dan grading tetap bisa dipakai.
- **Font**: Plus Jakarta Sans dan JetBrains Mono (OFL), dibundel lewat `@fontsource`.

### Angka faktual

Angka yang muncul di layar disimpan di `src/data/facts.ts` lengkap dengan sumbernya.
**Cek ulang ke sumber resmi sebelum video dipublikasikan:**

- 7,46 juta ha lahan baku sawah nasional (Kementerian ATR/BPN, 2019)
- 28,4 juta rumah tangga usaha pertanian (BPS, Sensus Pertanian 2023)

## Musik & voice-over

### Musik latar
**"Affirmations" oleh Scott Buckley** (CC BY 4.0, via Wikimedia Commons). Instrumennya piano,
string, dan synth, **tanpa vokal**. Durasinya 301,8 detik, jadi cukup satu lagu untuk seluruh
film. Ada fade-in 2,5 detik di awal dan fade-out 5 detik di akhir. Atribusi otomatis tampil di
kredit penutup (bagian MUSIK). Pengaturan volume ada di `src/data/audio.ts`.

### Efek suara & suasana
Ada dua jenis, semuanya **tanpa suara orang**:

| Jenis | Isi | Sumber |
|---|---|---|
| Suasana alam | Burung fajar (Nilgiri), tonggeret (Mojokerto, Jawa Timur), aliran air, hujan | Wikimedia Commons (CC BY / CC BY-SA / CC0 / domain publik). Dibuang dengung rendahnya (high-pass 150 Hz) dan diseragamkan ke −24 LUFS |
| Efek sintetis | Whoosh transisi, dentum judul, tik UI, blip data, alarm, katup, tetesan, sapuan pemindai, dengung drone, angin | Dibuat sendiri dari rumus oleh `scripts/make-sfx.mjs`, tanpa sampel rekaman |

Ada 109 cue, ditulis per scene di `src/data/sfx.ts` (waktu relatif ke awal scene, sama seperti
subtitle) dan disinkronkan ke animasinya. Contohnya: katup berbunyi "klek" saat terbuka di skema
irigasi, alarm saat petak kering terdeteksi, dan dengung drone di Scene 5. Kalau ada voice-over,
semua efek otomatis turun ke 45% saat narator bicara.

### Voice-over (rekaman suara sendiri)
Film ini disiapkan untuk dinarasikan **manual** dengan membacakan subtitle-nya.

1. `npm run voiceover:script`, lalu buka `voiceover/NASKAH-VOICEOVER.md`. Isinya 47 kalimat,
   masing-masing dengan ID, waktu mulai, dan "ruang bicara" (detik sampai kalimat berikutnya).
2. Rekam **satu file per kalimat** dan beri nama sesuai ID-nya: `s1-01.wav`, `s1-02.wav`, …
   Atau rekam satu file utuh 5 menit sambil menonton video, beri nama `full.wav`.
3. Taruh filenya di `public/assets/voiceover/`.
4. `npm run voiceover:scan`. Rekaman terdeteksi, durasinya diukur, dan muncul peringatan kalau
   ada yang kepanjangan sampai menabrak kalimat berikutnya.
5. `npm run render`. Musik otomatis turun jadi latar (32%) dan mengecil lagi (14%) setiap kamu
   bicara, dengan transisi halus.

Mau ubah kalimat? Edit `src/data/subtitles.ts`, lalu jalankan ulang `voiceover:script`.
Subtitle di layar dan naskah rekaman selalu sinkron karena sumbernya sama.

## Render lokal

```bash
npm run render:scene1     # Scene 1 saja, sekitar 1–2 menit
npm run render:preview    # film penuh 960×540
npm run render            # final 1920×1080 → out/iot-pertanian.mp4
```

Sebagai patokan: Scene 1 di 960×540 selesai sekitar 80 detik di container 4 core.
Render final 1080p untuk film penuh kira-kira 10× lebih lama dari itu.

## Render di cloud (AWS Lambda), opsional

Proyeknya sudah siap untuk Lambda: font lokal, semua aset di `public/`, tidak
memanggil jaringan saat render, dan semua paket `@remotion/*` di versi yang sama.
**Belum ada resource AWS yang dibuat, dan belum ada biaya yang keluar.**

1. Cek kesiapan (offline, gratis):
   ```bash
   npm run lambda:check
   ```
2. Siapkan kredensial IAM sesuai panduan resmi
   ([remotion.dev/docs/lambda/setup](https://www.remotion.dev/docs/lambda/setup)).
   Taruh kredensialnya di environment, **jangan pernah di-commit**:
   ```bash
   export REMOTION_AWS_ACCESS_KEY_ID=...
   export REMOTION_AWS_SECRET_ACCESS_KEY=...
   export REMOTION_AWS_REGION=ap-southeast-1   # Singapura, region terdekat dari Indonesia
   ```
3. Lihat rencananya dulu (dry-run, tanpa biaya):
   ```bash
   npm run lambda:render
   ```
4. **Hanya setelah owner menyetujui biayanya**, jalankan render sungguhan. Skrip ini butuh
   dua konfirmasi sekaligus:
   ```bash
   REMOTION_LAMBDA_CONFIRM=yes node scripts/lambda-render.mjs --i-approve-aws-costs
   ```
   Skrip akan membuat fungsi Lambda dan bucket S3, mengunggah bundle, lalu render dengan
   30 worker (240 frame per worker). Progres dan perkiraan biaya ditampilkan selama
   proses. Hasilnya disimpan *private* di S3.

Opsi lain bisa diatur lewat flag: `--region=`, `--memory=`, `--timeout=`,
`--frames-per-lambda=`, `--composition=Scene1-Intro`.

Kalau tidak dipakai lagi, hapus resource-nya dengan `npx remotion lambda functions rmall` dan
`npx remotion lambda sites rmall`.
