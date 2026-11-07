import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { colors, fonts, panel, status } from '../styles/theme';
import { easeOut, formatId } from './ui';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

// Geometri penampang (px layar)
const BOX = { x: 160, y: 150, w: 1000, h: 640 } as const;
const SURFACE = 290; // y permukaan tanah
const PX_PER_CM = 7.4;
const PROBE_X = 560;
const DEPTHS = [
  { cm: 10, start: 24, end: 52 },
  { cm: 30, start: 27, end: 47 },
  { cm: 60, start: 31, end: 40 },
] as const;
const ROOT_DEPTH_CM = 30; // zona akar padi yang dipantau

const yAt = (cm: number): number => SURFACE + cm * PX_PER_CM;

interface Props {
  /** Frame mulai air masuk (irigasi/hujan). */
  wetAt?: number;
}

/**
 * Penampang tanah sawah: lapisan tanah, akar padi, probe sensor dengan tiga
 * titik ukur, dan "front basah" yang turun perlahan setelah air masuk.
 * Nilai kelembapan adalah ilustrasi untuk menjelaskan cara kerja sensor.
 */
export const SoilCrossSection: React.FC<Props> = ({ wetAt = 70 }) => {
  const frame = useCurrentFrame();
  const probeIn = interpolate(frame, [8, 46], [0, 1], { ...clamp, easing: easeOut });
  const front = interpolate(frame, [wetAt, wetAt + 280], [0, 68], { ...clamp, easing: (t) => 1 - (1 - t) ** 1.6 });
  const rain = interpolate(frame, [wetAt - 20, wetAt, wetAt + 110, wetAt + 150], [0, 1, 1, 0], clamp);
  const frontY = yAt(front);
  const rootReached = front >= ROOT_DEPTH_CM + 4;
  const rootMsgP = interpolate(frame, [wetAt + 170, wetAt + 190], [0, 1], clamp);

  const readings = DEPTHS.map((d) => {
    const p = interpolate(front - d.cm, [-2, 10], [0, 1], { ...clamp, easing: easeOut });
    return { ...d, value: d.start + (d.end - d.start) * p, wet: p };
  });

  return (
    <AbsoluteFill>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <linearGradient id="soil" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5a3e2b" />
            <stop offset="35%" stopColor="#6e4b31" />
            <stop offset="70%" stopColor="#7d5a3c" />
            <stop offset="100%" stopColor="#8b6a4a" />
          </linearGradient>
          <linearGradient id="wet" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#2c2a2a" stopOpacity={0.7} />
            <stop offset="85%" stopColor="#24303a" stopOpacity={0.55} />
            <stop offset="100%" stopColor="#24303a" stopOpacity={0} />
          </linearGradient>
          <clipPath id="box">
            <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={14} />
          </clipPath>
        </defs>
        <g clipPath="url(#box)">
          {/* langit tipis + air genangan */}
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={SURFACE - BOX.y} fill="rgba(140,170,180,0.12)" />
          <rect x={BOX.x} y={SURFACE - 10} width={BOX.w} height={10} fill={colors.water} opacity={0.25 + rain * 0.35} />
          {/* lapisan tanah */}
          <rect x={BOX.x} y={SURFACE} width={BOX.w} height={BOX.y + BOX.h - SURFACE} fill="url(#soil)" />
          {[yAt(18), yAt(45)].map((y) => (
            <path key={y} d={`M ${BOX.x} ${y} Q ${BOX.x + 300} ${y - 8} ${BOX.x + 600} ${y + 4} T ${BOX.x + BOX.w} ${y}`} stroke="rgba(0,0,0,0.25)" strokeWidth={2} fill="none" />
          ))}
          {/* butiran tanah */}
          {Array.from({ length: 220 }, (_, i) => (
            <circle
              key={i}
              cx={BOX.x + random(`gx${i}`) * BOX.w}
              cy={SURFACE + 6 + random(`gy${i}`) * (BOX.y + BOX.h - SURFACE)}
              r={0.8 + random(`gr${i}`) * 2.6}
              fill={random(`gc${i}`) > 0.5 ? 'rgba(255,230,200,0.10)' : 'rgba(0,0,0,0.22)'}
            />
          ))}
          {/* front basah */}
          <rect x={BOX.x} y={SURFACE} width={BOX.w} height={Math.max(0, frontY - SURFACE + 30)} fill="url(#wet)" />
          {front > 1 ? (
            <path
              d={`M ${BOX.x} ${frontY} ${Array.from({ length: 21 }, (_, i) => `L ${BOX.x + (i * BOX.w) / 20} ${frontY + Math.sin(i * 1.3 + frame / 20) * 6}`).join(' ')}`}
              stroke={colors.water}
              strokeOpacity={0.55}
              strokeWidth={2}
              strokeDasharray="4 6"
              fill="none"
            />
          ) : null}
          {/* tanaman padi + akar */}
          {[300, 430, 690, 820, 950, 1080].map((x, k) => (
            <g key={x}>
              {Array.from({ length: 7 }, (_, j) => {
                const a = (j - 3) * 0.16 + Math.sin(frame / 30 + k) * 0.03;
                return <line key={j} x1={x} y1={SURFACE} x2={x + Math.sin(a) * 130} y2={SURFACE - Math.cos(a) * 130} stroke="#8fbf54" strokeWidth={3} strokeLinecap="round" />;
              })}
              {Array.from({ length: 6 }, (_, j) => {
                const dx = (j - 2.5) * 16;
                const depth = yAt(ROOT_DEPTH_CM * (0.6 + random(`rd${k}${j}`) * 0.4));
                return <path key={j} d={`M ${x} ${SURFACE} C ${x + dx * 0.5} ${SURFACE + 40}, ${x + dx * 1.4} ${depth - 60}, ${x + dx * 1.2} ${depth}`} stroke="rgba(230,215,180,0.55)" strokeWidth={1.6} fill="none" />;
              })}
            </g>
          ))}
          {/* tetes air masuk */}
          {rain > 0
            ? Array.from({ length: 34 }, (_, i) => {
                const x = BOX.x + random(`rx${i}`) * BOX.w;
                const t = ((frame + random(`rt${i}`) * 30) % 30) / 30;
                return <line key={i} x1={x} x2={x - 3} y1={BOX.y + t * (SURFACE - BOX.y)} y2={BOX.y + t * (SURFACE - BOX.y) + 18} stroke={colors.water} strokeOpacity={0.6 * rain} strokeWidth={2} />;
              })
            : null}
          {/* zona akar */}
          <line x1={BOX.x} x2={BOX.x + BOX.w} y1={yAt(ROOT_DEPTH_CM)} y2={yAt(ROOT_DEPTH_CM)} stroke={colors.rice} strokeOpacity={0.5} strokeDasharray="10 8" />
          <text x={BOX.x + BOX.w - 16} y={yAt(ROOT_DEPTH_CM) - 10} textAnchor="end" fill={colors.rice} style={{ fontFamily: fonts.mono, fontSize: 16 }}>
            ZONA AKAR
          </text>
          {/* probe sensor */}
          <g transform={`translate(0 ${(1 - probeIn) * -480})`}>
            <rect x={PROBE_X - 34} y={SURFACE - 120} width={68} height={70} rx={8} fill="#d9d6cc" />
            <rect x={PROBE_X - 22} y={SURFACE - 104} width={44} height={10} rx={3} fill={colors.riceDeep} />
            <rect x={PROBE_X - 9} y={SURFACE - 50} width={18} height={yAt(66) - SURFACE + 50} rx={9} fill="#cfcac0" />
            {readings.map((r) => (
              <g key={r.cm}>
                <rect x={PROBE_X - 12} y={yAt(r.cm) - 9} width={24} height={18} rx={4} fill={r.wet > 0.5 ? colors.water : '#7f8a8f'} />
                <circle cx={PROBE_X} cy={yAt(r.cm)} r={14 + r.wet * 24} fill="none" stroke={colors.water} strokeOpacity={0.5 * (1 - r.wet)} />
              </g>
            ))}
          </g>
        </g>
        <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={14} fill="none" stroke="rgba(244,241,234,0.2)" />
        {/* label kedalaman */}
        {readings.map((r) => (
          <g key={r.cm} opacity={probeIn}>
            <line x1={PROBE_X + 16} x2={PROBE_X + 70} y1={yAt(r.cm)} y2={yAt(r.cm)} stroke={colors.paper} strokeOpacity={0.6} />
            <text x={PROBE_X + 78} y={yAt(r.cm) + 7} fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 20 }}>
              {r.cm} cm · {formatId(r.value, 0)}%
            </text>
          </g>
        ))}
      </svg>

      {/* Panel pembacaan */}
      <div style={{ position: 'absolute', left: 1230, top: 150, width: 530, padding: '26px 30px', boxSizing: 'border-box', fontFamily: fonts.sans, color: colors.paper, opacity: probeIn, ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>KELEMBAPAN TANAH</div>
        {readings.map((r) => {
          const c = r.value < 30 ? status.poor : r.value < 40 ? status.fair : status.good;
          return (
            <div key={r.cm} style={{ marginTop: 26 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 22 }}>
                <span style={{ color: colors.paperDim }}>Kedalaman {r.cm} cm</span>
                <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{formatId(r.value, 0)}%</span>
              </div>
              <div style={{ height: 10, borderRadius: 5, background: 'rgba(244,241,234,0.1)', marginTop: 10 }}>
                <div style={{ width: `${r.value * 1.5}%`, height: '100%', borderRadius: 5, background: c }} />
              </div>
            </div>
          );
        })}
        <div style={{ marginTop: 30, paddingTop: 22, borderTop: '1px solid rgba(244,241,234,0.12)', fontSize: 22, lineHeight: 1.4 }}>
          {rootReached ? (
            <span style={{ color: status.good, opacity: rootMsgP }}>✓ Air sudah mencapai zona akar</span>
          ) : (
            <span style={{ color: colors.paperDim }}>Menunggu air mencapai zona akar…</span>
          )}
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 15, color: colors.paperFaint, marginTop: 18, letterSpacing: '0.1em' }}>DATA ILUSTRASI · DIPERBARUI TIAP 5 MENIT</div>
      </div>
    </AbsoluteFill>
  );
};
