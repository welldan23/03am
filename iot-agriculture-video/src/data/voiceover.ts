import { staticFile } from 'remotion';
import clips from './voiceover.generated.json';

/**
 * Rekaman voice-over manual (suara narator asli, bukan sintesis).
 * Daftar ini dibuat oleh `npm run voiceover:scan` dari isi public/assets/voiceover/.
 */
export interface VoiceoverClip {
  id: string;
  file: string;
  startFrame: number;
  durationInFrames: number;
}

export const VO_CLIPS: readonly VoiceoverClip[] = clips as VoiceoverClip[];
export const HAS_VOICEOVER = VO_CLIPS.length > 0;
export const voSrc = (c: VoiceoverClip): string => staticFile(`assets/${c.file}`);
