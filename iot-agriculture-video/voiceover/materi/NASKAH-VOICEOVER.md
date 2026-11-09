# Naskah Voice-Over — IoT Pertanian Inovatif — Materi Lengkap (8 menit)

Dibuat otomatis oleh `npm run voiceover:script` dari `src/data/subtitles.ts`. Jangan diedit manual —
ubah teksnya di `subtitles.ts`, lalu jalankan ulang perintahnya.

## Cara merekam

1. Rekam **satu file per kalimat**, beri nama sesuai kolom **ID** (contoh `s1-01.wav`).
   Format: WAV/MP3/M4A, 48 kHz atau 44,1 kHz, mono atau stereo.
2. Mulai bicara langsung (jeda hening di awal maks. ±0,2 detik) — rekaman diputar tepat
   saat subtitle kalimat itu muncul.
3. Usahakan durasi bicara **≤ kolom "Ruang bicara"**. Ruang = sampai kalimat berikutnya mulai.
   Kalimat bertanda ⚠ cukup padat: baca sedikit lebih cepat atau ringkas jedanya.
4. Taruh semua file di `public/assets/voiceover/materi/`, lalu jalankan:
   `npm run voiceover:scan -- materi` → cek peringatan → render.
5. Musik otomatis mengecil jadi latar, dan "minggir" lagi setiap kamu bicara.

Alternatif: rekam satu file utuh 5 menit sambil menonton video, beri nama `full.wav`.

Tips: ruangan sunyi (lemari baju penuh baju = peredam bagus), mikrofon ±15 cm dari mulut,
nada santai seperti bercerita, bukan membaca berita.

## Scene 1 · Pertanian Indonesia (00:00–00:35)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s1-01` | 00:01 | 5,0 dtk | Indonesia adalah negeri agraris yang kaya sawah, kebun, dan laut. |
| `s1-02` | 00:06 | 6,5 dtk | Jutaan keluarga menggantungkan hidup pada hasil pertanian. |
| `s1-03` | 00:12 | 6,3 dtk | Namun petani menghadapi tantangan baru: cuaca tak menentu dan biaya yang naik. |
| `s1-04` | 00:18 | 16,3 dtk | Air makin langka, lahan makin sempit, dan hama sulit diprediksi. |

## Scene 2 · Apa Itu IoT? (00:35–01:20)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s2-01` | 00:36 | 5,5 dtk | Internet of Things (IoT) adalah jaringan benda yang terhubung lewat internet. |
| `s2-02` | 00:41 | 5,0 dtk | Di pertanian, bendanya bisa berupa sensor, pompa, katup, hingga drone. |
| `s2-03` | 00:46 | 5,3 dtk | Sistem IoT punya empat komponen utama. |
| `s2-04` | 00:51 | 5,5 dtk | Pertama, sensor, ibarat indra yang merasakan kondisi lahan. |
| `s2-05` | 00:57 | 5,5 dtk | Kedua, konektivitas, ibarat saraf yang mengirimkan data. |
| `s2-06` | 01:02 | 5,5 dtk | Ketiga, platform cloud, ibarat otak yang mengolah data. |
| `s2-07` | 01:08 | 6,0 dtk | Keempat, aplikasi dan aktuator, ibarat tangan yang bertindak. |
| `s2-08` | 01:14 | 5,8 dtk | Keempatnya bekerja dalam satu siklus yang terus berulang. |

## Scene 3 · Arsitektur & Jaringan (01:20–02:05)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s3-01` | 01:21 | 5,3 dtk | Sistem IoT pertanian biasanya disusun dalam empat lapisan. |
| `s3-02` | 01:26 | 5,0 dtk | Lapisan perangkat: sensor dan aktuator di lahan. |
| `s3-03` | 01:31 | 4,5 dtk | Lapisan jaringan mengirimkan datanya. |
| `s3-04` | 01:35 | 5,0 dtk | Lapisan pengolahan menyimpan dan menganalisis data. |
| `s3-05` | 01:40 | 5,3 dtk | Lapisan aplikasi menampilkannya kepada petani. |
| `s3-06` | 01:46 | 5,3 dtk | Pilihan jaringan menentukan jangkauan dan daya tahan baterai. |
| `s3-07` | 01:51 | 5,3 dtk | LoRa menjangkau beberapa kilometer dengan daya sangat hemat. |
| `s3-08` | 01:56 | 4,5 dtk | NB-IoT dan 4G memakai sinyal operator seluler. |
| `s3-09` | 02:01 | 4,0 dtk | Wi-Fi cocok untuk area dekat, seperti greenhouse. |

