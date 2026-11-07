import { interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts } from '../styles/theme';
import { easeOut } from './ui';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

interface LineChartProps {
  data: readonly number[];
  width: number;
  height: number;
  min: number;
  max: number;
  delay?: number;
  /** Lama garis tergambar (frame). */
  duration?: number;
  color?: string;
  /** Garis ambang batas horizontal (misal batas kering). */
  threshold?: { value: number; label: string };
  labels?: readonly string[];
  unit?: string;
}

/** Grafik garis yang tergambar dari kiri ke kanan, dengan area tipis di bawahnya. */
export const LineChart: React.FC<LineChartProps> = ({
  data,
  width,
  height,
  min,
  max,
  delay = 0,
  duration = 60,
  color = colors.water,
  threshold,
  labels,
  unit = '',
}) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [delay, delay + duration], [0, 1], { ...clamp, easing: easeOut });
  const padB = labels ? 30 : 6;
  const h = height - padB;
  const x = (i: number): number => (i / (data.length - 1)) * width;
  const y = (v: number): number => h - ((v - min) / (max - min)) * h;
  const pts = data.map((v, i) => [x(i), y(v)] as const);
  const d = pts.map(([px, py], i) => `${i ? 'L' : 'M'} ${px.toFixed(1)} ${py.toFixed(1)}`).join(' ');
  const len = pts.reduce((s, [px, py], i) => {
    const prev = pts[i - 1];
    return prev ? s + Math.hypot(px - prev[0], py - prev[1]) : s;
  }, 0);
  const headIdx = Math.min(data.length - 1, Math.floor(p * (data.length - 1)));
  const head = pts[headIdx];
  const last = data[headIdx] ?? 0;

  return (
    <svg width={width} height={height} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={`area-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.28} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
        <clipPath id={`reveal-${width}-${height}-${delay}`}>
          <rect x={0} y={-20} width={width * p} height={height + 40} />
        </clipPath>
      </defs>
      {[0.25, 0.5, 0.75].map((g) => (
        <line key={g} x1={0} x2={width} y1={h * g} y2={h * g} stroke="rgba(244,241,234,0.08)" />
      ))}
      {threshold ? (
        <g opacity={p}>
          <line x1={0} x2={width} y1={y(threshold.value)} y2={y(threshold.value)} stroke={colors.alert} strokeDasharray="6 6" strokeWidth={1.5} />
          <text x={width} y={y(threshold.value) - 8} textAnchor="end" fill={colors.alert} style={{ fontFamily: fonts.mono, fontSize: 15 }}>
            {threshold.label}
          </text>
        </g>
      ) : null}
      <g clipPath={`url(#reveal-${width}-${height}-${delay})`}>
        <path d={`${d} L ${width} ${h} L 0 ${h} Z`} fill={`url(#area-${color})`} />
      </g>
      <path d={d} fill="none" stroke={color} strokeWidth={3} strokeLinejoin="round" strokeDasharray={len} strokeDashoffset={len * (1 - p)} />
      {head && p > 0 ? (
        <g>
          <circle cx={head[0]} cy={head[1]} r={6} fill={color} />
          <text x={head[0] + 10} y={head[1] - 12} fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 17 }}>
            {Math.round(last)}
            {unit}
          </text>
        </g>
      ) : null}
      {labels?.map((l, i) => (
        <text
          key={l + i}
          x={x(i)}
          y={height - 4}
          textAnchor={i === 0 ? 'start' : i === labels.length - 1 ? 'end' : 'middle'}
          fill={colors.paperDim}
          style={{ fontFamily: fonts.mono, fontSize: 15 }}
        >
          {l}
        </text>
      ))}
    </svg>
  );
};

interface BarChartProps {
  data: readonly number[];
  labels: readonly string[];
  width: number;
  height: number;
  max: number;
  delay?: number;
  color?: string;
  /** Indeks batang yang disorot. */
  highlight?: number;
}

/** Grafik batang yang tumbuh bergiliran. */
export const BarChart: React.FC<BarChartProps> = ({ data, labels, width, height, max, delay = 0, color = colors.water, highlight }) => {
  const frame = useCurrentFrame();
  const gap = 14;
  const bw = (width - gap * (data.length - 1)) / data.length;
  const h = height - 28;
  return (
    <svg width={width} height={height}>
      {data.map((v, i) => {
        const p = interpolate(frame, [delay + i * 4, delay + i * 4 + 24], [0, 1], { ...clamp, easing: easeOut });
        const bh = (v / max) * h * p;
        const x = i * (bw + gap);
        return (
          <g key={i}>
            <rect x={x} y={h - bh} width={bw} height={bh} rx={4} fill={i === highlight ? colors.rice : color} opacity={i === highlight ? 1 : 0.75} />
            <text x={x + bw / 2} y={height - 4} textAnchor="middle" fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 15 }}>
              {labels[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

interface GaugeProps {
  value: number; // 0–100
  size?: number;
  delay?: number;
  color?: string;
  label: string;
}

/** Meter melingkar sederhana (0–100%). */
export const Gauge: React.FC<GaugeProps> = ({ value, size = 150, delay = 0, color = colors.water, label }) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [delay, delay + 40], [0, 1], { ...clamp, easing: easeOut });
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r * 0.75; // busur 270°
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(135deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(244,241,234,0.12)" strokeWidth={9} strokeDasharray={`${c} ${2 * Math.PI * r}`} strokeLinecap="round" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={`${c * (value / 100) * p} ${2 * Math.PI * r}`}
        />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontFamily: fonts.sans, color: colors.paper }}>
        <div style={{ fontSize: size * 0.24, fontWeight: 700 }}>{Math.round(value * p)}%</div>
        <div style={{ fontSize: 16, color: colors.paperDim, marginTop: 2 }}>{label}</div>
      </div>
    </div>
  );
};
