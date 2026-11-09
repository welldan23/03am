import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { Icon, type IconName } from '../../../components/Icons';
import { easeOut, formatId } from '../../../components/ui';
import { colors, fonts, panel, status } from '../../../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export interface GreenhouseTimeline {
  fanOn: number;
  fanOff: number;
  mistOff: number;
  ecLowAt: number;
  doseOn: number;
  doseOff: number;
}

const GROUND = 790;
const LEFT = 150;
const RIGHT = 1190;
const WALL_TOP = 560;
const LIMIT = 32;

/**
 * Greenhouse hidroponik (penampang samping): sensor suhu/kelembapan & cahaya,
 * kipas + pengabut otomatis saat suhu > 32°C, dan pompa dosis nutrisi A/B saat EC turun.
 * Angka adalah ilustrasi.
 */
export const Greenhouse: React.FC<{ t: GreenhouseTimeline }> = ({ t }) => {
  const frame = useCurrentFrame();
  const appear = interpolate(frame, [0, 24], [0, 1], { ...clamp, easing: easeOut });
  const temp =
    frame < t.fanOn ? interpolate(frame, [0, t.fanOn], [30.4, 33.1], clamp) : interpolate(frame, [t.fanOn, t.fanOn + 140], [33.1, 28.6], { ...clamp, easing: easeOut });
  const fan = frame >= t.fanOn && frame < t.fanOff;
  const mist = frame >= t.fanOn && frame < t.mistOff;
  const rh = interpolate(frame, [t.fanOn, t.fanOn + 120], [66, 78], clamp);
  const ec = frame < t.doseOn ? interpolate(frame, [0, t.ecLowAt], [1.9, 1.25], clamp) : interpolate(frame, [t.doseOn, t.doseOff], [1.25, 1.85], { ...clamp, easing: easeOut });
  const dose = frame >= t.doseOn && frame < t.doseOff;
  const ecLow = ec < 1.5;
  const fanAngle = fan ? frame * 22 : 0;

  const roof = `M ${LEFT} ${GROUND} L ${LEFT} ${WALL_TOP} Q ${(LEFT + RIGHT) / 2} 150 ${RIGHT} ${WALL_TOP} L ${RIGHT} ${GROUND}`;
  const roofY = (x: number): number => {
    // titik pada kurva kuadratik (perkiraan untuk posisi rusuk)
    const u = (x - LEFT) / (RIGHT - LEFT);
    return (1 - u) * (1 - u) * WALL_TOP + 2 * (1 - u) * u * 150 + u * u * WALL_TOP;
  };

  return (
    <AbsoluteFill style={{ opacity: appear }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        <rect x={60} y={GROUND} width={1220} height={24} fill="#5b3f2b" />
        <path d={roof} fill="rgba(220,235,240,0.07)" stroke="rgba(244,241,234,0.55)" strokeWidth={3} />
        {Array.from({ length: 9 }, (_, i) => {
          const x = LEFT + ((i + 1) * (RIGHT - LEFT)) / 10;
          return <line key={i} x1={x} x2={x} y1={roofY(x)} y2={GROUND} stroke="rgba(244,241,234,0.12)" />;
        })}
        {/* meja NFT + tanaman (2 tingkat) */}
        {[700, 610].map((y, tier) => (
          <g key={y}>
            <rect x={300} y={y} width={760} height={16} rx={8} fill="#e8e4da" />
            {[340, 1020].map((x) => (
              <rect key={x} x={x} y={y + 16} width={8} height={GROUND - y - 16} fill="#9e988b" />
            ))}
            {Array.from({ length: 11 }, (_, i) => {
              const x = 330 + i * 70;
              const grow = 1 + Math.sin(frame / 40 + i + tier) * 0.03;
              return (
                <g key={i} transform={`translate(${x} ${y}) scale(${grow})`}>
                  <ellipse cx={-10} cy={-22} rx={14} ry={26} fill="#7fb85a" transform="rotate(-25)" />
                  <ellipse cx={10} cy={-22} rx={14} ry={26} fill="#93c96a" transform="rotate(25)" />
                  <ellipse cx={0} cy={-30} rx={12} ry={28} fill="#a7d67a" />
                </g>
              );
            })}
          </g>
        ))}
        {/* jalur pengabut */}
        <line x1={300} x2={1060} y1={470} y2={470} stroke="#9e988b" strokeWidth={5} />
        {Array.from({ length: 9 }, (_, i) => {
          const x = 320 + i * 90;
          return (
            <g key={i}>
              <rect x={x - 5} y={470} width={10} height={10} fill="#9e988b" />
              {mist
                ? Array.from({ length: 10 }, (_, k) => {
                    const u = ((frame * 2 + k * 9 + i * 5) % 50) / 50;
                    const dx = (random(`m${i}${k}`) - 0.5) * 70 * u;
                    return <circle key={k} cx={x + dx} cy={482 + u * 90} r={2.2} fill={colors.paper} opacity={(1 - u) * 0.7} />;
                  })
                : null}
            </g>
          );
        })}
        {/* sensor suhu & kelembapan */}
        <line x1={560} x2={560} y1={roofY(560)} y2={400} stroke="#9e988b" strokeWidth={2} />
        {[0, 1, 2, 3].map((k) => (
          <ellipse key={k} cx={560} cy={402 + k * 9} rx={24 - k} ry={5} fill="#e8e4da" />
        ))}
        {/* sensor cahaya di atap */}
        <path d={`M 840 ${roofY(840) - 2} a 16 16 0 0 1 32 0 z`} fill="rgba(240,240,255,0.85)" />
        {/* kipas exhaust */}
        <g transform={`translate(${RIGHT} 660)`}>
          <circle r={52} fill="#2b3430" stroke="#4b5650" strokeWidth={4} />
          <g transform={`rotate(${fanAngle})`}>
            {[0, 90, 180, 270].map((a) => (
              <ellipse key={a} cx={0} cy={-24} rx={11} ry={24} fill={fan ? colors.water : '#7a8580'} transform={`rotate(${a})`} />
            ))}
          </g>
          <circle r={8} fill="#cfcac0" />
        </g>
        {fan
          ? Array.from({ length: 6 }, (_, i) => {
              const u = ((frame * 3 + i * 17) % 80) / 80;
              return <path key={i} d={`M ${RIGHT + 60 + u * 90} ${630 + i * 12} q 14 -8 28 0`} stroke={colors.paper} strokeOpacity={(1 - u) * 0.6} strokeWidth={2} fill="none" />;
            })
          : null}
        {/* tangki nutrisi + pompa dosis */}
        <rect x={170} y={700} width={110} height={88} rx={8} fill="rgba(143,195,209,0.25)" stroke="#9e988b" />
        <rect x={172} y={720} width={106} height={66} rx={6} fill={`rgba(${Math.round(120 + ec * 20)}, ${Math.round(160 + ec * 15)}, 120, 0.6)`} />
        <rect x={250} y={672} width={8} height={90} fill="#cfcac0" />
        <rect x={244} y={662} width={20} height={14} rx={3} fill="#2b3430" />
        {(['A', 'B'] as const).map((l, k) => (
          <g key={l}>
            <rect x={172 + k * 40} y={600} width={30} height={52} rx={5} fill={k ? '#c9a45a' : '#7aa3c9'} />
            <text x={187 + k * 40} y={632} textAnchor="middle" fill="#111" style={{ fontFamily: fonts.sans, fontSize: 18, fontWeight: 800 }}>
              {l}
            </text>
            <line x1={187 + k * 40} x2={200 + k * 20} y1={652} y2={712} stroke="#9e988b" strokeWidth={2} />
            {dose
              ? Array.from({ length: 3 }, (_, d) => {
                  const u = ((frame * 2 + d * 16 + k * 8) % 48) / 48;
                  return <circle key={d} cx={187 + k * 40 + (13 - k * 20) * u} cy={652 + u * 60} r={3.5} fill={k ? '#e0b660' : '#8fb8de'} />;
                })
              : null}
          </g>
        ))}
        {/* label */}
        {(
          [
            [560, 372, 'SUHU & RH'],
            [856, roofY(840) - 26, 'CAHAYA'],
            [RIGHT, 586, 'KIPAS'],
            [680, 450, 'PENGABUT'],
            [225, 588, 'POMPA DOSIS'],
            [225, 812, 'TANGKI NUTRISI · EC/pH'],
          ] as const
        ).map(([x, y, l]) => (
          <text key={l} x={x} y={y} textAnchor="middle" fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 15, letterSpacing: '0.08em' }}>
            {l}
          </text>
        ))}
      </svg>

      {/* Panel pembacaan */}
      <div style={{ position: 'absolute', left: 1330, top: 140, width: 460, boxSizing: 'border-box', padding: '24px 28px', fontFamily: fonts.sans, color: colors.paper, ...panel }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.14em', color: colors.paperDim }}>GREENHOUSE · LANGSUNG</div>
        {(
          [
            ['thermo', 'Suhu udara', `${formatId(temp, 1)} °C`, temp > LIMIT ? status.poor : colors.paper],
            ['drop', 'Kelembapan', `${formatId(rh, 0)} %`, colors.paper],
            ['sun', 'Cahaya', '52.000 lux', colors.paper],
            ['leaf', 'EC nutrisi', `${formatId(ec, 2)} mS/cm`, ecLow ? status.poor : colors.paper],
            ['target', 'pH nutrisi', '6,1', colors.paper],
          ] as ReadonlyArray<readonly [IconName, string, string, string]>
        ).map(([ic, l, v, c]) => (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 16 }}>
            <Icon name={ic} size={30} color={c} />
            <span style={{ fontSize: 21, color: colors.paperDim, flex: 1 }}>{l}</span>
            <span style={{ fontSize: 26, fontWeight: 700, color: c, fontVariantNumeric: 'tabular-nums' }}>{v}</span>
          </div>
        ))}
        <div style={{ borderTop: '1px solid rgba(244,241,234,0.12)', marginTop: 20, paddingTop: 14 }}>
          {(
            [
              ['Kipas exhaust', fan],
              ['Pengabut', mist],
              ['Pompa dosis A/B', dose],
            ] as const
          ).map(([l, on]) => (
            <div key={l} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 21, marginTop: 8 }}>
              <span style={{ color: colors.paperDim }}>{l}</span>
              <span style={{ fontWeight: 700, color: on ? status.good : colors.paperFaint }}>{on ? 'MENYALA' : 'MATI'}</span>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 17, color: colors.paperDim, marginTop: 14 }}>Batas suhu: {LIMIT} °C · Target EC: 1,8–2,0</div>
        <div style={{ fontFamily: fonts.mono, fontSize: 14, color: colors.paperFaint, marginTop: 10, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
      </div>
    </AbsoluteFill>
  );
};
