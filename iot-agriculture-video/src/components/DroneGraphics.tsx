import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { colors, fonts, panel, status } from '../styles/theme';
import { Callout, easeOut, formatId } from './ui';
import { Icon } from './Icons';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

// ── HUD survei drone ─────────────────────────────────────────────────────

const AREA = { x: 420, y: 170, w: 1100, h: 560 } as const;
const PASSES = 6;

/** Titik di sepanjang rute zig-zag (lawnmower) pada progress 0–1. */
const routePoint = (p: number): { x: number; y: number } => {
  const total = PASSES * AREA.w + (PASSES - 1) * (AREA.h / (PASSES - 1));
  let d = p * total;
  const step = AREA.h / (PASSES - 1);
  for (let i = 0; i < PASSES; i++) {
    const y = AREA.y + i * step;
    const ltr = i % 2 === 0;
    if (d <= AREA.w) return { x: ltr ? AREA.x + d : AREA.x + AREA.w - d, y };
    d -= AREA.w;
    if (i < PASSES - 1) {
      if (d <= step) return { x: ltr ? AREA.x + AREA.w : AREA.x, y: y + d };
      d -= step;
    }
  }
  return { x: AREA.x + (PASSES % 2 === 0 ? 0 : AREA.w), y: AREA.y + AREA.h };
};

export const DroneSurveyHUD: React.FC<{ start?: number; duration?: number }> = ({ start = 20, duration = 250 }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [start, start + duration], [0, 1], clamp);
  const appear = interpolate(frame, [0, 20], [0, 1], { ...clamp, easing: easeOut });
  const head = routePoint(p);
  const samples = 220;
  const trail = Array.from({ length: Math.max(2, Math.round(samples * p)) }, (_, i) => routePoint((i / samples) * 1));
  const d = trail.map((pt, i) => `${i ? 'L' : 'M'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ') + ` L ${head.x} ${head.y}`;
  const fullD = Array.from({ length: samples + 1 }, (_, i) => routePoint(i / samples)).map((pt, i) => `${i ? 'L' : 'M'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(' ');
  const photos = Math.round(312 * p);
  const battery = 82 - 11 * p;
  const rec = Math.floor(frame / 12) % 2 === 0;

  return (
    <AbsoluteFill style={{ opacity: appear }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {/* bingkai jendela bidik */}
        {[
          [80, 70, 1, 1],
          [1840, 70, -1, 1],
          [80, 1010, 1, -1],
          [1840, 1010, -1, -1],
        ].map(([x, y, sx, sy]) => (
          <path key={`${x}-${y}`} d={`M ${x} ${(y ?? 0) + 46 * (sy ?? 1)} L ${x} ${y} L ${(x ?? 0) + 46 * (sx ?? 1)} ${y}`} stroke={colors.paper} strokeOpacity={0.7} strokeWidth={2} fill="none" />
        ))}
        <rect x={AREA.x} y={AREA.y} width={AREA.w} height={AREA.h} fill="none" stroke={colors.paper} strokeOpacity={0.35} strokeDasharray="8 8" />
        <path d={fullD} fill="none" stroke={colors.paper} strokeOpacity={0.18} strokeWidth={1.5} />
        {/* jejak area yang sudah dipotret */}
        <path d={d} fill="none" stroke={colors.rice} strokeOpacity={0.16} strokeWidth={AREA.h / (PASSES - 1)} strokeLinejoin="round" />
        <path d={d} fill="none" stroke={colors.rice} strokeWidth={2.5} />
        {/* titik pemotretan */}
        {Array.from({ length: Math.floor(48 * p) }, (_, i) => {
          const pt = routePoint(i / 48);
          return <circle key={i} cx={pt.x} cy={pt.y} r={3.5} fill={colors.paper} opacity={0.8} />;
        })}
        {/* drone */}
        <g transform={`translate(${head.x} ${head.y})`}>
          <circle r={40} fill="none" stroke={colors.rice} strokeOpacity={0.5} />
          <rect x={-60} y={-40} width={120} height={80} fill="none" stroke={colors.paper} strokeOpacity={0.6} strokeDasharray="4 4" />
          <g transform="translate(-24 -24)">
            <Icon name="drone" size={48} color={colors.paper} />
          </g>
        </g>
        <circle cx={1780} cy={112} r={9} fill={colors.alert} opacity={rec ? 1 : 0.25} />
        <text x={1760} y={119} textAnchor="end" fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 19 }}>
          PEMETAAN
        </text>
      </svg>
      <div style={{ position: 'absolute', left: 110, top: 190, width: 270, padding: '20px 22px', boxSizing: 'border-box', fontFamily: fonts.mono, color: colors.paper, fontSize: 19, lineHeight: 2, ...panel }}>
        <div style={{ fontSize: 15, letterSpacing: '0.14em', color: colors.paperDim }}>TELEMETRI</div>
        <div>KETINGGIAN 30 m</div>
        <div>KECEPATAN 6 m/s</div>
        <div>BATERAI {formatId(battery, 0)}%</div>
        <div>FOTO {photos}</div>
        <div style={{ color: colors.rice }}>TERPETAKAN {formatId(p * 100, 0)}%</div>
        <div style={{ fontSize: 14, color: colors.paperFaint, letterSpacing: '0.1em', marginTop: 6 }}>DATA ILUSTRASI</div>
      </div>
    </AbsoluteFill>
  );
};

