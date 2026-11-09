import type { VoiceoverClip } from '../../data/voiceover';
import clips from './voiceover.generated.json';

/** Rekaman voice-over film 8 menit — dibuat oleh `npm run voiceover:scan -- materi`. */
export const MATERI_VO_CLIPS: readonly VoiceoverClip[] = clips as VoiceoverClip[];
