import { interpolate, useCurrentFrame } from 'remotion';
import { colors, cornerScrim, fonts, safe, textShadow } from '../styles/theme';

interface LocationTagProps {
  place: string;
  region: string;
  /** Koordinat opsional, contoh "8°22′ LS · 115°08′ BT". */
  coords?: string;
  /** Frame mulai & lama tampil (relatif ke Sequence induk). */
  delay?: number;
  hold?: number;
}

/** Label lokasi ala dokumenter: garis tipis yang tumbuh, lalu teks naik pelan. */
export const LocationTag: React.FC<LocationTagProps> = ({ place, region, coords, delay = 10, hold = 90 }) => {
  const frame = useCurrentFrame() - delay;
  const line = interpolate(frame, [0, 16], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const text = interpolate(frame, [8, 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const out = interpolate(frame, [hold, hold + 14], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (frame < 0) return null;

  return (
    <div
      style={{
        position: 'absolute',
        left: safe.x - 36,
        top: safe.top + 8 - 28,
        padding: '28px 36px',
        background: cornerScrim,
        opacity: out,
        fontFamily: fonts.sans,
        color: colors.paper,
        textShadow,
      }}
    >
      <div style={{ width: 64 * line, height: 2, background: colors.sun, marginBottom: 14 }} />
      <div
        style={{
          opacity: text,
          transform: `translateY(${(1 - text) * 10}px)`,
          fontSize: 30,
          fontWeight: 700,
          letterSpacing: '0.02em',
        }}
      >
        {place}
      </div>
      <div style={{ opacity: text * 0.85, fontSize: 21, fontWeight: 400, marginTop: 4, letterSpacing: '0.04em' }}>
        {region}
      </div>
      {coords ? (
        <div
          style={{
            opacity: text * 0.9,
            fontFamily: fonts.mono,
            fontSize: 16,
            marginTop: 10,
            letterSpacing: '0.08em',
            color: colors.paperDim,
          }}
        >
          {coords}
        </div>
      ) : null}
    </div>
  );
};
