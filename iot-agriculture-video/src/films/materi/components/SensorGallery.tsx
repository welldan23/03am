import { interpolate, random, useCurrentFrame } from 'remotion';
import { easeOut } from '../../../components/ui';
import { colors, fonts, panel } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export type SensorKind = 'soil' | 'air' | 'ph' | 'npk' | 'rain' | 'light' | 'level' | 'camera';

const SOIL = '#6e4b31';
const METAL = '#cfcac0';
const BODY = '#e8e4da';

/** Ilustrasi sensor (viewBox 200×200). `t` = waktu (frame) untuk animasi kecil. */
export const SensorArt: React.FC<{ kind: SensorKind; size: number; t: number }> = ({ kind, size, t }) => {
  const wave = (k: number): number => Math.sin(t / 10 + k);
  return (
    <svg width={size} height={size} viewBox="0 0 200 200">
      {kind === 'soil' && (
        <g>
          <rect x={0} y={110} width={200} height={90} fill={SOIL} rx={6} />
          {Array.from({ length: 30 }, (_, i) => (
            <circle key={i} cx={random(`s${i}`) * 200} cy={115 + random(`t${i}`) * 80} r={1.5 + random(`r${i}`) * 2} fill="rgba(0,0,0,0.25)" />
          ))}
          <rect x={70} y={30} width={60} height={50} rx={8} fill={BODY} />
          <rect x={80} y={42} width={40} height={10} rx={3} fill={colors.riceDeep} />
          <path d="M80 80 L80 170 L92 178 L92 80 M108 80 L108 178 L120 170 L120 80" fill="#2f6b4f" />
          {[0, 1, 2].map((k) => (
            <path key={k} d={`M 60 ${135 + k * 16} q 10 ${-6 + wave(k) * 3} 20 0`} stroke={colors.water} strokeWidth={3} fill="none" opacity={0.8} />
          ))}
        </g>
      )}
      {kind === 'air' && (
        <g>
          <rect x={96} y={100} width={8} height={100} fill={METAL} />
          {[0, 1, 2, 3, 4, 5].map((k) => (
            <ellipse key={k} cx={100} cy={40 + k * 12} rx={42 - k * 1.5} ry={8} fill={BODY} stroke="#b9b4a8" />
          ))}
          <rect x={92} y={108} width={16} height={22} rx={3} fill="#8f8a7f" />
          <text x={150} y={60} fill={colors.sun} style={{ fontFamily: fonts.mono, fontSize: 18 }}>
            °C
          </text>
          <text x={150} y={92} fill={colors.water} style={{ fontFamily: fonts.mono, fontSize: 18 }}>
            %RH
          </text>
        </g>
      )}
      {kind === 'ph' && (
        <g>
          <rect x={0} y={130} width={200} height={70} fill={SOIL} rx={6} />
          <rect x={52} y={20} width={96} height={64} rx={10} fill="#2b3430" stroke="#4b5650" />
          <text x={100} y={63} textAnchor="middle" fill={colors.rice} style={{ fontFamily: fonts.mono, fontSize: 28, fontWeight: 700 }}>
            6,3
          </text>
          <rect x={94} y={84} width={12} height={74} fill={METAL} />
          <ellipse cx={100} cy={164} rx={11} ry={13} fill="rgba(180,220,230,0.7)" stroke={METAL} />
          {[0, 1, 2, 3, 4, 5, 6].map((k) => (
            <rect key={k} x={20 + k * 23} y={100} width={20} height={10} rx={2} fill={['#d9534f', '#ef8a4c', '#f0c75a', '#9cc95c', '#4fb38a', '#4f8fc0', '#6c5fb5'][k]} opacity={0.85} />
          ))}
        </g>
      )}
      {kind === 'npk' && (
        <g>
          <rect x={0} y={110} width={200} height={90} fill={SOIL} rx={6} />
          <rect x={60} y={40} width={80} height={44} rx={8} fill={BODY} />
          {[78, 100, 122].map((x) => (
            <rect key={x} x={x - 3} y={84} width={6} height={86} fill={METAL} />
          ))}
          {(['N', 'P', 'K'] as const).map((l, k) => (
            <g key={l}>
              <circle cx={40 + k * 60} cy={20} r={15} fill={[colors.rice, colors.sun, colors.water][k]} opacity={0.9} />
              <text x={40 + k * 60} y={27} textAnchor="middle" fill="#111" style={{ fontFamily: fonts.sans, fontSize: 19, fontWeight: 800 }}>
                {l}
              </text>
            </g>
          ))}
        </g>
      )}
      {kind === 'rain' && (
        <g>
          <path d="M60 40 L140 40 L118 80 L82 80 Z" fill={BODY} stroke="#b9b4a8" />
          <rect x={70} y={80} width={60} height={90} rx={6} fill="#d7d3c8" />
          <rect x={92} y={170} width={16} height={30} fill={METAL} />
          <path d={`M85 ${120 + wave(0) * 6} L115 ${130 - wave(0) * 6}`} stroke="#7a7466" strokeWidth={5} strokeLinecap="round" />
          {Array.from({ length: 7 }, (_, k) => {
            const y = ((t * 3 + k * 23) % 60) - 10;
            return <line key={k} x1={70 + k * 10} x2={68 + k * 10} y1={y} y2={y + 12} stroke={colors.water} strokeWidth={3} strokeLinecap="round" />;
          })}
        </g>
      )}
      {kind === 'light' && (
        <g>
          <rect x={96} y={120} width={8} height={80} fill={METAL} />
          <rect x={70} y={100} width={60} height={24} rx={6} fill={BODY} />
          <path d="M76 100 a24 24 0 0 1 48 0 z" fill="rgba(240,240,255,0.75)" stroke="#b9b4a8" />
          {Array.from({ length: 9 }, (_, k) => {
            const ang = (Math.PI * (k + 1)) / 10;
            const r1 = 40 + wave(k) * 3;
            return (
              <line key={k} x1={100 - Math.cos(ang) * r1} y1={92 - Math.sin(ang) * r1} x2={100 - Math.cos(ang) * (r1 + 22)} y2={92 - Math.sin(ang) * (r1 + 22)} stroke={colors.sun} strokeWidth={4} strokeLinecap="round" />
            );
          })}
        </g>
      )}
      {kind === 'level' && (
        <g>
          <rect x={0} y={120} width={200} height={80} fill="rgba(143,195,209,0.45)" />
          <path d={`M0 ${120 + wave(1) * 3} Q 50 ${114 + wave(2) * 3} 100 ${120 + wave(3) * 3} T 200 ${120 + wave(4) * 3}`} stroke={colors.water} strokeWidth={3} fill="none" />
          <rect x={40} y={20} width={8} height={180} fill={METAL} />
          <rect x={44} y={24} width={76} height={30} rx={6} fill={BODY} />
          <circle cx={78} cy={54} r={9} fill="#8f8a7f" />
          <circle cx={100} cy={54} r={9} fill="#8f8a7f" />
          {[0, 1, 2].map((k) => {
            const r = ((t * 2 + k * 18) % 54) + 6;
            return <path key={k} d={`M ${89 - r * 0.8} ${60 + r} q ${r * 0.8} 12 ${r * 1.6} 0`} stroke={colors.paper} strokeOpacity={1 - r / 60} strokeWidth={2.5} fill="none" />;
          })}
        </g>
      )}
      {kind === 'camera' && (
        <g>
          <path d="M30 170 C 50 90, 120 70, 175 60 C 160 120, 110 165, 30 170 Z" fill="#6fa64a" />
          <path d="M30 170 C 80 130, 120 100, 175 60" stroke="#4d7f33" strokeWidth={3} fill="none" />
          {[
            [92, 128],
            [128, 104],
          ].map(([x, y]) => (
            <circle key={x} cx={x} cy={y} r={7} fill="#7a5a2a" opacity={0.85} />
          ))}
          <rect x={74} y={84} width={78} height={64} fill="none" stroke={colors.alert} strokeWidth={3} strokeDasharray="8 5" />
          <rect x={74} y={66} width={70} height={18} fill={colors.alert} />
          <text x={78} y={80} fill="#111" style={{ fontFamily: fonts.mono, fontSize: 13, fontWeight: 700 }}>
            BERCAK 87%
          </text>
          <rect x={10} y={10} width={64} height={44} rx={8} fill="#2b3430" stroke="#4b5650" />
          <circle cx={42} cy={32} r={13} fill="#1a1f1c" stroke={METAL} strokeWidth={3} />
        </g>
      )}
    </svg>
  );
};

