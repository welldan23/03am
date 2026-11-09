import { interpolate } from 'remotion';
import { SOUNDTRACK } from '../data/audio';
import { VO_CLIPS, type VoiceoverClip } from '../data/voiceover';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** 1 = narator sedang bicara di frame t (dengan ramp halus), 0 = diam. */
export const speaking = (t: number, clips: readonly VoiceoverClip[] = VO_CLIPS): number => {
  const r = SOUNDTRACK.duckRampFrames;
  let v = 0;
  for (const c of clips) {
    const end = c.startFrame + c.durationInFrames;
    if (t < c.startFrame - r || t > end + r) continue;
    v = Math.max(v, interpolate(t, [c.startFrame - r, c.startFrame, end, end + r], [0, 1, 1, 0], clamp));
  }
  return v;
};