## Scene 4 · Mengenal Jenis Sensor (02:05–02:50)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s4-01` | 02:06 | 7,0 dtk | Sensor adalah ujung tombak IoT. Mari mengenal jenis-jenisnya. |
| `s4-02` | 02:13 | 4,6 dtk ⚠ | Sensor kelembapan tanah memberi tahu kapan tanaman perlu disiram. |
| `s4-03` | 02:17 | 4,6 dtk ⚠ | Sensor suhu & kelembapan udara membantu mewaspadai penyakit jamur. |
| `s4-04` | 02:22 | 4,6 dtk | Sensor pH menunjukkan tingkat keasaman, agar pemupukan tepat. |
| `s4-05` | 02:26 | 4,6 dtk | Sensor NPK mengukur nitrogen, fosfor, dan kalium di tanah. |
| `s4-06` | 02:31 | 4,6 dtk ⚠ | Penakar hujan mencatat curah hujan, sehingga irigasi bisa ditunda. |
| `s4-07` | 02:36 | 4,6 dtk | Sensor cahaya mengukur sinar matahari yang diterima tanaman. |
| `s4-08` | 02:40 | 4,6 dtk | Sensor ketinggian air dipakai di sawah dan tambak. |
| `s4-09` | 02:45 | 4,8 dtk | Kamera dan AI mengenali gejala hama dan penyakit pada daun. |

## Scene 5 · Sawah Padi Hemat Air (02:50–03:45)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s5-01` | 02:51 | 5,3 dtk | Contoh pertama: sawah padi yang hemat air. |
| `s5-02` | 02:56 | 3,3 dtk | Padi tidak harus selalu tergenang. |
| `s5-03` | 02:59 | 5,8 dtk | Teknik basah-kering berselang (AWD): sawah dikeringkan sebentar, lalu diairi. |
| `s5-04` | 03:05 | 5,5 dtk | Pipa berlubang ditanam di petak sawah untuk melihat air di dalam tanah. |
| `s5-05` | 03:10 | 5,5 dtk | Sensor di dalam pipa mengukur ketinggian air setiap saat. |
| `s5-06` | 03:16 | 5,5 dtk | Saat air turun sekitar 15 cm di bawah permukaan tanah… |
| `s5-07` | 03:21 | 5,0 dtk | …pompa atau pintu air terbuka otomatis. |
| `s5-08` | 03:26 | 5,5 dtk | Menurut IRRI, cara ini bisa menghemat air irigasi hingga sekitar 30%. |
| `s5-09` | 03:32 | 5,5 dtk | Hasil panen tetap terjaga, dan emisi gas metana ikut berkurang. |
| `s5-10` | 03:37 | 7,3 dtk | Petani tak perlu lagi bolak-balik ke sawah hanya untuk mengecek air. |

## Scene 6 · Greenhouse & Hidroponik (03:45–04:35)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s6-01` | 03:46 | 7,3 dtk | Contoh kedua: greenhouse dan kebun hidroponik. |
| `s6-02` | 03:53 | 5,3 dtk | Di greenhouse, sensor memantau suhu, kelembapan, dan cahaya. |
| `s6-03` | 03:58 | 5,5 dtk | Saat suhu melewati batas, misalnya 32°C, kipas dan pengabut menyala otomatis. |
| `s6-04` | 04:04 | 5,0 dtk | Suhu turun kembali, tanaman terhindar dari stres panas. |
| `s6-05` | 04:09 | 5,5 dtk | Di tangki nutrisi, sensor EC dan pH mengukur kepekatan larutan. |
| `s6-06` | 04:14 | 5,5 dtk | Jika nutrisi kurang pekat, pompa dosis menambahkan larutan A dan B. |
| `s6-07` | 04:20 | 6,3 dtk | Petani cukup memantau dari ponsel, bahkan saat berada jauh dari kebun. |
| `s6-08` | 04:26 | 8,8 dtk | Hasilnya: tanaman tumbuh seragam dan air nutrisi tidak terbuang. |