export interface SensorInfo {
  kind: SensorKind;
  name: string;
  measures: string;
  why: string;
}

export const SENSORS: readonly SensorInfo[] = [
  { kind: 'soil', name: 'Kelembapan Tanah', measures: 'kadar air dalam tanah (%)', why: 'tahu kapan perlu menyiram' },
  { kind: 'air', name: 'Suhu & Kelembapan Udara', measures: 'suhu (°C) & kelembapan relatif (%RH)', why: 'waspada stres panas & penyakit jamur' },
  { kind: 'ph', name: 'pH Tanah', measures: 'tingkat keasaman tanah (skala 0–14)', why: 'memilih pupuk & kapur yang tepat' },
  { kind: 'npk', name: 'Unsur Hara NPK', measures: 'nitrogen, fosfor, kalium', why: 'dosis pupuk tidak berlebihan' },
  { kind: 'rain', name: 'Penakar Hujan', measures: 'curah hujan (mm)', why: 'irigasi ditunda saat hujan cukup' },
  { kind: 'light', name: 'Intensitas Cahaya', measures: 'sinar matahari (lux)', why: 'atur naungan & lampu tanam' },
  { kind: 'level', name: 'Ketinggian Air', measures: 'tinggi muka air (cm)', why: 'sawah, saluran, dan tambak' },
  { kind: 'camera', name: 'Kamera + AI', measures: 'gambar daun & tanaman', why: 'kenali gejala hama & penyakit' },
];

