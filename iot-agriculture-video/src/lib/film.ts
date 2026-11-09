import type { TransitionStyle } from '../data/scenes';
import { sec, tc } from './time';

/**
 * Tipe generik "film" — supaya beberapa video (5 menit, 8 menit, …) bisa memakai
 * komponen, subtitle, musik, dan voice-over yang sama.
 */
export interface FilmSceneInput {
  id: string;
  number: number;
  /** Nama komposisi per-scene di Remotion Studio (huruf, angka, '-'). */
  compositionId: string;
  title: string;
  kicker: string;
  start: string; // mm:ss
  end: string;
  transitionIn: TransitionStyle;
}

export interface FilmScene extends FilmSceneInput {
  startFrame: number;
  endFrame: number;
  durationInFrames: number;
}

export const buildScenes = (inputs: readonly FilmSceneInput[]): FilmScene[] =>
  inputs.map((s) => {
    const startFrame = tc(s.start);
    const endFrame = tc(s.end);
    return { ...s, startFrame, endFrame, durationInFrames: endFrame - startFrame };
  });

export interface CueInput {
  scene: string;
  /** Detik relatif ke awal scene. */
  from: number;
  to: number;
  text: string;
}

export interface Cue {
  /** s<nomor scene>-<urutan>, juga nama file rekaman voice-over. */
  id: string;
  scene: string;
  startFrame: number;
  endFrame: number;
  text: string;
}

export const buildCues = (scenes: readonly FilmScene[], inputs: readonly CueInput[]): Cue[] => {
  const perScene = new Map<string, number>();
  return inputs.map((c) => {
    const scene = scenes.find((s) => s.id === c.scene);
    if (!scene) throw new Error(`Subtitle merujuk scene tak dikenal: ${c.scene}`);
    const n = (perScene.get(c.scene) ?? 0) + 1;
    perScene.set(c.scene, n);
    return {
      id: `s${scene.number}-${String(n).padStart(2, '0')}`,
      scene: c.scene,
      startFrame: scene.startFrame + sec(c.from),
      endFrame: scene.startFrame + sec(c.to),
      text: c.text,
    };
  });
};

/** Satu lagu yang ditempatkan di timeline (beberapa lagu bisa disambung dengan crossfade). */
export interface MusicPlacement {
  /** id di credits.generated.json, mis. 'musicAffirmations'. */
  creditId: string;
  startFrame: number;
  durationInFrames: number;
  /** Lewati awal lagu sebanyak ini (frame). */
  trimBeforeFrames: number;
  fadeInFrames: number;
  fadeOutFrames: number;
}
