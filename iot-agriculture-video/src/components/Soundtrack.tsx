import { Audio, interpolate, Sequence, useVideoConfig } from 'remotion';
import { SOUNDTRACK, soundtrackSrc } from '../data/audio';
import { TOTAL_FRAMES } from '../data/video';
import { HAS_VOICEOVER, VO_CLIPS, voSrc } from '../data/voiceover';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** 1 = narator sedang bicara di frame t (dengan ramp halus), 0 = diam. */
const speaking = (t: number): number => {
  const r = SOUNDTRACK.duckRampFrames;
  let v = 0;
  for (const c of VO_CLIPS) {
    const end = c.startFrame + c.durationInFrames;
    if (t < c.startFrame - r || t > end + r) continue;
    v = Math.max(v, interpolate(t, [c.startFrame - r, c.startFrame, end, end + r], [0, 1, 1, 0], clamp));
  }
  return v;
};

interface AudioProps {
  /** Mulai dari frame ke berapa di timeline utama (untuk komposisi per-scene). */
  offset?: number;
}

/**
 * Musik latar + voice-over. Tanpa rekaman: musik penuh. Dengan rekaman: musik turun
 * jadi latar dan "minggir" (ducking) setiap kali narator bicara. Semua dihitung dari
 * posisi di timeline UTAMA, jadi preview per-scene terdengar sama dengan film penuh.
 */
export const Soundtrack: React.FC<AudioProps> = ({ offset = 0 }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const fadeIn = SOUNDTRACK.fadeInSec * fps;
  const fadeOut = SOUNDTRACK.fadeOutSec * fps;
  return (
    <>
      <Audio
        src={soundtrackSrc()}
        trimBefore={offset}
        volume={(f) => {
          const t = f + offset;
          const envelope = interpolate(t, [0, fadeIn, TOTAL_FRAMES - fadeOut, TOTAL_FRAMES], [0, 1, 1, 0], clamp);
          const level = HAS_VOICEOVER
            ? SOUNDTRACK.bedVolume + (SOUNDTRACK.duckedVolume - SOUNDTRACK.bedVolume) * speaking(t)
            : SOUNDTRACK.volume;
          return envelope * level;
        }}
      />
      {VO_CLIPS.map((c) => {
        const from = c.startFrame - offset;
        if (from + c.durationInFrames <= 0 || from >= durationInFrames) return null;
        return (
          <Sequence key={c.id} name={`VO ${c.id}`} from={Math.max(0, from)} durationInFrames={c.durationInFrames - Math.max(0, -from)} layout="none">
            <Audio src={voSrc(c)} trimBefore={Math.max(0, -from)} />
          </Sequence>
        );
      })}
    </>
  );
};
