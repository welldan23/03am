import { buildCues, buildScenes, type CueInput, type MusicPlacement } from '../../lib/film';
import { FPS } from '../../data/video';

/**
 * FILM 2 — "IoT Pertanian Inovatif: Materi Lengkap" (8 menit = 11.520 frame).
 * Data murni (tanpa React) supaya bisa dibaca skrip verifikasi & naskah voice-over.
 */
export const MATERI_ID = 'materi';
export const MATERI_TITLE = 'IoT PERTANIAN INOVATIF';
export const MATERI_SUBTITLE = 'Materi Lengkap & Contoh Penerapan';
export const MATERI_SECONDS = 480;
export const MATERI_TOTAL_FRAMES = MATERI_SECONDS * FPS; // 11.520

export const MATERI_SCENES = buildScenes([
  { id: 'm-opening', number: 1, compositionId: 'M01-Pembuka', title: 'Pertanian Indonesia', kicker: 'Pembuka', start: '00:00', end: '00:35', transitionIn: 'fade' },
  { id: 'm-what', number: 2, compositionId: 'M02-Apa-Itu-IoT', title: 'Apa Itu IoT?', kicker: 'Bab 1', start: '00:35', end: '01:20', transitionIn: 'dip-to-black' },
  { id: 'm-arch', number: 3, compositionId: 'M03-Arsitektur', title: 'Arsitektur & Jaringan', kicker: 'Bab 2', start: '01:20', end: '02:05', transitionIn: 'blur-dissolve' },
  { id: 'm-sensors', number: 4, compositionId: 'M04-Jenis-Sensor', title: 'Mengenal Jenis Sensor', kicker: 'Bab 3', start: '02:05', end: '02:50', transitionIn: 'light-wipe' },
  { id: 'm-rice', number: 5, compositionId: 'M05-Contoh-Sawah', title: 'Sawah Padi Hemat Air', kicker: 'Contoh 1', start: '02:50', end: '03:45', transitionIn: 'dip-to-black' },
  { id: 'm-greenhouse', number: 6, compositionId: 'M06-Contoh-Greenhouse', title: 'Greenhouse & Hidroponik', kicker: 'Contoh 2', start: '03:45', end: '04:35', transitionIn: 'blur-dissolve' },
  { id: 'm-livestock', number: 7, compositionId: 'M07-Contoh-Ternak-Tambak', title: 'Peternakan & Perikanan', kicker: 'Contoh 3', start: '04:35', end: '05:25', transitionIn: 'light-wipe' },
  { id: 'm-plantation', number: 8, compositionId: 'M08-Contoh-Perkebunan', title: 'Kebun & Perkebunan', kicker: 'Contoh 4', start: '05:25', end: '06:10', transitionIn: 'blur-dissolve' },
  { id: 'm-dashboard', number: 9, compositionId: 'M09-Dasbor', title: 'Dari Data ke Keputusan', kicker: 'Bab 4', start: '06:10', end: '06:55', transitionIn: 'light-wipe' },
  { id: 'm-start', number: 10, compositionId: 'M10-Manfaat-Memulai', title: 'Manfaat, Tantangan & Cara Memulai', kicker: 'Bab 5', start: '06:55', end: '07:35', transitionIn: 'dip-to-black' },
  { id: 'm-closing', number: 11, compositionId: 'M11-Penutup', title: 'Penutup', kicker: 'Penutup', start: '07:35', end: '08:00', transitionIn: 'fade' },
]);

