import { AbsoluteFill, Easing, useCurrentFrame } from 'remotion';
import { colors, fonts, status } from '../styles/theme';
import { BarChart, LineChart } from './Charts';
import { Icon, type IconName } from './Icons';
import { Metric, Panel, useProgress } from './ui';

const ease = Easing.bezier(0.45, 0, 0.2, 1);

/** Pose kamera di atas kanvas dasbor: titik tengah (cx, cy) dan zoom. */
export interface DashCam {
  at: number;
  cx: number;
  cy: number;
  zoom: number;
}

const camAt = (keys: readonly DashCam[], frame: number): Omit<DashCam, 'at'> => {
  const first = keys[0];
  if (!first) return { cx: 960, cy: 540, zoom: 1 };
  if (frame <= first.at) return first;
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1];
    const b = keys[i];
    if (a && b && frame <= b.at) {
      const t = ease((frame - a.at) / Math.max(1, b.at - a.at));
      return { cx: a.cx + (b.cx - a.cx) * t, cy: a.cy + (b.cy - a.cy) * t, zoom: a.zoom + (b.zoom - a.zoom) * t };
    }
  }
  return keys[keys.length - 1] ?? first;
};

const MOISTURE_7D = [52, 47, 41, 36, 31, 55, 49] as const;
const DAYS = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'] as const;
const WATER_7D = [24, 28, 31, 22, 30, 35, 12] as const; // total 182 m³
const PLOT_STATUS = ['good', 'good', 'poor', 'good', 'good', 'fair', 'good', 'good'] as const;
const FORECAST: ReadonlyArray<{ day: string; icon: IconName; text: string }> = [
  { day: 'Hari ini', icon: 'drop', text: 'Hujan sore\n12 mm' },
  { day: 'Besok', icon: 'sun', text: 'Cerah\n0 mm' },
  { day: 'Kamis', icon: 'sun', text: 'Cerah\n0 mm' },
  { day: 'Jumat', icon: 'drop', text: 'Gerimis\n4 mm' },
  { day: 'Sabtu', icon: 'sun', text: 'Berawan\n0 mm' },
];

interface AlertItem {
  at: number;
  color: string;
  icon: IconName;
  title: string;
  body: string;
}

const AlertRow: React.FC<AlertItem> = ({ at, color, icon, title, body }) => {
  const p = useProgress(at, 18);
  if (p <= 0) return null;
  return (
    <div style={{ display: 'flex', gap: 14, padding: '14px 0', borderTop: '1px solid rgba(244,241,234,0.1)', opacity: p, transform: `translateX(${(1 - p) * 20}px)` }}>
      <Icon name={icon} size={34} color={color} />
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color }}>{title}</div>
        <div style={{ fontSize: 17, color: colors.paperDim, marginTop: 4, lineHeight: 1.35 }}>{body}</div>
      </div>
    </div>
  );
};

/**
 * Dasbor pertanian cerdas di kanvas 1920×1080, "difilmkan" oleh kamera virtual
 * yang berpindah antar-panel. Semua angka adalah data ilustrasi.
 */
