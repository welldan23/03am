import type { CSSProperties } from 'react';
import { Easing, interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts, panel } from '../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);

/** Progress 0→1 antara dua frame, dengan easing keluar yang lembut. */
export const useProgress = (from: number, duration: number, easing = easeOut): number => {
  const frame = useCurrentFrame();
  return interpolate(frame, [from, from + Math.max(1, duration)], [0, 1], { ...clamp, easing });
};

/** Format angka gaya Indonesia: koma desimal, titik ribuan. */
export const formatId = (value: number, decimals = 0): string =>
  value.toLocaleString('id-ID', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

interface PanelProps {
  x: number;
  y: number;
  w: number;
  h?: number;
  /** Frame mulai muncul. */
  delay?: number;
  title?: string;
  style?: CSSProperties;
  children?: React.ReactNode;
}

/** Kartu data yang muncul halus (naik + fade). */
export const Panel: React.FC<PanelProps> = ({ x, y, w, h, delay = 0, title, style, children }) => {
  const p = useProgress(delay, 22);
  if (p <= 0) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: w,
        height: h,
        padding: '22px 26px',
        boxSizing: 'border-box',
        opacity: p,
        transform: `translateY(${(1 - p) * 18}px)`,
        fontFamily: fonts.sans,
        color: colors.paper,
        ...panel,
        ...style,
      }}
    >
      {title ? (
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 16,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: colors.paperDim,
            marginBottom: 14,
          }}
        >
          {title}
        </div>
      ) : null}
      {children}
    </div>
  );
};

interface CountUpProps {
  to: number;
  from?: number;
  delay?: number;
  duration?: number;
  decimals?: number;
  style?: CSSProperties;
}

/** Angka yang "berjalan" ke nilai akhirnya. */
export const CountUp: React.FC<CountUpProps> = ({ to, from = 0, delay = 0, duration = 36, decimals = 0, style }) => {
  const p = useProgress(delay, duration);
  return <span style={{ fontVariantNumeric: 'tabular-nums', ...style }}>{formatId(from + (to - from) * p, decimals)}</span>;
};

interface MetricProps {
  label: string;
  value: number;
  unit: string;
  decimals?: number;
  delay?: number;
  accent?: string;
  size?: number;
}

/** Satu angka besar + label + satuan. */
export const Metric: React.FC<MetricProps> = ({ label, value, unit, decimals = 0, delay = 0, accent = colors.paper, size = 56 }) => (
  <div style={{ fontFamily: fonts.sans }}>
    <div style={{ fontSize: 19, color: colors.paperDim, marginBottom: 6 }}>{label}</div>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <CountUp to={value} decimals={decimals} delay={delay} style={{ fontSize: size, fontWeight: 700, color: accent, letterSpacing: '-0.02em' }} />
      <span style={{ fontSize: size * 0.42, color: colors.paperDim, fontWeight: 500 }}>{unit}</span>
    </div>
  </div>
);

/** Penanda kecil bahwa angka di layar adalah contoh, bukan pengukuran sungguhan. */
export const IllustrativeTag: React.FC<{ x: number; y: number; delay?: number }> = ({ x, y, delay = 0 }) => {
  const p = useProgress(delay, 16);
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        opacity: p * 0.8,
        fontFamily: fonts.mono,
        fontSize: 15,
        letterSpacing: '0.16em',
        color: colors.paperDim,
        border: '1px solid rgba(244,241,234,0.25)',
        borderRadius: 4,
        padding: '4px 10px',
      }}
    >
      DATA ILUSTRASI
    </div>
  );
};

interface CalloutProps {
  /** Titik yang ditunjuk (px layar). */
  x: number;
  y: number;
  /** Posisi label relatif ke titik. */
  dx: number;
  dy: number;
  label: string;
  sub?: string;
  delay?: number;
}

/** Label penunjuk: titik → garis siku → teks. Dipakai untuk menamai bagian alat di foto. */
export const Callout: React.FC<CalloutProps> = ({ x, y, dx, dy, label, sub, delay = 0 }) => {
  const p = useProgress(delay, 20);
  const t = useProgress(delay + 10, 16);
  if (p <= 0) return null;
  const ex = x + dx;
  const ey = y + dy;
  const right = dx >= 0;
  const len = Math.hypot(dx, dy) + 60;
  return (
    <>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
        <circle cx={x} cy={y} r={7} fill="none" stroke={colors.paper} strokeWidth={2} opacity={p} />
        <circle cx={x} cy={y} r={2.5} fill={colors.rice} opacity={p} />
        <path
          d={`M ${x} ${y} L ${ex} ${ey} L ${ex + (right ? 60 : -60)} ${ey}`}
          fill="none"
          stroke={colors.paper}
          strokeOpacity={0.8}
          strokeWidth={1.5}
          strokeDasharray={len}
          strokeDashoffset={len * (1 - p)}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          left: right ? ex + 72 : undefined,
          right: right ? undefined : 1920 - ex + 72,
          top: ey - 20,
          opacity: t,
          transform: `translateX(${(1 - t) * (right ? -10 : 10)}px)`,
          fontFamily: fonts.sans,
          color: colors.paper,
          textAlign: right ? 'left' : 'right',
          textShadow: '0 2px 12px rgba(0,0,0,0.7)',
        }}
      >
        <div style={{ fontSize: 28, fontWeight: 700 }}>{label}</div>
        {sub ? <div style={{ fontSize: 20, color: colors.paperDim, marginTop: 2 }}>{sub}</div> : null}
      </div>
    </>
  );
};

/** Judul bab di awal setiap scene. */
export const ChapterTitle: React.FC<{ kicker: string; title: string; delay?: number; hold?: number }> = ({
  kicker,
  title,
  delay = 8,
  hold = 100,
}) => {
  const frame = useCurrentFrame();
  const p = useProgress(delay, 26);
  const line = useProgress(delay + 4, 30);
  const out = interpolate(frame, [delay + hold, delay + hold + 16], [1, 0], clamp);
  if (p <= 0 || out <= 0) return null;
  return (
    <div style={{ position: 'absolute', left: 96, top: 92, opacity: out, fontFamily: fonts.sans, color: colors.paper }}>
      <div style={{ fontFamily: fonts.mono, fontSize: 18, letterSpacing: '0.3em', color: colors.rice, opacity: p }}>
        {kicker.toUpperCase()}
      </div>
      <div style={{ width: 90 * line, height: 2, background: colors.sun, margin: '14px 0 16px' }} />
      <div style={{ overflow: 'hidden' }}>
        <div
          style={{
            fontSize: 60,
            fontWeight: 700,
            letterSpacing: '-0.01em',
            transform: `translateY(${(1 - p) * 100}%)`,
            textShadow: '0 4px 30px rgba(0,0,0,0.55)',
          }}
        >
          {title}
        </div>
      </div>
    </div>
  );
};