/**
 * Galeri sensor: panel detail besar di kiri (bergantian), grid 8 kartu kecil di kanan.
 * `activeAt[i]` = frame sensor ke-i mulai disorot.
 */
export const SensorGallery: React.FC<{ activeAt: readonly number[] }> = ({ activeAt }) => {
  const frame = useCurrentFrame();
  const active = activeAt.reduce((acc, f, i) => (frame >= f ? i : acc), -1);
  const appear = interpolate(frame, [0, 24], [0, 1], { ...clamp, easing: easeOut });
  const info = SENSORS[Math.max(0, active)] ?? SENSORS[0];
  const swap = active >= 0 ? interpolate(frame, [activeAt[active] ?? 0, (activeAt[active] ?? 0) + 14], [0, 1], { ...clamp, easing: easeOut }) : 0;

  return (
    <div style={{ position: 'absolute', inset: 0, fontFamily: fonts.sans, color: colors.paper, opacity: appear }}>
      {/* Panel detail */}
      <div style={{ position: 'absolute', left: 110, top: 130, width: 760, height: 640, boxSizing: 'border-box', padding: 40, ...panel }}>
        {info && active >= 0 ? (
          <div style={{ opacity: swap, transform: `translateY(${(1 - swap) * 16}px)` }}>
            <div style={{ display: 'flex', gap: 34, alignItems: 'center' }}>
              <div style={{ width: 300, height: 300, borderRadius: 20, background: 'radial-gradient(circle at 50% 40%, rgba(244,241,234,0.10), rgba(244,241,234,0.02))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <SensorArt kind={info.kind} size={270} t={frame} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: fonts.mono, fontSize: 18, letterSpacing: '0.2em', color: colors.rice }}>SENSOR 0{active + 1}</div>
                <div style={{ fontSize: 42, fontWeight: 700, marginTop: 10, lineHeight: 1.1 }}>{info.name}</div>
              </div>
            </div>
            <div style={{ marginTop: 40 }}>
              <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.16em', color: colors.paperDim }}>MENGUKUR</div>
              <div style={{ fontSize: 30, marginTop: 8 }}>{info.measures}</div>
            </div>
            <div style={{ marginTop: 28 }}>
              <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.16em', color: colors.paperDim }}>GUNANYA</div>
              <div style={{ fontSize: 30, marginTop: 8, color: colors.rice }}>{info.why}</div>
            </div>
          </div>
        ) : null}
      </div>
      {/* Grid kartu */}
      {SENSORS.map((s, i) => {
        const col = i % 2;
        const row = Math.floor(i / 2);
        const a = interpolate(frame, [6 + i * 4, 26 + i * 4], [0, 1], { ...clamp, easing: easeOut });
        const on = i === active;
        const done = i < active;
        return (
          <div
            key={s.kind}
            style={{
              position: 'absolute',
              left: 920 + col * 450,
              top: 130 + row * 162,
              width: 430,
              height: 146,
              boxSizing: 'border-box',
              padding: '14px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 18,
              opacity: a * (on ? 1 : done ? 0.75 : 0.5),
              transform: `scale(${on ? 1.03 : 1})`,
              ...panel,
              border: on ? `2px solid ${colors.rice}` : panel.border,
            }}
          >
            <SensorArt kind={s.kind} size={112} t={on ? frame : 0} />
            <div>
              <div style={{ fontFamily: fonts.mono, fontSize: 15, color: on ? colors.rice : colors.paperDim }}>0{i + 1}</div>
              <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.2 }}>{s.name}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
