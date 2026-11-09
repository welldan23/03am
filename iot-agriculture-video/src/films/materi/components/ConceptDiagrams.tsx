import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { Icon, type IconName } from '../../../components/Icons';
import { easeOut } from '../../../components/ui';
import { colors, fonts, panel } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
const p = (frame: number, at: number, len = 22): number => interpolate(frame, [at, at + len], [0, 1], { ...clamp, easing: easeOut });

// ── 4 komponen IoT dengan analogi tubuh ──────────────────────────────────

interface Part {
  icon: IconName;
  analogyIcon: IconName;
  title: string;
  analogy: string;
  desc: string;
}
const PARTS: readonly Part[] = [
  { icon: 'sensor', analogyIcon: 'eye', title: 'Sensor', analogy: 'indra', desc: 'merasakan tanah,\nair, dan cuaca' },
  { icon: 'gateway', analogyIcon: 'nerve', title: 'Konektivitas', analogy: 'saraf', desc: 'mengirim data\nlewat jaringan' },
  { icon: 'cloud', analogyIcon: 'brain', title: 'Platform Cloud', analogy: 'otak', desc: 'menyimpan &\nmengolah data' },
  { icon: 'valve', analogyIcon: 'hand', title: 'Aplikasi & Aktuator', analogy: 'tangan', desc: 'menampilkan info\n& bertindak' },
];
const CARD_X = [150, 580, 1010, 1440] as const;
const CARD_W = 330;
const CARD_Y = 230;
const CARD_H = 420;

