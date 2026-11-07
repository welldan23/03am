import { interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts, panel } from '../styles/theme';
import { Icon, type IconName } from './Icons';
import { easeOut } from './ui';

export interface Point {
  icon: IconName;
  title: string;
  desc: string;
  at: number;
}

interface PointListProps {
  heading: string;
  accent: string;
  points: readonly Point[];
  /** Panjang tampil (frame) — dipakai untuk fade-out di akhir. */
  durationInFrames: number;
}

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/** Daftar poin bernomor di sisi kanan, tiap poin masuk bergiliran mengikuti subtitle. */
export const PointList: React.FC<PointListProps> = ({ heading, accent, points, durationInFrames }) => {
  const frame = useCurrentFrame();
  const head = interpolate(frame, [0, 22], [0, 1], { ...clamp, easing: easeOut });
  const out = interpolate(frame, [durationInFrames - 16, durationInFrames], [1, 0], clamp);
  return (
    <div style={{ position: 'absolute', left: 1160, top: 120, width: 650, opacity: out, fontFamily: fonts.sans, color: colors.paper }}>
      <div style={{ opacity: head, fontFamily: fonts.mono, fontSize: 20, letterSpacing: '0.32em', color: accent }}>{heading}</div>
      <div style={{ width: 120 * head, height: 2, background: accent, margin: '14px 0 22px' }} />
      {points.map((pt, i) => {
        const p = interpolate(frame, [pt.at, pt.at + 20], [0, 1], { ...clamp, easing: easeOut });
        if (p <= 0) return null;
        return (
          <div
            key={pt.title}
            style={{
              display: 'flex',
              gap: 22,
              alignItems: 'center',
              padding: '18px 22px',
              marginBottom: 14,
              opacity: p,
              transform: `translateX(${(1 - p) * 30}px)`,
              ...panel,
            }}
          >
            <div style={{ fontFamily: fonts.mono, fontSize: 18, color: accent, width: 30 }}>0{i + 1}</div>
            <Icon name={pt.icon} size={46} color={accent} />
            <div>
              <div style={{ fontSize: 29, fontWeight: 700 }}>{pt.title}</div>
              <div style={{ fontSize: 20, color: colors.paperDim, marginTop: 4 }}>{pt.desc}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
