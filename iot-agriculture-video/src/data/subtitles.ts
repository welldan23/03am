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
