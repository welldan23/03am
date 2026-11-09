import { Audio, interpolate, Sequence, staticFile, useVideoConfig } from 'remotion';
import { CREDITS } from '../data/assets';
import { SOUNDTRACK } from '../data/audio';
import { TOTAL_FRAMES } from '../data/video';
import { VO_CLIPS, voSrc, type VoiceoverClip } from '../data/voiceover';
import type { MusicPlacement } from '../lib/film';
import { speaking } from '../lib/voiceDuck';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** Film 5 menit: satu lagu penuh dari awal. */
const DEFAULT_TRACKS: readonly MusicPlacement[] = [
  {
    creditId: SOUNDTRACK.id,
    startFrame: 0,
    durationInFrames: TOTAL_FRAMES,
    trimBeforeFrames: 0,
    fadeInFrames: Math.round(SOUNDTRACK.fadeInSec * 24),
    fadeOutFrames: Math.round(SOUNDTRACK.fadeOutSec * 24),
  },
];

const musicSrc = (creditId: string): string => {
  const c = CREDITS.find((x) => x.id === creditId);
  if (!c) throw new Error(`Musik ${creditId} belum diunduh. Jalankan npm run fetch-assets.`);
  return staticFile(`assets/${c.file}`);
};

interface SoundtrackProps {
  /** Mulai dari frame ke berapa di timeline utama (untuk komposisi per-scene). */
  offset?: number;
  tracks?: readonly MusicPlacement[];
  clips?: readonly VoiceoverClip[];
}

/**
 * Musik latar (satu lagu atau beberapa lagu bersambung) + voice-over. Tanpa rekaman:
 * musik penuh. Dengan rekaman: musik turun jadi latar dan "minggir" (ducking) setiap
 * narator bicara. Semua dihitung dari posisi di timeline UTAMA.
 */
export const Soundtrack: React.FC<SoundtrackProps> = ({ offset = 0, tracks = DEFAULT_TRACKS, clips = VO_CLIPS }) => {
  const { durationInFrames } = useVideoConfig();
  const hasVo = clips.length > 0;
  const visible = (from: number, len: number): boolean => from + len > 0 && from < durationInFrames;
  return (
    <>
      {tracks.map((tr) => {
        const from = tr.startFrame - offset;
        if (!visible(from, tr.durationInFrames)) return null;
        const skip = Math.max(0, -from);
        return (
          <Sequence key={tr.creditId + tr.startFrame} name={`Musik ${tr.creditId}`} from={Math.max(0, from)} durationInFrames={tr.durationInFrames - skip} layout="none">
            <Audio
              src={musicSrc(tr.creditId)}
              trimBefore={tr.trimBeforeFrames + skip}
              volume={(f) => {
                const local = f + skip;
                const t = tr.startFrame + local;
                const env = interpolate(
                  local,
                  [0, Math.max(1, tr.fadeInFrames), tr.durationInFrames - Math.max(1, tr.fadeOutFrames), tr.durationInFrames],
                  [0, 1, 1, 0],
                  clamp,
                );
                const level = hasVo ? SOUNDTRACK.bedVolume + (SOUNDTRACK.duckedVolume - SOUNDTRACK.bedVolume) * speaking(t, clips) : SOUNDTRACK.volume;
                return env * level;
              }}
            />
          </Sequence>
        );
      })}
      {clips.map((c) => {
        const from = c.startFrame - offset;
        if (!visible(from, c.durationInFrames)) return null;
        return (
          <Sequence key={c.id} name={`VO ${c.id}`} from={Math.max(0, from)} durationInFrames={c.durationInFrames - Math.max(0, -from)} layout="none">
            <Audio src={voSrc(c)} trimBefore={Math.max(0, -from)} />
          </Sequence>
        );
      })}
    </>
  );
};
