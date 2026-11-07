import { interpolate, useCurrentFrame } from 'remotion';
import type { Fact } from '../data/facts';
import { colors, cornerScrim, fonts, safe, textShadow } from '../styles/theme';

interface StatCalloutProps {
  fact: Fact;
  delay?: number;
  hold?: number;
  align?: 'left' | 'right';
  /** Jarak dari atas layar (px). */
  top?: number;
}

/** Angka faktual kecil di pojok, selalu lengkap dengan sumbernya. */
export const StatCallout: React.FC<StatCalloutProps> = ({ fact, delay = 0, hold = 100, align = 'right', top = 150 }) => {
  const frame = useCurrentFrame() - delay;
  if (frame < 0) return null;
  const inP = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' });
  const out = interpolate(frame, [hold, hold + 14], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const bar = interpolate(frame, [6, 40], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  return (
    <div
      style={{
        position: 'absolute',
        top: top - 28,
        [align]: safe.x - 36,
        padding: '28px 36px',
        background: cornerScrim,
        textAlign: align,
        opacity: inP * out,
        transform: `translateX(${(align === 'right' ? 1 : -1) * (1 - inP) * 16}px)`,
        fontFamily: fonts.sans,
        color: colors.paper,
        textShadow,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
        <span style={{ fontSize: 76, fontWeight: 700, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>
          {fact.value}
        </span>
        <span style={{ fontSize: 30, fontWeight: 500, color: colors.paperDim }}>{fact.unit}</span>
      </div>
      <div
        style={{
          height: 2,
          width: 280 * bar,
          background: `linear-gradient(90deg, ${colors.rice}, rgba(201,217,107,0))`,
          margin: align === 'right' ? '10px 0 12px auto' : '10px 0 12px 0',
          transform: align === 'right' ? 'scaleX(-1)' : undefined,
        }}
      />
      <div style={{ fontSize: 24, fontWeight: 500 }}>{fact.label}</div>
      <div style={{ fontFamily: fonts.mono, fontSize: 15, marginTop: 8, color: colors.paperDim, letterSpacing: '0.06em' }}>
        Sumber: {fact.source}
      </div>
    </div>
  );
};
