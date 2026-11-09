import { interpolate, useCurrentFrame } from 'remotion';
import { Icon, type IconName } from '../../../components/Icons';
import { easeOut, formatId } from '../../../components/ui';
import { colors, fonts, panel, status } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/**
 * Peringatan dini penyakit jamur di kebun teh: data stasiun cuaca (kelembapan, jam
 * daun basah) menaikkan meter risiko → notifikasi ke petani. Ilustrasi.
 */
export const DiseaseRisk: React.FC<{ highAt: number; alertAt: number }> = ({ highAt, alertAt }) => {
  const frame = useCurrentFrame();
  const a = interpolate(frame, [0, 24], [0, 1], { ...clamp, easing: easeOut });
  const g = interpolate(frame, [20, highAt], [0, 1], { ...clamp, easing: (x) => x });
  const rh = 78 + 16 * g;
  const wet = 3 + 9 * g;
  const rain = 2 + 10 * g;
  const temp = 23 - 2 * g;
  const risk = interpolate(frame, [30, highAt], [0.15, 0.88], { ...clamp, easing: easeOut });
  const alert = interpolate(frame, [alertAt, alertAt + 20], [0, 1], { ...clamp, easing: easeOut });
  const label = risk < 0.4 ? ['RENDAH', status.good] : risk < 0.7 ? ['SEDANG', status.fair] : ['TINGGI', status.poor];
  const R = 150;
  const ang = Math.PI * (1 - risk);
  return (
    <div style={{ position: 'absolute', inset: 0, opacity: a, fontFamily: fonts.sans, color: colors.paper }}>
      <div style={{ position: 'absolute', left: 110, top: 150, width: 520, boxSizing: 'border-box', padding: '26px 30px', ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>STASIUN CUACA · BLOK 3</div>
        {(
          [
            ['thermo', 'Suhu udara', `${formatId(temp, 1)} °C`],
            ['drop', 'Kelembapan udara', `${formatId(rh, 0)} %`],
            ['leaf', 'Daun basah', `${formatId(wet, 0)} jam`],
            ['cloud', 'Hujan hari ini', `${formatId(rain, 0)} mm`],
          ] as ReadonlyArray<readonly [IconName, string, string]>
        ).map(([ic, l, v]) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 20 }}>
            <Icon name={ic} size={34} color={colors.water} />
            <span style={{ fontSize: 23, color: colors.paperDim, flex: 1 }}>{l}</span>
            <span style={{ fontSize: 30, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{v}</span>
          </div>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 1180, top: 150, width: 620, boxSizing: 'border-box', padding: '26px 30px', textAlign: 'center', ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>RISIKO PENYAKIT JAMUR (CACAR DAUN)</div>
        <svg width={360} height={200} style={{ marginTop: 14, overflow: 'visible' }}>
          <defs>
            <linearGradient id="riskg" x1="0" x2="1">
              <stop offset="0%" stopColor={status.good} />
              <stop offset="55%" stopColor={status.fair} />
              <stop offset="100%" stopColor={status.poor} />
            </linearGradient>
          </defs>
          <path d={`M ${180 - R} 180 A ${R} ${R} 0 0 1 ${180 + R} 180`} stroke="url(#riskg)" strokeWidth={22} fill="none" strokeLinecap="round" />
          <line x1={180} y1={180} x2={180 + Math.cos(ang) * (R - 30)} y2={180 - Math.sin(ang) * (R - 30)} stroke={colors.paper} strokeWidth={5} strokeLinecap="round" />
          <circle cx={180} cy={180} r={12} fill={colors.paper} />
        </svg>
        <div style={{ fontSize: 46, fontWeight: 800, color: label[1], marginTop: 6 }}>{label[0]}</div>
        <div style={{ fontSize: 19, color: colors.paperDim, marginTop: 6 }}>dihitung dari kelembapan & lama daun basah</div>
      </div>
      {alert > 0 ? (
        <div
          style={{
            position: 'absolute',
            left: 1180,
            top: 600,
            width: 620,
            boxSizing: 'border-box',
            padding: '20px 26px',
            display: 'flex',
            gap: 16,
            alignItems: 'center',
            opacity: alert,
            transform: `translateY(${(1 - alert) * 14}px)`,
            ...panel,
            border: `1.5px solid ${status.poor}`,
          }}
        >
          <Icon name="phone" size={44} color={status.poor} />
          <div>
            <div style={{ fontSize: 24, fontWeight: 700, color: status.poor }}>Waspada cacar daun di Blok 3</div>
            <div style={{ fontSize: 19, color: colors.paperDim, marginTop: 4 }}>Periksa daun & siapkan penyemprotan pencegahan</div>
          </div>
        </div>
      ) : null}
      <div style={{ position: 'absolute', left: 110, top: 600, fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
    </div>
  );
};
