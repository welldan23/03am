import { staticFile } from 'remotion';
import { CREDITS } from './assets';
import { getScene, SCENE_TIMINGS, type SceneId } from './scenes';
import { FPS } from './video';

/**
 * Efek suara & suasana. Dua jenis sumber:
 *  - Rekaman alam (Wikimedia Commons, CC) — burung, tonggeret Jawa Timur, aliran air, hujan.
 *    Dinormalisasi ke −24 LUFS saat diunduh (npm run fetch-assets).
 *  - Efek sintetis buatan sendiri (npm run make-sfx) — whoosh, tik UI, blip, katup, dll.
 * TIDAK ada suara orang. Waktu `at` dalam detik, relatif ke awal scene (boleh negatif
 * sedikit untuk whoosh yang dimulai tepat sebelum transisi).
 */
/**
 * Saklar efek suara. Atas permintaan owner, film memakai MUSIK LATAR SAJA,
 * jadi efek & suasana dimatikan. Ganti ke `true` untuk menyalakannya lagi.
 */
export const SFX_ENABLED = false;

export type SoundId =
  | 'birds'
  | 'cicada'
  | 'stream'
  | 'rain'
  | 'whoosh'
  | 'impact'
  | 'tick'
  | 'blip'
  | 'alert'
  | 'valve'
  | 'drip'
  | 'scan'
  | 'drone'
  | 'wind';

const AMBIENCE: Partial<Record<SoundId, string>> = {
  birds: 'ambDawnBirds',
  cicada: 'ambCicadaJava',
  stream: 'ambStream',
  rain: 'ambRain',
};
const SYNTH: Partial<Record<SoundId, string>> = {
  whoosh: 'whoosh',
  impact: 'impact',
  tick: 'tick',
  blip: 'blip',
  alert: 'alert',
  valve: 'valve',
  drip: 'drip',
  scan: 'scan',
  drone: 'drone-loop',
  wind: 'wind-loop',
};

export const soundSrc = (id: SoundId): string => {
  const amb = AMBIENCE[id];
  if (amb) {
    const c = CREDITS.find((x) => x.id === amb);
    if (!c) throw new Error(`Suasana ${id} belum diunduh. Jalankan npm run fetch-assets.`);
    return staticFile(`assets/${c.file}`);
  }
  return staticFile(`assets/sfx/${SYNTH[id] ?? id}.wav`);
};

/** Suara yang panjangnya diatur `dur` dan diulang kalau file lebih pendek. */
const LOOPABLE = new Set<SoundId>(['birds', 'cicada', 'stream', 'rain', 'drone', 'wind']);
export const isLoopable = (id: SoundId): boolean => LOOPABLE.has(id);

interface CueInput {
  at: number;
  sound: SoundId;
  vol: number;
  /** Lama (detik) — wajib untuk suasana/loop. */
  dur?: number;
  fadeIn?: number;
  fadeOut?: number;
}

const bed = (sound: SoundId, at: number, dur: number, vol: number, fadeIn = 2, fadeOut = 2): CueInput => ({ sound, at, dur, vol, fadeIn, fadeOut });
const hits = (sound: SoundId, vol: number, ...times: number[]): CueInput[] => times.map((at) => ({ sound, at, vol }));

/** Whoosh di setiap pergantian scene (kecuali scene pertama yang muncul dari hitam). */
const TRANSITION: CueInput = { sound: 'whoosh', at: -0.15, vol: 0.32 };

