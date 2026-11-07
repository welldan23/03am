import { FPS } from '../data/video';

/** Detik → frame (dibulatkan ke frame terdekat). */
export const sec = (seconds: number): number => Math.round(seconds * FPS);

/** "mm:ss" → frame. Dipakai agar data storyboard bisa ditulis seperti timecode. */
export const tc = (timecode: string): number => {
  const [m, s] = timecode.split(':').map(Number);
  if (m === undefined || s === undefined || Number.isNaN(m) || Number.isNaN(s)) {
    throw new Error(`Timecode tidak valid: ${timecode}`);
  }
  return sec(m * 60 + s);
};

/** Frame → "mm:ss.ff" untuk label & log. */
export const formatTc = (frame: number): string => {
  const totalSec = Math.floor(frame / FPS);
  const ff = String(frame % FPS).padStart(2, '0');
  const mm = String(Math.floor(totalSec / 60)).padStart(2, '0');
  const ss = String(totalSec % 60).padStart(2, '0');
  return `${mm}:${ss}.${ff}`;
};