const CUES: readonly CueInput[] = [
  // 1 · Pembuka
  { scene: 'm-opening', from: 1.0, to: 5.0, text: 'Indonesia adalah negeri agraris yang\nkaya sawah, kebun, dan laut.' },
  { scene: 'm-opening', from: 6.0, to: 11.0, text: 'Jutaan keluarga menggantungkan hidup\npada hasil pertanian.' },
  { scene: 'm-opening', from: 12.5, to: 17.5, text: 'Namun petani menghadapi tantangan baru:\ncuaca tak menentu dan biaya yang naik.' },
  { scene: 'm-opening', from: 18.75, to: 24.0, text: 'Air makin langka, lahan makin sempit,\ndan hama sulit diprediksi.' },

  // 2 · Apa itu IoT
  { scene: 'm-what', from: 1.0, to: 5.75, text: 'Internet of Things (IoT) adalah jaringan\nbenda yang terhubung lewat internet.' },
  { scene: 'm-what', from: 6.5, to: 10.75, text: 'Di pertanian, bendanya bisa berupa sensor,\npompa, katup, hingga drone.' },
  { scene: 'm-what', from: 11.5, to: 16.0, text: 'Sistem IoT punya empat komponen utama.' },
  { scene: 'm-what', from: 16.75, to: 21.5, text: 'Pertama, sensor, ibarat indra yang\nmerasakan kondisi lahan.' },
  { scene: 'm-what', from: 22.25, to: 27.0, text: 'Kedua, konektivitas, ibarat saraf\nyang mengirimkan data.' },
  { scene: 'm-what', from: 27.75, to: 32.5, text: 'Ketiga, platform cloud, ibarat otak\nyang mengolah data.' },
  { scene: 'm-what', from: 33.25, to: 38.5, text: 'Keempat, aplikasi dan aktuator, ibarat\ntangan yang bertindak.' },
  { scene: 'm-what', from: 39.25, to: 44.0, text: 'Keempatnya bekerja dalam satu siklus\nyang terus berulang.' },

  // 3 · Arsitektur & jaringan
  { scene: 'm-arch', from: 1.0, to: 5.5, text: 'Sistem IoT pertanian biasanya disusun\ndalam empat lapisan.' },
  { scene: 'm-arch', from: 6.25, to: 10.5, text: 'Lapisan perangkat: sensor dan aktuator\ndi lahan.' },
  { scene: 'm-arch', from: 11.25, to: 15.0, text: 'Lapisan jaringan mengirimkan datanya.' },
  { scene: 'm-arch', from: 15.75, to: 20.0, text: 'Lapisan pengolahan menyimpan dan\nmenganalisis data.' },
  { scene: 'm-arch', from: 20.75, to: 24.5, text: 'Lapisan aplikasi menampilkannya\nkepada petani.' },
  { scene: 'm-arch', from: 26.0, to: 30.5, text: 'Pilihan jaringan menentukan jangkauan\ndan daya tahan baterai.' },
  { scene: 'm-arch', from: 31.25, to: 35.75, text: 'LoRa menjangkau beberapa kilometer\ndengan daya sangat hemat.' },
  { scene: 'm-arch', from: 36.5, to: 40.25, text: 'NB-IoT dan 4G memakai sinyal\noperator seluler.' },
  { scene: 'm-arch', from: 41.0, to: 44.5, text: 'Wi-Fi cocok untuk area dekat,\nseperti greenhouse.' },

  // 4 · Jenis sensor
  { scene: 'm-sensors', from: 1.0, to: 6.0, text: 'Sensor adalah ujung tombak IoT.\nMari mengenal jenis-jenisnya.' },
  { scene: 'm-sensors', from: 8.0, to: 12.0, text: 'Sensor kelembapan tanah memberi tahu\nkapan tanaman perlu disiram.' },
  { scene: 'm-sensors', from: 12.6, to: 16.6, text: 'Sensor suhu & kelembapan udara membantu\nmewaspadai penyakit jamur.' },
  { scene: 'm-sensors', from: 17.2, to: 21.2, text: 'Sensor pH menunjukkan tingkat keasaman,\nagar pemupukan tepat.' },
  { scene: 'm-sensors', from: 21.8, to: 25.8, text: 'Sensor NPK mengukur nitrogen, fosfor,\ndan kalium di tanah.' },
  { scene: 'm-sensors', from: 26.4, to: 30.4, text: 'Penakar hujan mencatat curah hujan,\nsehingga irigasi bisa ditunda.' },
  { scene: 'm-sensors', from: 31.0, to: 35.0, text: 'Sensor cahaya mengukur sinar matahari\nyang diterima tanaman.' },
  { scene: 'm-sensors', from: 35.6, to: 39.6, text: 'Sensor ketinggian air dipakai\ndi sawah dan tambak.' },
  { scene: 'm-sensors', from: 40.2, to: 44.6, text: 'Kamera dan AI mengenali gejala hama\ndan penyakit pada daun.' },

  // 5 · Contoh 1: sawah AWD
  { scene: 'm-rice', from: 1.0, to: 5.5, text: 'Contoh pertama: sawah padi yang\nhemat air.' },
  { scene: 'm-rice', from: 6.25, to: 8.75, text: 'Padi tidak harus selalu tergenang.' },
  { scene: 'm-rice', from: 9.5, to: 14.5, text: 'Teknik basah-kering berselang (AWD):\nsawah dikeringkan sebentar, lalu diairi.' },
  { scene: 'm-rice', from: 15.25, to: 20.0, text: 'Pipa berlubang ditanam di petak sawah\nuntuk melihat air di dalam tanah.' },
  { scene: 'm-rice', from: 20.75, to: 25.5, text: 'Sensor di dalam pipa mengukur\nketinggian air setiap saat.' },
  { scene: 'm-rice', from: 26.25, to: 31.0, text: 'Saat air turun sekitar 15 cm\ndi bawah permukaan tanah…' },
  { scene: 'm-rice', from: 31.75, to: 36.0, text: '…pompa atau pintu air terbuka otomatis.' },
  { scene: 'm-rice', from: 36.75, to: 41.5, text: 'Menurut IRRI, cara ini bisa menghemat\nair irigasi hingga sekitar 30%.' },
  { scene: 'm-rice', from: 42.25, to: 47.0, text: 'Hasil panen tetap terjaga, dan\nemisi gas metana ikut berkurang.' },
  { scene: 'm-rice', from: 47.75, to: 54.0, text: 'Petani tak perlu lagi bolak-balik\nke sawah hanya untuk mengecek air.' },

  // 6 · Contoh 2: greenhouse
  { scene: 'm-greenhouse', from: 1.0, to: 5.5, text: 'Contoh kedua: greenhouse dan\nkebun hidroponik.' },
  { scene: 'm-greenhouse', from: 8.25, to: 12.75, text: 'Di greenhouse, sensor memantau suhu,\nkelembapan, dan cahaya.' },
  { scene: 'm-greenhouse', from: 13.5, to: 18.25, text: 'Saat suhu melewati batas, misalnya 32°C,\nkipas dan pengabut menyala otomatis.' },
  { scene: 'm-greenhouse', from: 19.0, to: 23.25, text: 'Suhu turun kembali, tanaman\nterhindar dari stres panas.' },
  { scene: 'm-greenhouse', from: 24.0, to: 28.75, text: 'Di tangki nutrisi, sensor EC dan pH\nmengukur kepekatan larutan.' },
  { scene: 'm-greenhouse', from: 29.5, to: 34.25, text: 'Jika nutrisi kurang pekat, pompa dosis\nmenambahkan larutan A dan B.' },
  { scene: 'm-greenhouse', from: 35.0, to: 40.5, text: 'Petani cukup memantau dari ponsel,\nbahkan saat berada jauh dari kebun.' },
  { scene: 'm-greenhouse', from: 41.25, to: 49.0, text: 'Hasilnya: tanaman tumbuh seragam\ndan air nutrisi tidak terbuang.' },

  // 7 · Contoh 3: ternak & tambak
  { scene: 'm-livestock', from: 1.0, to: 5.75, text: 'Contoh ketiga: peternakan\ndan perikanan.' },
  { scene: 'm-livestock', from: 6.5, to: 11.0, text: 'Sapi bisa dipasangi kalung sensor\nberisi GPS dan sensor gerak.' },
  { scene: 'm-livestock', from: 11.75, to: 16.25, text: 'Jika aktivitasnya tiba-tiba turun,\npeternak mendapat peringatan dini.' },
  { scene: 'm-livestock', from: 17.0, to: 21.5, text: 'Sakit atau birahi pun lebih cepat\nterdeteksi, tanpa harus menebak.' },
  { scene: 'm-livestock', from: 22.25, to: 27.0, text: 'Di tambak udang, kadar oksigen terlarut\nsangat menentukan hidup-matinya udang.' },
  { scene: 'm-livestock', from: 27.75, to: 32.5, text: 'Oksigen biasanya turun pada malam hari\nhingga menjelang subuh.' },
  { scene: 'm-livestock', from: 33.25, to: 38.0, text: 'Sensor oksigen memantaunya terus-menerus,\nsiang dan malam.' },
  { scene: 'm-livestock', from: 38.75, to: 43.5, text: 'Saat oksigen turun di bawah batas,\nkincir air menyala otomatis.' },
  { scene: 'm-livestock', from: 44.25, to: 49.25, text: 'Pakan pun diberikan terjadwal oleh\npemberi pakan otomatis.' },

  // 8 · Contoh 4: perkebunan
  { scene: 'm-plantation', from: 1.0, to: 5.5, text: 'Contoh keempat: kebun dan\nperkebunan yang luas.' },
  { scene: 'm-plantation', from: 6.25, to: 10.75, text: 'Di sini, IoT membantu mengawasi\nribuan tanaman sekaligus.' },
  { scene: 'm-plantation', from: 11.5, to: 16.0, text: 'Stasiun cuaca mencatat suhu, kelembapan,\nhujan, dan basah daun.' },
  { scene: 'm-plantation', from: 16.75, to: 21.5, text: 'Daun yang lama basah dan udara lembap\nmeningkatkan risiko penyakit jamur.' },
  { scene: 'm-plantation', from: 22.25, to: 27.0, text: 'Sistem memberi peringatan dini, sebelum\npenyakit menyebar ke seluruh kebun.' },
  { scene: 'm-plantation', from: 27.75, to: 32.5, text: 'Drone memetakan kebun dan menandai\nblok yang perlu diperiksa.' },
  { scene: 'm-plantation', from: 33.25, to: 38.0, text: 'Di kebun cabai dan sayuran, sensor tanah\nmembantu penyiraman dan pemupukan.' },
  { scene: 'm-plantation', from: 38.75, to: 44.0, text: 'Semua data dari lahan yang luas\nterkumpul di satu layar.' },

  // 9 · Dasbor
  { scene: 'm-dashboard', from: 1.0, to: 5.5, text: 'Semua data bermuara di dasbor,\ndi ponsel atau komputer.' },
  { scene: 'm-dashboard', from: 6.25, to: 11.0, text: 'Petani melihat kondisi tiap petak\nsecara langsung.' },
  { scene: 'm-dashboard', from: 11.75, to: 16.5, text: 'Grafik menunjukkan tren kelembapan\ndari hari ke hari.' },
  { scene: 'm-dashboard', from: 17.25, to: 22.0, text: 'Peta menandai petak yang perlu\ndidahulukan.' },
  { scene: 'm-dashboard', from: 22.75, to: 27.5, text: 'Peringatan datang otomatis, misalnya\nsaat hujan akan turun.' },
  { scene: 'm-dashboard', from: 28.25, to: 33.0, text: 'Data cuaca membantu menunda irigasi,\nsehingga air lebih hemat.' },
  { scene: 'm-dashboard', from: 33.75, to: 38.5, text: 'Makin lama data terkumpul, makin akurat\nprediksi yang bisa dibuat.' },
  { scene: 'm-dashboard', from: 39.25, to: 44.0, text: 'Keputusan pun berdasarkan data,\nbukan lagi tebakan.' },

  // 10 · Manfaat, tantangan, cara memulai
  { scene: 'm-start', from: 1.0, to: 5.5, text: 'Manfaatnya: air dan pupuk lebih hemat,\nmasalah terdeteksi lebih awal.' },
  { scene: 'm-start', from: 6.25, to: 13.0, text: 'Hasil panen lebih terjaga, dan petani\nbekerja lebih efisien.' },
  { scene: 'm-start', from: 14.25, to: 18.75, text: 'Tantangannya: biaya perangkat\nmasih terasa mahal.' },
  { scene: 'm-start', from: 19.5, to: 26.0, text: 'Sinyal di desa belum merata,\ndan petani perlu pendampingan.' },
  { scene: 'm-start', from: 27.25, to: 31.75, text: 'Cara memulainya: pilih satu masalah\nyang paling penting dulu.' },
  { scene: 'm-start', from: 32.5, to: 36.5, text: 'Mulai dengan satu atau dua sensor,\npatungan lewat kelompok tani.' },
  { scene: 'm-start', from: 37.0, to: 39.75, text: 'Lalu perluas sedikit demi sedikit.' },

  // 11 · Penutup
  { scene: 'm-closing', from: 9.5, to: 14.0, text: 'Mari wujudkan pertanian Indonesia\nyang cerdas dan berkelanjutan.' },
];

