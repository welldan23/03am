import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { Icon } from '../../../components/Icons';
import { easeOut, formatId } from '../../../components/ui';
import { colors, fonts, panel, status } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export interface AwdTimeline {
  pipeAt: number;
  sensorAt: number;
  dryFrom: number; // air mulai surut
  thresholdAt: number; // air mencapai −15 cm
  gateAt: number; // pintu air terbuka
  refilledAt: number; // kembali tergenang +5 cm
  savingAt: number;
}

const BOX = { x: 110, y: 150, w: 1090, h: 650 } as const;
const SURFACE = 440;
const PX = 8; // px per cm
const PIPE_X = 760;
const THRESHOLD = -15;

/**
 * Basah-Kering Berselang (Alternate Wetting & Drying / AWD) — penampang sawah:
 * pipa berlubang + sensor ketinggian air. Saat muka air turun 15 cm di bawah
 * permukaan tanah, pintu air terbuka otomatis lalu sawah tergenang lagi (+5 cm).
 */
export const AwdPaddy: React.FC<{ t: AwdTimeline }> = ({ t }) => {
  const frame = useCurrentFrame();
  const level =
    frame < t.dryFrom
      ? 5
      : frame < t.gateAt
        ? interpolate(frame, [t.dryFrom, t.thresholdAt, t.gateAt], [5, THRESHOLD, THRESHOLD - 1], { ...clamp, easing: (x) => x })
        : interpolate(frame, [t.gateAt, t.refilledAt], [THRESHOLD - 1, 5], { ...clamp, easing: easeOut });
  const day = frame < t.dryFrom ? 1 : frame < t.thresholdAt ? Math.round(interpolate(frame, [t.dryFrom, t.thresholdAt], [2, 8], clamp)) : frame < t.gateAt ? 8 : 9;
  const gateOpen = frame >= t.gateAt && frame < t.refilledAt + 20;
  const pipeIn = interpolate(frame, [t.pipeAt, t.pipeAt + 30], [0, 1], { ...clamp, easing: easeOut });
  const sensorIn = interpolate(frame, [t.sensorAt, t.sensorAt + 20], [0, 1], { ...clamp, easing: easeOut });
  const saving = interpolate(frame, [t.savingAt, t.savingAt + 24], [0, 1], { ...clamp, easing: easeOut });
  const appear = interpolate(frame, [0, 20], [0, 1], clamp);
  const waterY = SURFACE - level * PX;
  const reached = frame >= t.thresholdAt;

  const state =
    frame < t.dryFrom
      ? ['TERGENANG', colors.water]
      : frame < t.thresholdAt
        ? ['MENGERING · BELUM PERLU AIR', colors.paper]
        : frame < t.gateAt
          ? ['AMBANG −15 cm TERCAPAI', status.poor]
          : frame < t.refilledAt
            ? ['PINTU AIR TERBUKA', colors.water]
            : ['TERGENANG KEMBALI · PINTU TERTUTUP', status.good];

  // riwayat muka air untuk grafik mini
  const hist = Array.from({ length: 60 }, (_, i) => {
    const f = Math.min(frame, t.dryFrom - 40 + (i / 59) * (t.refilledAt + 60 - (t.dryFrom - 40)));
    const lv =
      f < t.dryFrom ? 5 : f < t.gateAt ? interpolate(f, [t.dryFrom, t.thresholdAt, t.gateAt], [5, THRESHOLD, THRESHOLD - 1], clamp) : interpolate(f, [t.gateAt, t.refilledAt], [THRESHOLD - 1, 5], clamp);
    return { x: (i / 59) * 440, y: 110 - (lv + 20) * 4.4, show: f <= frame };
  });

  return (
    <AbsoluteFill style={{ opacity: appear }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <clipPath id="awdbox">
            <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={14} />
          </clipPath>
          <linearGradient id="awdsoil" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5b3f2b" />
            <stop offset="100%" stopColor="#7d5a3c" />
          </linearGradient>
        </defs>
        <g clipPath="url(#awdbox)">
          <rect x={BOX.x} y={BOX.y} width={BOX.w} height={SURFACE - BOX.y} fill="rgba(150,180,190,0.10)" />
          <rect x={BOX.x} y={SURFACE} width={BOX.w} height={BOX.y + BOX.h - SURFACE} fill="url(#awdsoil)" />
          {Array.from({ length: 160 }, (_, i) => (
            <circle key={i} cx={BOX.x + random(`ax${i}`) * BOX.w} cy={SURFACE + 8 + random(`ay${i}`) * 350} r={1 + random(`ar${i}`) * 2.4} fill="rgba(0,0,0,0.22)" />
          ))}
          {/* zona jenuh air di dalam tanah */}
          <rect x={BOX.x} y={Math.max(SURFACE, waterY)} width={BOX.w} height={BOX.y + BOX.h - Math.max(SURFACE, waterY)} fill="rgba(60,100,130,0.38)" />
          {/* genangan di atas tanah */}
          {level > 0 ? <rect x={BOX.x + 120} y={waterY} width={BOX.w - 120} height={SURFACE - waterY} fill="rgba(143,195,209,0.55)" /> : null}
          <line x1={BOX.x} x2={BOX.x + BOX.w} y1={waterY} y2={waterY} stroke={colors.water} strokeWidth={2.5} strokeDasharray={level > 0 ? '0' : '8 6'} />
          {/* padi */}
          {[330, 450, 570, 900, 1020, 1130].map((x, k) => (
            <g key={x}>
              {Array.from({ length: 7 }, (_, j) => {
                const a = (j - 3) * 0.15 + Math.sin(frame / 28 + k) * 0.03;
                return <line key={j} x1={x} y1={SURFACE} x2={x + Math.sin(a) * 120} y2={SURFACE - Math.cos(a) * 120} stroke="#8fbf54" strokeWidth={3} strokeLinecap="round" />;
              })}
              {Array.from({ length: 5 }, (_, j) => (
                <path key={j} d={`M ${x} ${SURFACE} q ${(j - 2) * 10} 60 ${(j - 2) * 18} ${100 + random(`rr${k}${j}`) * 60}`} stroke="rgba(230,215,180,0.5)" strokeWidth={1.5} fill="none" />
              ))}
            </g>
          ))}
          {/* saluran & pintu air */}
          <rect x={BOX.x} y={SURFACE - 70} width={120} height={150} fill="rgba(143,195,209,0.6)" />
          <rect x={BOX.x + 112} y={SURFACE - 90 - (gateOpen ? 60 : 0)} width={14} height={110} fill="#c9c3b5" />
          {gateOpen
            ? Array.from({ length: 10 }, (_, i) => {
                const u = ((frame * 4 + i * 37) % 260) / 260;
                return <circle key={i} cx={BOX.x + 130 + u * 300} cy={SURFACE - 6 - Math.sin(u * 3) * 4} r={4} fill={colors.water} opacity={1 - u} />;
              })
            : null}
          {/* pipa berlubang */}
          <g transform={`translate(0 ${(1 - pipeIn) * -500})`} opacity={pipeIn}>
            <rect x={PIPE_X - 23} y={SURFACE - 70} width={46} height={70 + 25 * PX} fill="rgba(235,232,224,0.9)" stroke="#9e988b" />
            <rect x={PIPE_X - 17} y={Math.max(SURFACE - 70, waterY)} width={34} height={SURFACE + 25 * PX - Math.max(SURFACE - 70, waterY)} fill="rgba(143,195,209,0.75)" />
            {Array.from({ length: 8 }, (_, i) => (
              <g key={i}>
                <circle cx={PIPE_X - 14} cy={SURFACE + 18 + i * 22} r={4} fill="#5b3f2b" />
                <circle cx={PIPE_X + 14} cy={SURFACE + 29 + i * 22} r={4} fill="#5b3f2b" />
              </g>
            ))}
          </g>
          {/* sensor di atas pipa */}
          <g opacity={sensorIn}>
            <rect x={PIPE_X - 38} y={SURFACE - 118} width={76} height={50} rx={8} fill="#2b3430" stroke="#4b5650" />
            <line x1={PIPE_X + 24} x2={PIPE_X + 24} y1={SURFACE - 118} y2={SURFACE - 160} stroke="#9e988b" strokeWidth={3} />
            {[0, 1, 2].map((k) => {
              const r = ((frame + k * 14) % 42) / 42;
              return <path key={k} d={`M ${PIPE_X + 24 - 10 - r * 16} ${SURFACE - 165 - r * 12} q ${10 + r * 16} ${-10 - r * 8} ${20 + r * 32} 0`} stroke={colors.rice} strokeOpacity={1 - r} strokeWidth={2} fill="none" />;
            })}
            <text x={PIPE_X} y={SURFACE - 86} textAnchor="middle" fill={colors.rice} style={{ fontFamily: fonts.mono, fontSize: 16 }}>
              {level >= 0 ? '+' : ''}
              {formatId(level, 0)} cm
            </text>
          </g>
          {/* ambang */}
          <line x1={BOX.x + 120} x2={BOX.x + BOX.w} y1={SURFACE - THRESHOLD * PX} y2={SURFACE - THRESHOLD * PX} stroke={status.poor} strokeWidth={2} strokeDasharray="10 8" opacity={sensorIn} />
          <text x={BOX.x + BOX.w - 14} y={SURFACE - THRESHOLD * PX - 10} textAnchor="end" fill={status.poor} style={{ fontFamily: fonts.mono, fontSize: 17 }} opacity={sensorIn}>
            AMBANG −15 cm
          </text>
        </g>
        <rect x={BOX.x} y={BOX.y} width={BOX.w} height={BOX.h} rx={14} fill="none" stroke="rgba(244,241,234,0.2)" />
        {/* penggaris */}
        {[5, 0, -5, -10, -15, -20, -25].map((cm) => (
          <g key={cm}>
            <line x1={BOX.x + 130} x2={BOX.x + 146} y1={SURFACE - cm * PX} y2={SURFACE - cm * PX} stroke={colors.paper} strokeOpacity={0.6} />
            <text x={BOX.x + 152} y={SURFACE - cm * PX + 6} fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 15 }}>
              {cm > 0 ? `+${cm}` : cm}
            </text>
          </g>
        ))}
        <text x={BOX.x + 20} y={BOX.y + 40} fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 22 }}>
          HARI {day}
        </text>
        <text x={BOX.x + 14} y={SURFACE - 82} fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 14 }}>
          SALURAN
        </text>
      </svg>

      {/* Panel status */}
      <div style={{ position: 'absolute', left: 1250, top: 150, width: 540, boxSizing: 'border-box', padding: '26px 30px', fontFamily: fonts.sans, color: colors.paper, ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>MUKA AIR (SENSOR PIPA)</div>
        <div style={{ fontSize: 64, fontWeight: 700, marginTop: 6, color: reached && frame < t.refilledAt ? status.poor : colors.water, fontVariantNumeric: 'tabular-nums' }}>
          {level >= 0 ? '+' : ''}
          {formatId(level, 1)} <span style={{ fontSize: 28, color: colors.paperDim }}>cm</span>
        </div>
        <svg width={440} height={130} style={{ marginTop: 10, overflow: 'visible' }}>
          <line x1={0} x2={440} y1={110 - (THRESHOLD + 20) * 4.4} y2={110 - (THRESHOLD + 20) * 4.4} stroke={status.poor} strokeDasharray="6 6" />
          <line x1={0} x2={440} y1={110 - 20 * 4.4} y2={110 - 20 * 4.4} stroke="rgba(244,241,234,0.25)" />
          <path d={hist.filter((h) => h.show).map((h, i) => `${i ? 'L' : 'M'} ${h.x} ${h.y}`).join(' ')} stroke={colors.water} strokeWidth={3} fill="none" />
        </svg>
        <div style={{ fontSize: 24, fontWeight: 700, marginTop: 14, color: state[1], minHeight: 64 }}>{state[0]}</div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 10, fontSize: 20, color: colors.paperDim }}>
          <Icon name="valve" size={30} color={gateOpen ? colors.water : colors.paperDim} /> Pintu air: {gateOpen ? 'TERBUKA' : 'TERTUTUP'}
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, marginTop: 16, letterSpacing: '0.1em' }}>ANIMASI ILUSTRASI · SIKLUS DIPERCEPAT</div>
      </div>
      {saving > 0 ? (
        <div
          style={{
            position: 'absolute',
            left: 1250,
            top: 640,
            width: 540,
            boxSizing: 'border-box',
            padding: '22px 30px',
            opacity: saving,
            transform: `translateY(${(1 - saving) * 16}px)`,
            fontFamily: fonts.sans,
            color: colors.paper,
            ...panel,
            border: `1.5px solid ${status.good}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{ fontSize: 22, color: colors.paperDim }}>Hemat air hingga</span>
            <span style={{ fontSize: 56, fontWeight: 800, color: status.good }}>±30%</span>
          </div>
          <div style={{ fontFamily: fonts.mono, fontSize: 15, color: colors.paperDim, marginTop: 6 }}>Sumber: IRRI (Safe AWD)</div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
