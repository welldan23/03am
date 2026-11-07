import { staticFile } from 'remotion';
import { CREDITS } from './assets';

/**
 * Musik latar — instrumental saja (piano, string, synth), TANPA suara orang.
 * "Affirmations" oleh Scott Buckley, CC BY 4.0, via Wikimedia Commons.
 * Atribusi otomatis tampil di kredit penutup (kind: 'audio').
 */
export const SOUNDTRACK = {
  id: 'musicAffirmations',
  /** Volume tanpa voice-over (0–1). Sumber ~−14 LUFS; 0,85 ≈ −15,5 LUFS. */
  volume: 0.85,
  /** Dengan voice-over: musik jadi latar… */
  bedVolume: 0.32,
  /** …dan turun lagi saat narator bicara (ducking). */
  duckedVolume: 0.14,
  /** Lama transisi naik/turun ducking (frame). */
  duckRampFrames: 10,
  fadeInSec: 2.5,
  fadeOutSec: 5,
} as const;

export const soundtrackSrc = (): string => {
  const c = CREDITS.find((x) => x.id === SOUNDTRACK.id);
  if (!c) throw new Error('Musik belum diunduh. Jalankan npm run fetch-assets.');
  return staticFile(`assets/${c.file}`);
};
