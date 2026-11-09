import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { fonts, safe } from '../styles/theme';

interface SubtitlesProps {
  cues: ReadonlyArray<{ startFrame: number; endFrame: number; text: string }>;
  /** Geser waktu (frame) — dipakai komposisi per-scene agar cue absolut tetap pas. */
  offset?: number;
}

const FADE = 6;

/**
 * Trek subtitle. Gaya dokumenter: teks putih, bayangan lembut, panel gelap tipis
 * yang hampir tak terlihat — terbaca di atas langit cerah maupun sawah gelap.
 */
export const Subtitles: React.FC<SubtitlesProps> = ({ cues, offset = 0 }) => {
  const frame = useCurrentFrame() + offset;
  const cue = cues.find((c) => frame >= c.startFrame && frame < c.endFrame);
  if (!cue) return null;

  const local = frame - cue.startFrame;
  const len = cue.endFrame - cue.startFrame;
  const opacity = interpolate(local, [0, FADE, len - FADE, len], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const lift = interpolate(local, [0, FADE * 2], [6, 0], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ justifyContent: 'flex-end', alignItems: 'center', pointerEvents: 'none' }}>
      <div
        style={{
          marginBottom: safe.bottom,
          maxWidth: 1400,
          padding: '14px 30px 16px',
          borderRadius: 6,
          background: 'linear-gradient(180deg, rgba(8,12,10,0.34), rgba(8,12,10,0.46))',
          backdropFilter: 'blur(2px)',
          opacity,
          transform: `translateY(${lift}px)`,
          fontFamily: fonts.sans,
          fontWeight: 500,
          fontSize: 40,
          lineHeight: 1.32,
          letterSpacing: '0.005em',
          color: '#f7f5ef',
          textAlign: 'center',
          whiteSpace: 'pre-line',
          textShadow: '0 1px 2px rgba(0,0,0,0.7), 0 0 14px rgba(0,0,0,0.35)',
        }}
      >
        {cue.text}
      </div>
    </AbsoluteFill>
  );
};
