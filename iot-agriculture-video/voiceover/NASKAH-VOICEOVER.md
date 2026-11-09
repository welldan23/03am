# Naskah Voice-Over — IoT Pertanian Inovatif (5 menit)

Dibuat otomatis oleh `npm run voiceover:script` dari `src/data/subtitles.ts`. Jangan diedit manual —
ubah teksnya di `subtitles.ts`, lalu jalankan ulang perintahnya.

## Cara merekam

1. Rekam **satu file per kalimat**, beri nama sesuai kolom **ID** (contoh `s1-01.wav`).
   Format: WAV/MP3/M4A, 48 kHz atau 44,1 kHz, mono atau stereo.
2. Mulai bicara langsung (jeda hening di awal maks. ±0,2 detik) — rekaman diputar tepat
   saat subtitle kalimat itu muncul.
3. Usahakan durasi bicara **≤ kolom "Ruang bicara"**. Ruang = sampai kalimat berikutnya mulai.
   Kalimat bertanda ⚠ cukup padat: baca sedikit lebih cepat atau ringkas jedanya.
4. Taruh semua file di `public/assets/voiceover/`, lalu jalankan:
   `npm run voiceover:scan` → cek peringatan → render.
5. Musik otomatis mengecil jadi latar, dan "minggir" lagi setiap kamu bicara.

Alternatif: rekam satu file utuh 5 menit sambil menonton video, beri nama `full.wav`.

Tips: ruangan sunyi (lemari baju penuh baju = peredam bagus), mikrofon ±15 cm dari mulut,
nada santai seperti bercerita, bukan membaca berita.

## Scene 1 · Sawah Nusantara (00:00–00:30)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s1-01` | 00:01 | 4,3 dtk | Fajar menyingsing di atas sawah Nusantara. |
| `s1-02` | 00:05 | 6,0 dtk | Selama berabad-abad, petani membaca alam: langit, angin, dan tanah. |
| `s1-03` | 00:11 | 5,5 dtk | Di Bali, sistem subak membagi air secara adil sejak abad ke-9. |
| `s1-04` | 00:16 | 13,3 dtk | Kini cuaca makin sulit ditebak, dan setiap tetes air makin berharga. |

## Scene 2 · Apa Itu Internet of Things? (00:30–01:10)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s2-01` | 00:31 | 5,0 dtk | Internet of Things (IoT) adalah jaringan benda yang saling terhubung. |
| `s2-02` | 00:36 | 8,3 dtk | Benda itu bisa mengukur, mengirim data, bahkan bertindak sendiri. |
| `s2-03` | 00:44 | 4,0 dtk | Sensor di lahan mengukur kondisi tanah, air, dan cuaca. |
| `s2-04` | 00:48 | 4,5 dtk ⚠ | Gateway mengirimkannya secara nirkabel, hingga beberapa kilometer. |
| `s2-05` | 00:53 | 4,5 dtk | Data diolah di cloud, lalu tampil di ponsel petani. |
| `s2-06` | 00:57 | 4,0 dtk | Informasi pun berubah menjadi tindakan di lahan. |
| `s2-07` | 01:01 | 8,5 dtk | Hasilnya: sawah yang bisa “berbicara” tentang apa yang ia butuhkan. |

## Scene 3 · Sensor Tanah & Lingkungan (01:10–01:50)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s3-01` | 01:11 | 5,3 dtk | Di tengah lahan, stasiun kecil bertenaga surya bekerja siang dan malam. |
| `s3-02` | 01:16 | 4,8 dtk | Ia mencatat suhu, kelembapan udara, curah hujan, dan angin. |
| `s3-03` | 01:21 | 5,8 dtk | Di bawah tanah, sensor kelembapan mengukur air di beberapa kedalaman. |
| `s3-04` | 01:27 | 6,0 dtk | Petani jadi tahu: apakah air sudah sampai ke akar, atau belum. |
| `s3-05` | 01:33 | 5,3 dtk | Pengukuran diulang setiap beberapa menit. |
| `s3-06` | 01:38 | 5,8 dtk | Sensor lain memantau pH dan suhu tanah, yang menentukan kesehatan tanaman. |
| `s3-07` | 01:44 | 5,8 dtk | Semua angka ini dikirim otomatis, tanpa perlu dicatat dengan tangan. |