/** Empat kartu komponen + panah alur + siklus kembali. `at` = frame munculnya tiap kartu. */
export const FourComponents: React.FC<{ at: readonly number[]; loopAt: number }> = ({ at, loopAt }) => {
  const frame = useCurrentFrame();
  const loop = p(frame, loopAt, 40);
  const loopLen = 1500;
  return (
    <AbsoluteFill>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {CARD_X.slice(0, -1).map((x, i) => {
          const a = p(frame, (at[i + 1] ?? 0) - 6, 18);
          const x1 = x + CARD_W + 10;
          const x2 = (CARD_X[i + 1] ?? 0) - 10;
          const y = CARD_Y + 120;
          return (
            <g key={x} opacity={a}>
              <line x1={x1} x2={x1 + (x2 - x1) * a} y1={y} y2={y} stroke={colors.rice} strokeWidth={3} />
              {a > 0.95 ? <path d={`M ${x2 - 12} ${y - 9} L ${x2} ${y} L ${x2 - 12} ${y + 9}`} fill="none" stroke={colors.rice} strokeWidth={3} /> : null}
              {a >= 1
                ? [0, 1].map((k) => {
                    const t = ((frame + k * 20) % 40) / 40;
                    return <circle key={k} cx={x1 + (x2 - x1) * t} cy={y} r={5} fill={colors.paper} opacity={Math.sin(t * Math.PI)} />;
                  })
                : null}
            </g>
          );
        })}
        {/* siklus: dari tangan kembali ke indra */}
        <path
          d={`M ${(CARD_X[3] ?? 0) + CARD_W / 2} ${CARD_Y + CARD_H + 10} C ${(CARD_X[3] ?? 0) + CARD_W / 2} 790, ${(CARD_X[0] ?? 0) + CARD_W / 2} 790, ${(CARD_X[0] ?? 0) + CARD_W / 2} ${CARD_Y + CARD_H + 10}`}
          fill="none"
          stroke={colors.sun}
          strokeWidth={2.5}
          strokeDasharray={loopLen}
          strokeDashoffset={loopLen * (1 - loop)}
        />
      </svg>
      {loop > 0 ? (
        <div style={{ position: 'absolute', left: 0, right: 0, top: 742, textAlign: 'center', opacity: loop, fontFamily: fonts.mono, fontSize: 22, letterSpacing: '0.16em', color: colors.sun }}>
          UKUR → KIRIM → OLAH → BERTINDAK → UKUR LAGI
        </div>
      ) : null}
      {PARTS.map((part, i) => {
        const a = p(frame, at[i] ?? 0);
        if (a <= 0) return null;
        const pulse = ((frame - (at[i] ?? 0)) % 60) / 60;
        return (
          <div
            key={part.title}
            style={{
              position: 'absolute',
              left: CARD_X[i],
              top: CARD_Y,
              width: CARD_W,
              height: CARD_H,
              boxSizing: 'border-box',
              padding: '30px 28px',
              opacity: a,
              transform: `translateY(${(1 - a) * 24}px)`,
              fontFamily: fonts.sans,
              color: colors.paper,
              textAlign: 'center',
              ...panel,
            }}
          >
            <div style={{ fontFamily: fonts.mono, fontSize: 17, letterSpacing: '0.2em', color: colors.rice }}>0{i + 1}</div>
            <div style={{ position: 'relative', width: 120, height: 120, margin: '14px auto 0' }}>
              <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '1.5px solid rgba(244,241,234,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon name={part.icon} size={64} />
              </div>
              <div style={{ position: 'absolute', inset: -pulse * 14, borderRadius: '50%', border: `1.5px solid ${colors.rice}`, opacity: (1 - pulse) * 0.5 }} />
            </div>
            <div style={{ fontSize: 30, fontWeight: 700, marginTop: 20, lineHeight: 1.15 }}>{part.title}</div>
            <div style={{ fontSize: 21, color: colors.paperDim, marginTop: 10, whiteSpace: 'pre-line', lineHeight: 1.35 }}>{part.desc}</div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 10,
                marginTop: 22,
                padding: '8px 16px',
                borderRadius: 30,
                background: 'rgba(242,194,123,0.14)',
                border: `1px solid ${colors.sun}`,
                color: colors.sun,
                fontSize: 21,
                fontWeight: 600,
              }}
            >
              <Icon name={part.analogyIcon} size={26} color={colors.sun} />
              ibarat {part.analogy}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// ── 4 lapisan arsitektur ─────────────────────────────────────────────────

interface Layer {
  name: string;
  desc: string;
  icons: readonly IconName[];
  color: string;
}
const LAYERS: readonly Layer[] = [
  { name: 'Perangkat', desc: 'sensor & aktuator di lahan', icons: ['sensor', 'thermo', 'drop', 'valve', 'fan'], color: '#8a5a3b' },
  { name: 'Jaringan', desc: 'LoRa · NB-IoT · 4G · Wi-Fi', icons: ['gateway', 'signal', 'wifi'], color: '#5f7f3a' },
  { name: 'Pengolahan', desc: 'cloud & edge: simpan, analisis', icons: ['cloud', 'brain', 'chart'], color: '#3d6f7a' },
  { name: 'Aplikasi', desc: 'dasbor, notifikasi, kendali', icons: ['phone', 'alert', 'chart'], color: '#7a6a3d' },
];

/** Tumpukan 4 lapisan (bawah → atas). Data naik, perintah turun. */
export const LayerStack: React.FC<{ at: readonly number[]; flowAt: number }> = ({ at, flowAt }) => {
  const frame = useCurrentFrame();
  const PLATE_W = 980;
  const PLATE_H = 112;
  const X0 = 300;
  const yOf = (i: number): number => 690 - i * 150; // i=0 bawah
  const flow = frame >= flowAt;
  const up = ((frame - flowAt) % 72) / 72;
  const down = ((frame - flowAt + 36) % 72) / 72;
  return (
    <AbsoluteFill style={{ fontFamily: fonts.sans, color: colors.paper }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {flow ? (
          <g>
            <line x1={X0 + PLATE_W - 120} x2={X0 + PLATE_W - 120} y1={yOf(0) + 20} y2={yOf(3) + 60} stroke={colors.rice} strokeOpacity={0.4} strokeDasharray="4 8" strokeWidth={2} />
            <circle cx={X0 + PLATE_W - 120} cy={yOf(0) + 40 - up * (yOf(0) - yOf(3))} r={9} fill={colors.rice} />
            <line x1={X0 + 120} x2={X0 + 120} y1={yOf(3) + 60} y2={yOf(0) + 20} stroke={colors.sun} strokeOpacity={0.4} strokeDasharray="4 8" strokeWidth={2} />
            <circle cx={X0 + 120} cy={yOf(3) + 60 + down * (yOf(0) - yOf(3) - 20)} r={9} fill={colors.sun} />
          </g>
        ) : null}
      </svg>
      {LAYERS.map((l, i) => {
        const a = p(frame, at[i] ?? 0, 24);
        if (a <= 0) return null;
        return (
          <div
            key={l.name}
            style={{
              position: 'absolute',
              left: X0,
              top: yOf(i),
              width: PLATE_W,
              height: PLATE_H,
              opacity: a,
              transform: `translateY(${(1 - a) * 40}px) perspective(1400px) rotateX(18deg)`,
              borderRadius: 16,
              background: `linear-gradient(90deg, ${l.color}cc, ${l.color}66)`,
              border: '1px solid rgba(244,241,234,0.25)',
              boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 34px',
              boxSizing: 'border-box',
              gap: 26,
            }}
          >
            <div style={{ fontFamily: fonts.mono, fontSize: 18, color: colors.paperDim, width: 40 }}>L{i + 1}</div>
            <div style={{ width: 300 }}>
              <div style={{ fontSize: 32, fontWeight: 700 }}>{l.name}</div>
              <div style={{ fontSize: 20, color: colors.paperDim, marginTop: 4 }}>{l.desc}</div>
            </div>
            <div style={{ display: 'flex', gap: 22, marginLeft: 'auto' }}>
              {l.icons.map((ic, k) => (
                <div key={ic + k} style={{ opacity: p(frame, (at[i] ?? 0) + 10 + k * 5, 14) }}>
                  <Icon name={ic} size={46} />
                </div>
              ))}
            </div>
          </div>
        );
      })}
      {flow ? (
        <>
          <div style={{ position: 'absolute', left: X0 + PLATE_W + 40, top: yOf(1) + 30, color: colors.rice, fontSize: 24, fontWeight: 600 }}>↑ data naik</div>
          <div style={{ position: 'absolute', left: X0 + PLATE_W + 40, top: yOf(2) + 30, color: colors.sun, fontSize: 24, fontWeight: 600 }}>↓ perintah turun</div>
        </>
      ) : null}
    </AbsoluteFill>
  );
};

// ── Perbandingan jaringan ────────────────────────────────────────────────

interface Net {
  name: string;
  icon: IconName;
  range: number; // 1–5 (kualitatif)
  power: number;
  speed: number;
  fit: string;
}
const NETS: readonly Net[] = [
  { name: 'LoRa / LoRaWAN', icon: 'gateway', range: 5, power: 5, speed: 1, fit: 'sensor tersebar di\nlahan yang luas' },
  { name: 'NB-IoT', icon: 'signal', range: 4, power: 4, speed: 2, fit: 'daerah yang sudah\nada sinyal operator' },
  { name: '4G / LTE', icon: 'signal', range: 4, power: 2, speed: 5, fit: 'kamera, drone,\ndata besar' },
  { name: 'Wi-Fi', icon: 'wifi', range: 1, power: 2, speed: 4, fit: 'greenhouse, kandang\ndekat rumah' },
];

const Dots: React.FC<{ n: number; color: string }> = ({ n, color }) => (
  <div style={{ display: 'flex', gap: 7 }}>
    {Array.from({ length: 5 }, (_, i) => (
      <div key={i} style={{ width: 22, height: 10, borderRadius: 5, background: i < n ? color : 'rgba(244,241,234,0.12)' }} />
    ))}
  </div>
);

/** Kartu perbandingan 4 jaringan (skala kualitatif 1–5). `focus` = [frame, indeks kolom yang disorot]. */
export const ConnectivityCompare: React.FC<{ appearAt: number; focus: ReadonlyArray<readonly [number, readonly number[]]> }> = ({ appearAt, focus }) => {
  const frame = useCurrentFrame();
  const current = [...focus].reverse().find(([f]) => frame >= f)?.[1] ?? null;
  return (
    <AbsoluteFill style={{ fontFamily: fonts.sans, color: colors.paper }}>
      {NETS.map((n, i) => {
        const a = p(frame, appearAt + i * 8, 22);
        const on = current === null || current.includes(i);
        return (
          <div
            key={n.name}
            style={{
              position: 'absolute',
              left: 150 + i * 415,
              top: 170,
              width: 385,
              height: 600,
              boxSizing: 'border-box',
              padding: '30px 30px',
              opacity: a * (on ? 1 : 0.38),
              transform: `translateY(${(1 - a) * 24}px) scale(${on && current ? 1.03 : 1})`,
              ...panel,
              border: on && current ? `1.5px solid ${colors.rice}` : panel.border,
            }}
          >
            <Icon name={n.icon} size={56} color={on ? colors.rice : colors.paper} />
            <div style={{ fontSize: 31, fontWeight: 700, marginTop: 16 }}>{n.name}</div>
            {(
              [
                ['Jangkauan', n.range, colors.water],
                ['Hemat daya', n.power, colors.rice],
                ['Kecepatan data', n.speed, colors.sun],
              ] as const
            ).map(([label, v, c]) => (
              <div key={label} style={{ marginTop: 26 }}>
                <div style={{ fontSize: 20, color: colors.paperDim, marginBottom: 10 }}>{label}</div>
                <Dots n={v} color={c} />
              </div>
            ))}
            <div style={{ marginTop: 30, paddingTop: 20, borderTop: '1px solid rgba(244,241,234,0.12)' }}>
              <div style={{ fontFamily: fonts.mono, fontSize: 15, letterSpacing: '0.14em', color: colors.paperDim }}>COCOK UNTUK</div>
              <div style={{ fontSize: 22, marginTop: 8, whiteSpace: 'pre-line', lineHeight: 1.35 }}>{n.fit}</div>
            </div>
          </div>
        );
      })}
      <div style={{ position: 'absolute', left: 150, top: 800, fontFamily: fonts.mono, fontSize: 15, color: colors.paperFaint, letterSpacing: '0.1em', opacity: p(frame, appearAt + 40) }}>
        SKALA PERBANDINGAN KUALITATIF · NILAI SEBENARNYA BERGANTUNG PERANGKAT & LOKASI
      </div>
    </AbsoluteFill>
  );
};