const CUES: Record<SceneId, readonly CueInput[]> = {
  // 00:00–00:30 — fajar, terasering, petani, judul
  intro: [
    bed('birds', 0, 31, 0.5, 3, 2.5),
    bed('cicada', 9, 13.5, 0.28, 3, 2.5),
    bed('wind', 5, 26, 0.14, 3, 3),
    ...hits('tick', 0.22, 5.7, 11.6, 17.1),
    ...hits('blip', 0.18, 6.6, 17.75),
    { sound: 'whoosh', at: 21.7, vol: 0.28 },
    { sound: 'impact', at: 23.2, vol: 0.55 },
    ...hits('blip', 0.12, 25.8, 26.15, 26.5, 26.85),
  ],
  // 00:30–01:10 — apa itu IoT
  'iot-basics': [
    TRANSITION,
    bed('cicada', 0, 14.5, 0.3),
    ...hits('blip', 0.11, 1.7, 2.45, 3.2, 3.95, 4.7),
    { sound: 'whoosh', at: 13.3, vol: 0.18 },
    ...hits('blip', 0.3, 14.5, 18.25, 23.0, 25.0),
    { sound: 'tick', at: 27.6, vol: 0.3 },
    bed('cicada', 30.5, 10.5, 0.3, 2, 1.5),
    bed('wind', 30.5, 10.5, 0.14, 2, 1.5),
    ...hits('blip', 0.11, 31.1, 31.5, 31.9),
  ],
  // 01:10–01:50 — sensor
  sensors: [
    TRANSITION,
    bed('wind', 0, 11, 0.3, 1.5, 1.5),
    bed('cicada', 0, 11, 0.15, 1.5, 1.5),
    ...hits('tick', 0.3, 5.4, 6.25, 7.1),
    { sound: 'valve', at: 10.85, vol: 0.4 },
    bed('rain', 13.0, 6.5, 0.5, 0.8, 1.5),
    ...hits('drip', 0.2, 13.4, 14.0, 14.9),
    { sound: 'blip', at: 20.9, vol: 0.3 },
    bed('cicada', 27.5, 13.5, 0.3, 2, 1.5),
    ...hits('tick', 0.3, 28.75, 29.85, 30.9),
  ],
  // 01:50–02:30 — irigasi
  irrigation: [
    TRANSITION,
    bed('stream', 0, 9.8, 0.7, 1, 1.5),
    { sound: 'alert', at: 11.5, vol: 0.32 },
    { sound: 'valve', at: 15.5, vol: 0.6 },
    bed('stream', 15.6, 6.5, 0.3, 0.6, 0.8),
    { sound: 'valve', at: 22.0, vol: 0.5 },
    { sound: 'blip', at: 22.3, vol: 0.25 },
    bed('cicada', 28, 13, 0.25, 1.5, 1.5),
    ...hits('drip', 0.25, 34.6, 35.5, 36.6, 37.5, 38.6, 39.4),
  ],
  // 02:30–03:10 — drone
  drones: [
    TRANSITION,
    bed('drone', 0, 8, 0.45, 1, 1),
    bed('cicada', 0, 8, 0.2, 1, 1),
    bed('wind', 7.5, 12.5, 0.35, 1, 1),
    bed('drone', 7.5, 12.5, 0.28, 1, 1),
    { sound: 'tick', at: 7.6, vol: 0.25 },
    { sound: 'scan', at: 20.33, vol: 0.35 },
    { sound: 'tick', at: 24.5, vol: 0.25 },
    { sound: 'blip', at: 26.17, vol: 0.3 },
    bed('drone', 31.5, 9.5, 0.4, 1.5, 1.5),
    bed('cicada', 31.5, 9.5, 0.2, 1.5, 1.5),
  ],
  // 03:10–03:50 — dasbor
  dashboard: [
    TRANSITION,
    ...hits('tick', 0.2, 3.5, 3.92, 4.25, 4.58, 4.92),
    ...hits('tick', 0.17, 5.17, 5.67, 6.17, 6.67, 7.17),
    ...hits('whoosh', 0.13, 9.0, 16.5, 27.0, 34.0),
    { sound: 'alert', at: 23.5, vol: 0.28 },
    ...hits('blip', 0.25, 25.17, 26.83),
  ],
  // 03:50–04:30 — manfaat & tantangan
  benefits: [
    TRANSITION,
    bed('birds', 0, 20.5, 0.35),
    bed('stream', 10, 10.5, 0.4, 1, 1.5),
    { sound: 'whoosh', at: 19.9, vol: 0.2 },
    bed('wind', 20, 21, 0.22, 1.5, 1.5),
    bed('cicada', 20, 21, 0.25, 1.5, 1.5),
    ...hits('tick', 0.28, 1.5, 3.5, 6.75, 11.5, 16.75),
    ...hits('tick', 0.28, 21.5, 26.75, 32.25, 35.5),
  ],
  // 04:30–05:00 — masa depan & kredit
  future: [
    TRANSITION,
    bed('birds', 0, 20.5, 0.4, 2, 2.5),
    { sound: 'impact', at: 12.8, vol: 0.3 },
  ],
};

export interface SfxCue {
  key: string;
  sound: SoundId;
  startFrame: number; // absolut di timeline utama
  durationInFrames: number;
  volume: number;
  fadeIn: number; // frame
  fadeOut: number;
}

/** Lama bawaan one-shot (detik) — sedikit lebih panjang dari filenya, aman. */
const ONE_SHOT_SEC: Partial<Record<SoundId, number>> = {
  whoosh: 1.7,
  impact: 3.6,
  tick: 0.2,
  blip: 0.3,
  alert: 0.8,
  valve: 0.7,
  drip: 0.4,
  scan: 5.1,
};

export const SFX_CUES: readonly SfxCue[] = SCENE_TIMINGS.flatMap((scene) =>
  (CUES[scene.id] ?? []).map((c, i) => {
    const s = getScene(scene.id);
    const dur = c.dur ?? ONE_SHOT_SEC[c.sound] ?? 1;
    return {
      key: `${scene.id}-${i}-${c.sound}`,
      sound: c.sound,
      startFrame: Math.max(0, s.startFrame + Math.round(c.at * FPS)),
      durationInFrames: Math.round(dur * FPS),
      volume: c.vol,
      fadeIn: Math.round((c.fadeIn ?? 0) * FPS),
      fadeOut: Math.round((c.fadeOut ?? 0) * FPS),
    };
  }),
);