export const MATERI_CUES = buildCues(MATERI_SCENES, CUES);

/** Musik: "Chasing Daylight" → crossfade 8 detik → "Affirmations" sampai akhir alaminya. */
const s = (x: number): number => Math.round(x * FPS);
const PART_B_START = s(248);
const AFFIRMATIONS_LEN = s(301.7);
export const MATERI_MUSIC: readonly MusicPlacement[] = [
  { creditId: 'musicChasingDaylight', startFrame: 0, durationInFrames: s(256), trimBeforeFrames: 0, fadeInFrames: s(2.5), fadeOutFrames: s(8) },
  {
    creditId: 'musicAffirmations',
    startFrame: PART_B_START,
    durationInFrames: MATERI_TOTAL_FRAMES - PART_B_START,
    trimBeforeFrames: AFFIRMATIONS_LEN - (MATERI_TOTAL_FRAMES - PART_B_START),
    fadeInFrames: s(8),
    fadeOutFrames: s(5),
  },
];

/** Angka faktual di film ini + sumbernya (verifikasi ulang sebelum publikasi). */
export const MATERI_FACTS = {
  awdThreshold: { value: '15', unit: 'cm', label: 'ambang AWD di bawah permukaan tanah', source: 'IRRI — Safe AWD' },
  awdSaving: { value: '±30', unit: '%', label: 'penghematan air irigasi (hingga)', source: 'IRRI' },
} as const;
export const MATERI_FACT_SOURCES = ['Kementerian ATR/BPN, 2019', 'BPS, Sensus Pertanian 2023', 'IRRI (International Rice Research Institute)'];