// ── Peta kesehatan tanaman ───────────────────────────────────────────────

const COLS = 24;
const ROWS = 12;
const STRESS = { c: 16.5, r: 7.5 }; // pusat zona stres (sel)

const healthAt = (c: number, r: number): number => {
  const base = 0.78 + Math.sin(c * 0.55) * 0.06 + Math.cos(r * 0.7 + c * 0.2) * 0.05 + (random(`h${c}-${r}`) - 0.5) * 0.12;
  const dist = Math.hypot((c - STRESS.c) / 3.4, (r - STRESS.r) / 2.4);
  return Math.max(0, Math.min(1, base - Math.max(0, 1 - dist) * 0.55));
};

export const CropHealthMap: React.FC<{ sweepFrom?: number; calloutAt?: number }> = ({ sweepFrom = 20, calloutAt = 170 }) => {
  const frame = useCurrentFrame();
  const sweep = interpolate(frame, [sweepFrom, sweepFrom + 120], [0, 1], { ...clamp, easing: (t) => t });
  const cw = 1920 / COLS;
  const ch = 900 / ROWS;
  const scanX = sweep * 1920;
  const legendP = interpolate(frame, [sweepFrom + 100, sweepFrom + 124], [0, 1], clamp);
  return (
    <AbsoluteFill>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {Array.from({ length: COLS * ROWS }, (_, i) => {
          const c = i % COLS;
          const r = Math.floor(i / COLS);
          const x = c * cw;
          if (x > scanX) return null;
          const h = healthAt(c, r);
          const fill = h > 0.7 ? status.good : h > 0.5 ? status.fair : status.poor;
          const fresh = interpolate(scanX - x, [0, 120], [0.75, 0.38], clamp);
          return <rect key={i} x={x + 1} y={r * ch + 1} width={cw - 2} height={ch - 2} fill={fill} opacity={fresh} />;
        })}
        {sweep > 0 && sweep < 1 ? (
          <g>
            <rect x={scanX - 80} y={0} width={80} height={900} fill="url(#scanGlow)" />
            <line x1={scanX} x2={scanX} y1={0} y2={900} stroke={colors.paper} strokeWidth={2} />
          </g>
        ) : null}
        <defs>
          <linearGradient id="scanGlow" x1="0" x2="1">
            <stop offset="0%" stopColor={colors.paper} stopOpacity={0} />
            <stop offset="100%" stopColor={colors.paper} stopOpacity={0.25} />
          </linearGradient>
        </defs>
      </svg>
      <Callout x={STRESS.c * cw} y={STRESS.r * ch} dx={-260} dy={-170} label="Zona stres terdeteksi" sub="periksa air & hama di area ini" delay={calloutAt} />
      <div style={{ position: 'absolute', right: 96, top: 92, width: 360, padding: '22px 26px', boxSizing: 'border-box', fontFamily: fonts.sans, color: colors.paper, opacity: legendP, ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 15, letterSpacing: '0.14em', color: colors.paperDim }}>INDEKS KESEHATAN TANAMAN</div>
        {[
          [status.good, 'Sehat'],
          [status.fair, 'Perlu dipantau'],
          [status.poor, 'Perlu tindakan'],
        ].map(([c, l]) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, fontSize: 22 }}>
            <div style={{ width: 22, height: 22, borderRadius: 4, background: c }} />
            {l}
          </div>
        ))}
        <div style={{ fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, marginTop: 16, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
      </div>
    </AbsoluteFill>
  );
};