## Scene 4 · Irigasi Otomatis (01:50–02:30)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s4-01` | 01:51 | 4,8 dtk | Air adalah sumber hidup sawah, namun jumlahnya terbatas. |
| `s4-02` | 01:56 | 3,8 dtk | Bagaimana membaginya dengan cermat? |
| `s4-03` | 02:00 | 5,8 dtk | Saat sensor mendeteksi tanah mengering, sistem langsung memberi tanda. |
| `s4-04` | 02:05 | 6,0 dtk | Katup terbuka otomatis, dan air mengalir hanya ke petak yang membutuhkan. |
| `s4-05` | 02:11 | 7,3 dtk | Begitu kelembapan cukup, katup menutup. Tidak ada air yang terbuang percuma. |
| `s4-06` | 02:19 | 5,5 dtk | Irigasi tetes membawa air langsung ke akar tanaman. |
| `s4-07` | 02:24 | 5,5 dtk | Kearifan subak dan teknologi baru bisa berjalan berdampingan. |

## Scene 5 · Drone Pertanian (02:30–03:10)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s5-01` | 02:31 | 7,3 dtk | Dari udara, drone melihat apa yang tak terlihat dari pematang. |
| `s5-02` | 02:38 | 5,3 dtk | Drone terbang mengikuti rute otomatis, memotret sawah petak demi petak. |
| `s5-03` | 02:43 | 6,8 dtk | Ratusan foto digabung menjadi satu peta sawah yang utuh. |
| `s5-04` | 02:50 | 5,8 dtk | Kamera khusus membaca warna daun untuk menilai kesehatan tanaman. |
| `s5-05` | 02:56 | 6,3 dtk | Area yang kekurangan air atau terserang hama terlihat lebih awal. |
| `s5-06` | 03:02 | 7,5 dtk | Drone juga bisa menyemprot pupuk dan pestisida tepat di titik yang perlu. |

## Scene 6 · Dasbor Pertanian Cerdas (03:10–03:50)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s6-01` | 03:11 | 5,3 dtk | Semua data bermuara di satu tempat: dasbor pertanian. |
| `s6-02` | 03:16 | 5,5 dtk | Di ponsel atau komputer, petani melihat kondisi sawahnya saat ini. |
| `s6-03` | 03:22 | 5,5 dtk | Grafik menunjukkan kapan tanah mulai kering, hari demi hari. |
| `s6-04` | 03:27 | 6,0 dtk | Peta menandai petak yang perlu diperhatikan lebih dulu. |
| `s6-05` | 03:33 | 5,5 dtk | Peringatan dikirim otomatis, misalnya saat hujan diprakirakan turun. |
| `s6-06` | 03:39 | 5,5 dtk | Irigasi bisa ditunda, dan air pun bisa dihemat. |
| `s6-07` | 03:44 | 5,3 dtk | Keputusan tak lagi berdasarkan tebakan, melainkan data. |

## Scene 7 · Manfaat & Tantangan (03:50–04:30)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s7-01` | 03:51 | 5,3 dtk | Manfaatnya nyata: air lebih hemat, pupuk lebih tepat sasaran. |
| `s7-02` | 03:56 | 4,8 dtk | Hasil panen pun lebih mudah diprediksi. |
| `s7-03` | 04:01 | 5,3 dtk | Masalah terdeteksi lebih awal, sebelum menjadi kerugian. |
| `s7-04` | 04:06 | 4,8 dtk | Petani bekerja lebih cerdas, bukan lebih keras. |
| `s7-05` | 04:11 | 5,3 dtk | Namun jalannya tidak selalu mudah. Perangkat masih terasa mahal. |
| `s7-06` | 04:16 | 5,5 dtk | Di banyak desa, sinyal internet belum stabil. |
| `s7-07` | 04:22 | 7,8 dtk | Petani juga perlu pendampingan agar teknologi benar-benar terpakai. |

## Scene 8 · Masa Depan Pertanian Cerdas (04:30–05:00)

| ID | Mulai | Ruang bicara | Teks |
|---|---|---|---|
| `s8-01` | 04:31 | 5,5 dtk | Petani muda mulai bertani dengan cara-cara baru. |
| `s8-02` | 04:37 | 23,0 dtk | Data, sensor, dan otomasi membuat lahan sempit pun bisa lebih produktif. |
