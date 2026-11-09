import { sec } from '../../../lib/time';

/** Panjang crossfade antar-shot (frame). */
export const XF = 12;
/** Frame relatif ke awal shot untuk sebuah waktu scene (detik). */
export const rel = (sceneSec: number, shotStartSec: number): number => Math.round((sceneSec - shotStartSec) * 24);
export { sec };