## Scene 7 · Peternakan & Perikanan (04:35–05:25)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s7-01` | 04:36 | 5,5 dtk | Contoh ketiga: peternakan dan perikanan. |
| `s7-02` | 04:41 | 5,3 dtk | Sapi bisa dipasangi kalung sensor berisi GPS dan sensor gerak. |
| `s7-03` | 04:46 | 5,3 dtk | Jika aktivitasnya tiba-tiba turun, peternak mendapat peringatan dini. |
| `s7-04` | 04:52 | 5,3 dtk | Sakit atau birahi pun lebih cepat terdeteksi, tanpa harus menebak. |
| `s7-05` | 04:57 | 5,5 dtk ⚠ | Di tambak udang, kadar oksigen terlarut sangat menentukan hidup-matinya udang. |
| `s7-06` | 05:02 | 5,5 dtk | Oksigen biasanya turun pada malam hari hingga menjelang subuh. |
| `s7-07` | 05:08 | 5,5 dtk | Sensor oksigen memantaunya terus-menerus, siang dan malam. |
| `s7-08` | 05:13 | 5,5 dtk | Saat oksigen turun di bawah batas, kincir air menyala otomatis. |
| `s7-09` | 05:19 | 5,8 dtk | Pakan pun diberikan terjadwal oleh pemberi pakan otomatis. |

## Scene 8 · Kebun & Perkebunan (05:25–06:10)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s8-01` | 05:26 | 5,3 dtk | Contoh keempat: kebun dan perkebunan yang luas. |
| `s8-02` | 05:31 | 5,3 dtk | Di sini, IoT membantu mengawasi ribuan tanaman sekaligus. |
| `s8-03` | 05:36 | 5,3 dtk | Stasiun cuaca mencatat suhu, kelembapan, hujan, dan basah daun. |
| `s8-04` | 05:41 | 5,5 dtk | Daun yang lama basah dan udara lembap meningkatkan risiko penyakit jamur. |
| `s8-05` | 05:47 | 5,5 dtk | Sistem memberi peringatan dini, sebelum penyakit menyebar ke seluruh kebun. |
| `s8-06` | 05:52 | 5,5 dtk | Drone memetakan kebun dan menandai blok yang perlu diperiksa. |
| `s8-07` | 05:58 | 5,5 dtk | Di kebun cabai dan sayuran, sensor tanah membantu penyiraman dan pemupukan. |
| `s8-08` | 06:03 | 6,3 dtk | Semua data dari lahan yang luas terkumpul di satu layar. |

## Scene 9 · Dari Data ke Keputusan (06:10–06:55)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s9-01` | 06:11 | 5,3 dtk | Semua data bermuara di dasbor, di ponsel atau komputer. |
| `s9-02` | 06:16 | 5,5 dtk | Petani melihat kondisi tiap petak secara langsung. |
| `s9-03` | 06:21 | 5,5 dtk | Grafik menunjukkan tren kelembapan dari hari ke hari. |
| `s9-04` | 06:27 | 5,5 dtk | Peta menandai petak yang perlu didahulukan. |
| `s9-05` | 06:32 | 5,5 dtk | Peringatan datang otomatis, misalnya saat hujan akan turun. |
| `s9-06` | 06:38 | 5,5 dtk | Data cuaca membantu menunda irigasi, sehingga air lebih hemat. |
| `s9-07` | 06:43 | 5,5 dtk | Makin lama data terkumpul, makin akurat prediksi yang bisa dibuat. |
| `s9-08` | 06:49 | 5,8 dtk | Keputusan pun berdasarkan data, bukan lagi tebakan. |

## Scene 10 · Manfaat, Tantangan & Cara Memulai (06:55–07:35)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s10-01` | 06:56 | 5,3 dtk | Manfaatnya: air dan pupuk lebih hemat, masalah terdeteksi lebih awal. |
| `s10-02` | 07:01 | 8,0 dtk | Hasil panen lebih terjaga, dan petani bekerja lebih efisien. |
| `s10-03` | 07:09 | 5,3 dtk | Tantangannya: biaya perangkat masih terasa mahal. |
| `s10-04` | 07:14 | 7,8 dtk | Sinyal di desa belum merata, dan petani perlu pendampingan. |
| `s10-05` | 07:22 | 5,3 dtk | Cara memulainya: pilih satu masalah yang paling penting dulu. |
| `s10-06` | 07:27 | 4,5 dtk ⚠ | Mulai dengan satu atau dua sensor, patungan lewat kelompok tani. |
| `s10-07` | 07:32 | 3,0 dtk | Lalu perluas sedikit demi sedikit. |

## Scene 11 · Penutup (07:35–08:00)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s11-01` | 07:44 | 15,5 dtk | Mari wujudkan pertanian Indonesia yang cerdas dan berkelanjutan. |