export const FarmDashboard: React.FC<{ camera: readonly DashCam[]; alertsAt: number }> = ({ camera, alertsAt }) => {
  const frame = useCurrentFrame();
  const cam = camAt(camera, frame);
  const clock = `14:${String(20 + Math.floor(frame / 240)).padStart(2, '0')}`;
  const live = Math.floor(frame / 15) % 2 === 0;

  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: 1920,
          height: 1080,
          transformOrigin: '0 0',
          transform: `translate(${960 - cam.cx * cam.zoom}px, ${540 - cam.cy * cam.zoom}px) scale(${cam.zoom})`,
          fontFamily: fonts.sans,
          color: colors.paper,
        }}
      >
        {/* Header */}
        <Panel x={120} y={60} w={1680} h={76} delay={0} style={{ padding: '0 30px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Icon name="leaf" size={34} color={colors.rice} />
            <span style={{ fontSize: 26, fontWeight: 700 }}>Sawah Subak Desa</span>
            <span style={{ fontSize: 20, color: colors.paperDim }}>· Dasbor Pertanian</span>
          </div>
          <div style={{ display: 'flex', gap: 28, fontFamily: fonts.mono, fontSize: 18, color: colors.paperDim }}>
            <span>
              <span style={{ color: status.good, opacity: live ? 1 : 0.3 }}>●</span> 18 sensor aktif
            </span>
            <span>Selasa {clock} WITA</span>
            <span style={{ border: '1px solid rgba(244,241,234,0.25)', borderRadius: 4, padding: '2px 8px', fontSize: 14, letterSpacing: '0.14em' }}>DATA ILUSTRASI</span>
          </div>
        </Panel>

        {/* KPI */}
        {[
          { label: 'Kelembapan tanah rata-rata', value: 46, unit: '%', dec: 0, accent: colors.water },
          { label: 'Suhu udara', value: 29.1, unit: '°C', dec: 1, accent: colors.sun },
          { label: 'Curah hujan hari ini', value: 12, unit: 'mm', dec: 0, accent: colors.paper },
          { label: 'Air terpakai (7 hari)', value: 182, unit: 'm³', dec: 0, accent: colors.rice },
        ].map((k, i) => (
          <Panel key={k.label} x={120 + i * 425} y={156} w={405} h={150} delay={10 + i * 8}>
            <Metric label={k.label} value={k.value} unit={k.unit} decimals={k.dec} delay={16 + i * 8} accent={k.accent} size={54} />
          </Panel>
        ))}

        {/* Grafik kelembapan */}
        <Panel x={120} y={326} w={820} h={450} delay={40} title="Kelembapan tanah · 7 hari">
          <LineChart data={MOISTURE_7D} labels={DAYS} width={768} height={340} min={20} max={60} delay={70} duration={220} threshold={{ value: 30, label: 'BATAS KERING 30%' }} unit="%" />
        </Panel>

        {/* Peta petak */}
        <Panel x={960} y={326} w={420} h={450} delay={52} title="Peta petak">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            {PLOT_STATUS.map((s, i) => {
              const c = status[s];
              const flash = s === 'poor' && Math.floor(frame / 14) % 2 === 0 && frame > alertsAt;
              return (
                <div key={i} style={{ height: 76, borderRadius: 8, background: `${c}${flash ? '66' : '40'}`, border: `1.5px solid ${c}`, display: 'flex', alignItems: 'flex-end', padding: '8px 10px', boxSizing: 'border-box', fontFamily: fonts.mono, fontSize: 16 }}>
                  PETAK {i + 1}
                </div>
              );
            })}
          </div>
        </Panel>

        {/* Peringatan */}
        <Panel x={1400} y={326} w={400} h={450} delay={64} title="Peringatan">
          <AlertRow at={alertsAt} color={status.poor} icon="alert" title="Petak 3 kering · 28%" body="Irigasi dijadwalkan 05.30 besok" />
          <AlertRow at={alertsAt + 40} color={colors.water} icon="drop" title="Hujan sore ini" body="Irigasi petak 1–2 ditunda" />
          <AlertRow at={alertsAt + 80} color={status.fair} icon="drone" title="Drone: stres di petak 6" body="Cek hama sebelum menyemprot" />
        </Panel>

        {/* Pemakaian air */}
        <Panel x={120} y={796} w={820} h={250} delay={76} title="Pemakaian air harian (m³)">
          <BarChart data={WATER_7D} labels={DAYS} width={768} height={160} max={40} delay={600} highlight={6} />
        </Panel>

        {/* Prakiraan */}
        <Panel x={960} y={796} w={840} h={250} delay={88} title="Prakiraan cuaca">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            {FORECAST.map((f) => (
              <div key={f.day} style={{ textAlign: 'center', width: 150 }}>
                <div style={{ fontSize: 18, color: colors.paperDim }}>{f.day}</div>
                <div style={{ margin: '10px auto', width: 44 }}>
                  <Icon name={f.icon} size={44} color={f.icon === 'drop' ? colors.water : colors.sun} />
                </div>
                <div style={{ fontSize: 18, whiteSpace: 'pre-line', lineHeight: 1.3 }}>{f.text}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </AbsoluteFill>
  );
};
