import type { FilmDefinition } from '../../compositions/Film';
import { MATERI_COMPONENTS } from './scenes';
import { MATERI_CUES, MATERI_MUSIC, MATERI_SCENES, MATERI_TOTAL_FRAMES } from './timeline';
import { MATERI_VO_CLIPS } from './voiceover';

export const MATERI_FILM: FilmDefinition = {
  totalFrames: MATERI_TOTAL_FRAMES,
  scenes: MATERI_SCENES,
  components: MATERI_COMPONENTS,
  cues: MATERI_CUES,
  music: MATERI_MUSIC,
  voiceover: MATERI_VO_CLIPS,
};
