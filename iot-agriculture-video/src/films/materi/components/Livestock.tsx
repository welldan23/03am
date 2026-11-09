import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { Icon } from '../../../components/Icons';
import { easeOut, formatId } from '../../../components/ui';
import { colors, fonts, panel, status } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const fade = (frame: number, at: number, len = 20): number => interpolate(frame, [at, at + len], [0, 1], { ...clamp, easing: easeOut });

/** Panel data kalung sensor sapi: suhu tubuh, aktivitas 24 jam (turun), lokasi & geofence. */
export const CattleCollarPanel: React.FC<{ alertAt: number }> = ({ alertAt }) => {
  const frame = useCurrentFrame();
  const a = fade(frame, 0, 24);
  // aktivitas per jam: normal, lalu turun di 6 jam terakhir
  const bars = Array.from({ length: 24 }, (_, h) => {
    const base = 60 + Math.sin(h / 3) * 18 + random(`act${h}`) * 14;
    return h >= 18 ? base * 0.35 : base;
  });
  const reveal = interpolate(frame, [20, 100], [0, 24], clamp);
  const alert = fade(frame, alertAt, 18);
  const blink = Math.floor(frame / 12) % 2 === 0;
  return (
    <div style={{ position: 'absolute', left: 1250, top: 120, width: 560, fontFamily: fonts.sans, color: colors.paper, opacity: a }}>
      <div style={{ padding: '22px 26px', ...panel }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <div style={{ fontSize: 28, fontWeight: 700 }}>Sapi #12</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 15, color: colors.paperDim }}>KALUNG SENSOR · AKTIF</div>
        </div>
        <div style={{ display: 'flex', gap: 30, marginTop: 16 }}>
          <div>
            <div style={{ fontSize: 18, color: colors.paperDim }}>Suhu tubuh</div>
            <div style={{ fontSize: 40, fontWeight: 700 }}>
              38,9 <span style={{ fontSize: 20, color: colors.paperDim }}>°C</span>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 18, color: colors.paperDim }}>Baterai</div>
            <div style={{ fontSize: 40, fontWeight: 700 }}>
              86 <span style={{ fontSize: 20, color: colors.paperDim }}>%</span>
            </div>
          </div>
        </div>
        <div style={{ fontSize: 18, color: colors.paperDim, marginTop: 18 }}>Aktivitas (gerak per jam, 24 jam terakhir)</div>
        <svg width={508} height={110} style={{ marginTop: 8 }}>
          {bars.map((v, h) => (
            <rect key={h} x={h * 21} y={100 - v} width={15} height={h < reveal ? v : 0} rx={3} fill={h >= 18 ? status.poor : colors.rice} opacity={0.85} />
          ))}
        </svg>
        {/* peta mini dengan pagar virtual */}
        <div style={{ fontSize: 18, color: colors.paperDim, marginTop: 14 }}>Lokasi (GPS) & pagar virtual</div>
        <svg width={508} height={130} style={{ marginTop: 8 }}>
          <rect width={508} height={130} rx={10} fill="rgba(95,127,58,0.25)" />
          <path d="M40 20 L460 30 L470 110 L60 115 Z" fill="none" stroke={colors.sun} strokeDasharray="8 6" strokeWidth={2} />
          {Array.from({ length: 9 }, (_, i) => (
            <circle key={i} cx={90 + random(`cx${i}`) * 330 + Math.sin(frame / 40 + i) * 6} cy={45 + random(`cy${i}`) * 55} r={6} fill={colors.paper} opacity={0.75} />
          ))}
          <circle cx={360} cy={80} r={9} fill={status.poor} />
          <circle cx={360} cy={80} r={18 + (blink ? 6 : 0)} fill="none" stroke={status.poor} />
        </svg>
      </div>
      {alert > 0 ? (
        <div style={{ marginTop: 14, padding: '18px 22px', display: 'flex', gap: 16, alignItems: 'center', opacity: alert, transform: `translateY(${(1 - alert) * 12}px)`, ...panel, border: `1.5px solid ${status.poor}` }}>
          <Icon name="alert" size={40} color={status.poor} />
          <div>
            <div style={{ fontSize: 23, fontWeight: 700, color: status.poor }}>Aktivitas sapi #12 turun drastis</div>
            <div style={{ fontSize: 19, color: colors.paperDim, marginTop: 4 }}>Periksa kesehatannya hari ini</div>
          </div>
        </div>
      ) : null}
      <div style={{ fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, marginTop: 10, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
    </div>
  );
};

export interface PondTimeline {
  sensorAt: number;
  aeratorAt: number;
  feederAt: number;
}

const LIMIT = 4; // mg/L, batas aman ilustrasi untuk udang

/**
 * Oksigen terlarut (mg/L) selama 24 jam mulai pukul 12.00 (h = jam sejak 12.00).
 * Puncak sore (fotosintesis), terendah menjelang subuh (respirasi malam).
 */
const doNatural = (h: number): number => 5.2 + 2.4 * Math.sin((h / 24) * Math.PI * 2 + Math.PI / 2 - Math.PI / 2) - (h > 6 && h < 20 ? (h - 6) * 0.06 : 0);
/** Jam (sejak 12.00) saat oksigen alami turun melewati batas → kincir menyala. */
const ON_H = 13.2;

/**
 * Tambak udang (penampang): sensor DO terapung, kincir air, dan pemberi pakan otomatis,
 * plus grafik oksigen 24 jam. Kincir menyala saat DO < 4 mg/L.
 */
export const PondMonitor: React.FC<{ t: PondTimeline }> = ({ t }) => {
  const frame = useCurrentFrame();
  const a = fade(frame, 0, 24);
  // Jam pada grafik dikalibrasi agar garis melewati batas tepat di frame `aeratorAt`.
  const hours = interpolate(frame, [10, t.aeratorAt, t.aeratorAt + 150], [0, ON_H, 24], clamp);
  const aerator = hours >= ON_H;
  const feeder = frame >= t.feederAt && frame < t.feederAt + 90;
  const sensorHi = fade(frame, t.sensorAt, 16);
  const doAt = (h: number): number => {
    const natural = doNatural(h);
    // setelah kincir menyala, oksigen ditahan naik kembali di atas batas
    return h > ON_H ? Math.max(natural, LIMIT - 0.2 + Math.min(1, (h - ON_H) / 1.2) * 1.0) : natural;
  };
  const curDo = doAt(hours);
  const W = 520;
  const H = 200;
  const px = (h: number): number => (h / 24) * W;
  const py = (v: number): number => H - ((v - 2) / 7) * H;
  const path = Array.from({ length: 97 }, (_, i) => (i / 96) * hours)
    .map((h, i) => `${i ? 'L' : 'M'} ${px(h).toFixed(1)} ${py(doAt(h)).toFixed(1)}`)
    .join(' ');
  const clock = (12 + Math.floor(hours)) % 24;
  const night = clock >= 18 || clock < 5;
  const period = night ? 'MALAM' : clock < 10 ? 'PAGI' : clock < 15 ? 'SIANG' : 'SORE';
  const WATER_Y = 470;
  const paddle = aerator ? frame * 14 : 0;

  return (
    <AbsoluteFill style={{ opacity: a, fontFamily: fonts.sans, color: colors.paper }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <defs>
          <linearGradient id="pond" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f7f86" />
            <stop offset="100%" stopColor="#24434a" />
          </linearGradient>
        </defs>
        {/* langit siang/malam */}
        <rect x={110} y={150} width={1080} height={WATER_Y - 150} rx={14} fill={night ? 'rgba(20,30,50,0.55)' : 'rgba(150,180,190,0.12)'} />
        {/* tanggul & kolam */}
        <path d={`M110 ${WATER_Y - 30} L230 ${WATER_Y - 30} L330 790 L970 790 L1070 ${WATER_Y - 30} L1190 ${WATER_Y - 30} L1190 800 L110 800 Z`} fill="#6e4b31" />
        <path d={`M230 ${WATER_Y} L330 790 L970 790 L1070 ${WATER_Y} Z`} fill="url(#pond)" />
        <path d={`M230 ${WATER_Y} ${Array.from({ length: 21 }, (_, i) => `L ${230 + i * 42} ${WATER_Y + Math.sin(frame / 8 + i) * (aerator ? 5 : 2)}`).join(' ')}`} stroke="rgba(220,240,245,0.6)" strokeWidth={2} fill="none" />
        {/* gelembung oksigen dari kincir */}
        {aerator
          ? Array.from({ length: 26 }, (_, i) => {
              const u = ((frame * 2 + i * 13) % 120) / 120;
              return <circle key={i} cx={760 + (random(`bx${i}`) - 0.5) * 300} cy={WATER_Y + 20 + u * 260} r={2 + random(`br${i}`) * 3} fill="rgba(230,250,255,0.7)" opacity={1 - u} />;
            })
          : null}
        {/* udang */}
        {Array.from({ length: 7 }, (_, i) => {
          const x = 380 + ((frame * (0.6 + random(`sv${i}`)) + i * 90) % 560);
          const y = 620 + random(`sy${i}`) * 140 + Math.sin(frame / 20 + i) * 6;
          return <path key={i} d={`M ${x} ${y} q 12 -10 26 -2 q -6 4 -2 10 q -14 2 -24 -8`} fill="#e9b9a0" opacity={0.8} />;
        })}
        {/* kincir air */}
        <g transform={`translate(760 ${WATER_Y - 6})`}>
          <rect x={-70} y={-40} width={140} height={14} rx={4} fill="#2b3430" />
          <circle r={34} fill="none" stroke="#e7c45a" strokeWidth={4} />
          <g transform={`rotate(${paddle})`}>
            {[0, 60, 120, 180, 240, 300].map((r) => (
              <rect key={r} x={-5} y={-36} width={10} height={20} fill="#e7c45a" transform={`rotate(${r})`} />
            ))}
          </g>
          {aerator
            ? Array.from({ length: 8 }, (_, i) => {
                const u = ((frame * 3 + i * 11) % 40) / 40;
                return <circle key={i} cx={-20 + i * 6 + u * 30} cy={-8 - Math.sin(u * Math.PI) * 30} r={3} fill="rgba(230,250,255,0.9)" opacity={1 - u} />;
              })
            : null}
        </g>
        {/* sensor DO terapung */}
        <g transform={`translate(470 ${WATER_Y - 4})`}>
          <ellipse rx={30} ry={10} fill="#e8e4da" />
          <line x1={0} x2={0} y1={0} y2={120} stroke="#9e988b" strokeWidth={3} />
          <rect x={-8} y={118} width={16} height={34} rx={4} fill="#cfcac0" />
          <line x1={0} x2={0} y1={-10} y2={-50} stroke="#9e988b" strokeWidth={2} />
          <circle r={34 + sensorHi * 10} fill="none" stroke={colors.rice} opacity={sensorHi * (0.5 + 0.5 * Math.sin(frame / 6))} />
        </g>
        {/* pemberi pakan otomatis */}
        <g transform={`translate(1080 ${WATER_Y - 120})`}>
          <path d="M-30 0 L30 0 L18 50 L-18 50 Z" fill="#cfcac0" />
          <rect x={-6} y={50} width={12} height={40} fill="#9e988b" />
          <rect x={-40} y={86} width={30} height={10} fill="#9e988b" />
          {feeder
            ? Array.from({ length: 12 }, (_, i) => {
                const u = ((frame * 3 + i * 9) % 40) / 40;
                return <circle key={i} cx={-40 - u * 120} cy={92 + u * u * 60} r={3} fill="#b07b3a" />;
              })
            : null}
        </g>
        {(
          [
            [470, WATER_Y - 70, 'SENSOR OKSIGEN (DO)'],
            [760, WATER_Y - 66, 'KINCIR AIR'],
            [1080, WATER_Y - 136, 'PEMBERI PAKAN'],
          ] as const
        ).map(([x, y, l]) => (
          <text key={l} x={x} y={y} textAnchor="middle" fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 15, letterSpacing: '0.08em' }}>
            {l}
          </text>
        ))}
        <text x={140} y={190} fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 22 }}>
          PUKUL {String(clock).padStart(2, '0')}.00 · {period}
        </text>
      </svg>

      {/* Panel oksigen */}
      <div style={{ position: 'absolute', left: 1250, top: 150, width: 580, boxSizing: 'border-box', padding: '24px 28px', ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>OKSIGEN TERLARUT · 24 JAM</div>
        <div style={{ fontSize: 60, fontWeight: 700, color: curDo < LIMIT ? status.poor : colors.water, fontVariantNumeric: 'tabular-nums' }}>
          {formatId(curDo, 1)} <span style={{ fontSize: 26, color: colors.paperDim }}>mg/L</span>
        </div>
        <svg width={W} height={H + 30} style={{ overflow: 'visible', marginTop: 6 }}>
          <rect x={px(6)} y={0} width={px(12)} height={H} fill="rgba(20,30,50,0.35)" />
          <line x1={0} x2={W} y1={py(LIMIT)} y2={py(LIMIT)} stroke={status.poor} strokeDasharray="6 6" />
          <text x={W} y={py(LIMIT) - 8} textAnchor="end" fill={status.poor} style={{ fontFamily: fonts.mono, fontSize: 14 }}>
            BATAS {LIMIT} mg/L
          </text>
          <path d={path} stroke={colors.water} strokeWidth={3} fill="none" />
          {['12', '18', '00', '06', '12'].map((l, i) => (
            <text key={i} x={(i / 4) * W} y={H + 24} textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'} fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 14 }}>
              {l}
            </text>
          ))}
        </svg>
        <div style={{ borderTop: '1px solid rgba(244,241,234,0.12)', marginTop: 12, paddingTop: 12 }}>
          {(
            [
              ['Kincir air', aerator],
              ['Pemberi pakan', feeder],
            ] as const
          ).map(([l, on]) => (
            <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 21, marginTop: 6 }}>
              <span style={{ color: colors.paperDim }}>{l}</span>
              <span style={{ fontWeight: 700, color: on ? status.good : colors.paperFaint }}>{on ? 'MENYALA' : 'MATI'}</span>
            </div>
          ))}
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, marginTop: 12, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
      </div>
    </AbsoluteFill>
  );
};
