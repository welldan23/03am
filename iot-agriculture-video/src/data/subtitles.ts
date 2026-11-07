import { sec } from '../lib/time';
import { getScene, type SceneId } from './scenes';

/**
 * Teks layar (subtitle) Bahasa Indonesia. Video ini TANPA narasi, jadi subtitle
 * berfungsi sebagai "suara" dokumenter. Waktu ditulis RELATIF terhadap awal scene
 * (detik) supaya scene bisa digeser tanpa menghitung ulang semua cue.
 *
 * Aturan keterbacaan (dicek `npm run verify`):
 *  - durasi tampil ≥ 1,5 detik
 *  - kecepatan baca ≤ 17 karakter/detik
 *  - maksimal 2 baris × 42 karakter
 *  - jeda antar-cue ≥ 0,25 detik, tidak tumpang tindih
 */
export interface SubtitleCueInput {
  scene: SceneId;
  from: number; // detik, relatif ke awal scene
  to: number;
  text: string;
}

export interface SubtitleCue {
  id: string;
  scene: SceneId;
  startFrame: number; // absolut di timeline utama
  endFrame: number;
  text: string;
}

const CUES: readonly SubtitleCueInput[] = [
  // ── Scene 1 · Pengantar (00:00–00:30) ───────────────────────────────
  { scene: 'intro', from: 1.0, to: 4.5, text: 'Fajar menyingsing di atas sawah Nusantara.' },
  {
    scene: 'intro',
    from: 5.25,
    to: 10.25,
    text: 'Selama berabad-abad, petani membaca alam:\nlangit, angin, dan tanah.',
  },
  {
    scene: 'intro',
    from: 11.25,
    to: 16.0,
    text: 'Di Bali, sistem subak membagi air\nsecara adil sejak abad ke-9.',
  },
  {
    scene: 'intro',
    from: 16.75,
    to: 21.5,
    text: 'Kini cuaca makin sulit ditebak,\ndan setiap tetes air makin berharga.',
  },

  // ── Scene 2 · Apa itu IoT (00:30–01:10) ─────────────────────────────
  { scene: 'iot-basics', from: 1.25, to: 5.75, text: 'Internet of Things (IoT) adalah jaringan\nbenda yang saling terhubung.' },
  { scene: 'iot-basics', from: 6.25, to: 11.0, text: 'Benda itu bisa mengukur, mengirim data,\nbahkan bertindak sendiri.' },
  { scene: 'iot-basics', from: 14.5, to: 18.0, text: 'Sensor di lahan mengukur kondisi\ntanah, air, dan cuaca.' },
  { scene: 'iot-basics', from: 18.5, to: 22.5, text: 'Gateway mengirimkannya secara nirkabel,\nhingga beberapa kilometer.' },
  { scene: 'iot-basics', from: 23.0, to: 27.0, text: 'Data diolah di cloud, lalu tampil\ndi ponsel petani.' },
  { scene: 'iot-basics', from: 27.5, to: 30.75, text: 'Informasi pun berubah menjadi\ntindakan di lahan.' },
  { scene: 'iot-basics', from: 31.5, to: 38.5, text: 'Hasilnya: sawah yang bisa “berbicara”\ntentang apa yang ia butuhkan.' },

  // ── Scene 3 · Sensor (01:10–01:50) ──────────────────────────────────
  { scene: 'sensors', from: 1.5, to: 6.0, text: 'Di tengah lahan, stasiun kecil bertenaga\nsurya bekerja siang dan malam.' },
  { scene: 'sensors', from: 6.75, to: 10.5, text: 'Ia mencatat suhu, kelembapan udara,\ncurah hujan, dan angin.' },
  { scene: 'sensors', from: 11.5, to: 16.5, text: 'Di bawah tanah, sensor kelembapan\nmengukur air di beberapa kedalaman.' },
  { scene: 'sensors', from: 17.25, to: 22.5, text: 'Petani jadi tahu: apakah air sudah\nsampai ke akar, atau belum.' },
  { scene: 'sensors', from: 23.25, to: 27.0, text: 'Pengukuran diulang setiap beberapa menit.' },
  { scene: 'sensors', from: 28.5, to: 33.5, text: 'Sensor lain memantau pH dan suhu tanah,\nyang menentukan kesehatan tanaman.' },
  { scene: 'sensors', from: 34.25, to: 39.0, text: 'Semua angka ini dikirim otomatis,\ntanpa perlu dicatat dengan tangan.' },

  // ── Scene 4 · Irigasi otomatis (01:50–02:30) ────────────────────────
  { scene: 'irrigation', from: 1.5, to: 5.75, text: 'Air adalah sumber hidup sawah,\nnamun jumlahnya terbatas.' },
  { scene: 'irrigation', from: 6.25, to: 9.0, text: 'Bagaimana membaginya dengan cermat?' },
  { scene: 'irrigation', from: 10.0, to: 15.0, text: 'Saat sensor mendeteksi tanah mengering,\nsistem langsung memberi tanda.' },
  { scene: 'irrigation', from: 15.75, to: 21.0, text: 'Katup terbuka otomatis, dan air mengalir\nhanya ke petak yang membutuhkan.' },
  { scene: 'irrigation', from: 21.75, to: 27.5, text: 'Begitu kelembapan cukup, katup menutup.\nTidak ada air yang terbuang percuma.' },
  { scene: 'irrigation', from: 29.0, to: 33.75, text: 'Irigasi tetes membawa air\nlangsung ke akar tanaman.' },
  { scene: 'irrigation', from: 34.5, to: 39.0, text: 'Kearifan subak dan teknologi baru\nbisa berjalan berdampingan.' },

  // ── Scene 5 · Drone (02:30–03:10) ───────────────────────────────────
  { scene: 'drones', from: 1.25, to: 6.0, text: 'Dari udara, drone melihat apa\nyang tak terlihat dari pematang.' },
  { scene: 'drones', from: 8.5, to: 13.0, text: 'Drone terbang mengikuti rute otomatis,\nmemotret sawah petak demi petak.' },
  { scene: 'drones', from: 13.75, to: 19.0, text: 'Ratusan foto digabung menjadi satu\npeta sawah yang utuh.' },
  { scene: 'drones', from: 20.5, to: 25.5, text: 'Kamera khusus membaca warna daun\nuntuk menilai kesehatan tanaman.' },
  { scene: 'drones', from: 26.25, to: 31.0, text: 'Area yang kekurangan air atau terserang\nhama terlihat lebih awal.' },
  { scene: 'drones', from: 32.5, to: 38.5, text: 'Drone juga bisa menyemprot pupuk dan\npestisida tepat di titik yang perlu.' },

  // ── Scene 6 · Dasbor (03:10–03:50) ──────────────────────────────────
  { scene: 'dashboard', from: 1.5, to: 6.0, text: 'Semua data bermuara di satu tempat:\ndasbor pertanian.' },
  { scene: 'dashboard', from: 6.75, to: 11.5, text: 'Di ponsel atau komputer, petani melihat\nkondisi sawahnya saat ini.' },
  { scene: 'dashboard', from: 12.25, to: 17.0, text: 'Grafik menunjukkan kapan tanah mulai\nkering, hari demi hari.' },
  { scene: 'dashboard', from: 17.75, to: 23.0, text: 'Peta menandai petak yang perlu\ndiperhatikan lebih dulu.' },
  { scene: 'dashboard', from: 23.75, to: 28.5, text: 'Peringatan dikirim otomatis, misalnya saat\nhujan diprakirakan turun.' },
  { scene: 'dashboard', from: 29.25, to: 34.0, text: 'Irigasi bisa ditunda,\ndan air pun bisa dihemat.' },
  { scene: 'dashboard', from: 34.75, to: 39.0, text: 'Keputusan tak lagi berdasarkan tebakan,\nmelainkan data.' },

  // ── Scene 7 · Manfaat & tantangan (03:50–04:30) ─────────────────────
  { scene: 'benefits', from: 1.5, to: 6.0, text: 'Manfaatnya nyata: air lebih hemat,\npupuk lebih tepat sasaran.' },
  { scene: 'benefits', from: 6.75, to: 10.5, text: 'Hasil panen pun lebih mudah diprediksi.' },
  { scene: 'benefits', from: 11.5, to: 16.0, text: 'Masalah terdeteksi lebih awal,\nsebelum menjadi kerugian.' },
  { scene: 'benefits', from: 16.75, to: 20.0, text: 'Petani bekerja lebih cerdas,\nbukan lebih keras.' },
  { scene: 'benefits', from: 21.5, to: 26.0, text: 'Namun jalannya tidak selalu mudah.\nPerangkat masih terasa mahal.' },
  { scene: 'benefits', from: 26.75, to: 31.5, text: 'Di banyak desa, sinyal internet\nbelum stabil.' },
  { scene: 'benefits', from: 32.25, to: 39.0, text: 'Petani juga perlu pendampingan\nagar teknologi benar-benar terpakai.' },

  // ── Scene 8 · Masa depan (04:30–05:00) ──────────────────────────────
  { scene: 'future', from: 1.5, to: 6.25, text: 'Petani muda mulai bertani\ndengan cara-cara baru.' },
  { scene: 'future', from: 7.0, to: 11.75, text: 'Data, sensor, dan otomasi membuat lahan\nsempit pun bisa lebih produktif.' },
];

export const SUBTITLES: readonly SubtitleCue[] = CUES.map((c, i) => {
  const scene = getScene(c.scene);
  return {
    id: `${c.scene}-${i}`,
    scene: c.scene,
    startFrame: scene.startFrame + sec(c.from),
    endFrame: scene.startFrame + sec(c.to),
    text: c.text,
  };
});

export const SUBTITLE_RULES = {
  minDurationSec: 1.5,
  maxCharsPerSecond: 17,
  maxLines: 2,
  maxCharsPerLine: 42,
  minGapSec: 0.25,
} as const;
