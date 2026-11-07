import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts, panel, status } from '../styles/theme';
import { Icon } from './Icons';
import { easeOut, formatId } from './ui';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

export interface IrrigationTimeline {
  detectAt: number; // sensor mendeteksi petak kering
  openAt: number; // katup terbuka
  closeAt: number; // target tercapai, katup menutup
}

const THRESHOLD = 30;
const TARGET = 60;
const MAIN_Y = 450;
const VALVE_X = 440;
const PLOTS = [
  { id: 1, x: 560, y: 175, needs: true },
  { id: 2, x: 920, y: 175, needs: false },
  { id: 3, x: 560, y: 505, needs: true },
  { id: 4, x: 920, y: 505, needs: false },
] as const;
const PW = 320;
const PH = 230;

/**
 * Skema irigasi otomatis dari atas: tandon → pipa utama → katup → 4 petak.
 * Hanya petak yang kelembapannya di bawah ambang batas yang dialiri air.
 */
export const IrrigationSchematic: React.FC<{ t: IrrigationTimeline }> = ({ t }) => {
  const frame = useCurrentFrame();
  const open = frame >= t.openAt && frame < t.closeAt;
  const valveRot = interpolate(frame, [t.openAt, t.openAt + 12, t.closeAt, t.closeAt + 12], [0, 90, 90, 0], clamp);
  const appear = interpolate(frame, [0, 24], [0, 1], { ...clamp, easing: easeOut });
  const flow = -frame * 4;
  const used = interpolate(frame, [t.openAt, t.closeAt], [0, 18.6], clamp);

  const moisture = (needs: boolean): number =>
    needs
      ? frame < t.openAt + 20
        ? interpolate(frame, [0, t.detectAt], [37, 27], clamp)
        : interpolate(frame, [t.openAt + 20, t.closeAt], [27, TARGET], { ...clamp, easing: (x) => 1 - (1 - x) ** 2 })
      : interpolate(frame, [0, 500], [57, 54], clamp);

  const state =
    frame < t.detectAt ? 'MEMANTAU' : frame < t.openAt ? 'TANAH KERING TERDETEKSI' : frame < t.closeAt ? 'KATUP TERBUKA' : 'TARGET TERCAPAI · KATUP TERTUTUP';
  const stateColor = frame < t.detectAt ? colors.paperDim : frame < t.openAt ? status.poor : frame < t.closeAt ? colors.water : status.good;

  return (
    <AbsoluteFill style={{ opacity: appear }}>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {/* tandon air */}
        <rect x={150} y={290} width={190} height={320} rx={18} fill="rgba(143,195,209,0.22)" stroke={colors.water} strokeOpacity={0.6} />
        {Array.from({ length: 5 }, (_, i) => (
          <path key={i} d={`M 170 ${330 + i * 56} q 20 -8 40 0 t 40 0 t 40 0 t 40 0`} stroke={colors.water} strokeOpacity={0.35} fill="none" transform={`translate(${Math.sin(frame / 20 + i) * 6} 0)`} />
        ))}
        <text x={245} y={650} textAnchor="middle" fill={colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 17 }}>
          SUMBER AIR
        </text>
        {/* pipa utama */}
        <line x1={340} x2={1260} y1={MAIN_Y} y2={MAIN_Y} stroke="rgba(244,241,234,0.25)" strokeWidth={14} strokeLinecap="round" />
        {open ? <line x1={340} x2={1260} y1={MAIN_Y} y2={MAIN_Y} stroke={colors.water} strokeWidth={6} strokeDasharray="14 16" strokeDashoffset={flow} /> : null}
        {/* petak */}
        {PLOTS.map((p) => {
          const m = moisture(p.needs);
          const wet = interpolate(m, [25, 60], [0, 1], clamp);
          const alert = p.needs && frame >= t.detectAt && frame < t.openAt;
          const pulse = ((frame - t.detectAt) % 30) / 30;
          const branchX = p.x + PW / 2;
          const branchY1 = MAIN_Y;
          const branchY2 = p.y < MAIN_Y ? p.y + PH : p.y;
          const flowing = open && p.needs;
          return (
            <g key={p.id}>
              <line x1={branchX} x2={branchX} y1={branchY1} y2={branchY2} stroke="rgba(244,241,234,0.25)" strokeWidth={9} />
              {flowing ? <line x1={branchX} x2={branchX} y1={branchY1} y2={branchY2} stroke={colors.water} strokeWidth={4} strokeDasharray="10 12" strokeDashoffset={p.y < MAIN_Y ? -flow : flow} /> : null}
              <rect
                x={p.x}
                y={p.y}
                width={PW}
                height={PH}
                rx={10}
                fill={`rgb(${Math.round(120 - wet * 60)}, ${Math.round(92 + wet * 40)}, ${Math.round(60 + wet * 30)})`}
                stroke={alert ? status.poor : 'rgba(244,241,234,0.25)'}
                strokeWidth={alert ? 3 : 1.5}
              />
              {/* deretan tanaman */}
              {Array.from({ length: 7 }, (_, r) =>
                Array.from({ length: 10 }, (_, c) => (
                  <circle key={`${r}-${c}`} cx={p.x + 22 + c * 31} cy={p.y + 24 + r * 31} r={4} fill={wet > 0.6 ? '#a7d26a' : '#7f9a4c'} opacity={0.85} />
                )),
              )}
              {flowing ? (
                <rect x={p.x} y={p.y} width={PW} height={PH} rx={10} fill={colors.water} opacity={0.1 + Math.sin(frame / 8) * 0.04} />
              ) : null}
              {alert ? <rect x={p.x - pulse * 14} y={p.y - pulse * 14} width={PW + pulse * 28} height={PH + pulse * 28} rx={14} fill="none" stroke={status.poor} opacity={1 - pulse} /> : null}
              <text x={p.x + 14} y={p.y + PH - 14} fill={colors.paper} style={{ fontFamily: fonts.mono, fontSize: 18 }}>
                PETAK {p.id} · {formatId(m, 0)}%
              </text>
            </g>
          );
        })}
        {/* katup */}
        <g transform={`translate(${VALVE_X} ${MAIN_Y})`}>
          <circle r={30} fill="#1a2420" stroke={open ? colors.water : colors.paper} strokeWidth={3} />
          <rect x={-4} y={-22} width={8} height={44} rx={3} fill={open ? colors.water : colors.paper} transform={`rotate(${valveRot})`} />
        </g>
        <text x={VALVE_X} y={MAIN_Y - 46} textAnchor="middle" fill={open ? colors.water : colors.paperDim} style={{ fontFamily: fonts.mono, fontSize: 17 }}>
          KATUP {open ? 'TERBUKA' : 'TERTUTUP'}
        </text>
      </svg>

      {/* panel pengendali */}
      <div style={{ position: 'absolute', left: 1330, top: 175, width: 440, padding: '26px 30px', boxSizing: 'border-box', fontFamily: fonts.sans, color: colors.paper, ...panel }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <Icon name="valve" size={40} color={stateColor} />
          <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.12em', color: colors.paperDim }}>PENGENDALI IRIGASI</div>
        </div>
        <div style={{ fontSize: 26, fontWeight: 700, color: stateColor, marginTop: 18, minHeight: 68, lineHeight: 1.3 }}>{state}</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 18, fontSize: 21, color: colors.paperDim }}>
          <span>Ambang kering</span>
          <span style={{ color: status.poor, fontWeight: 700 }}>&lt; {THRESHOLD}%</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 21, color: colors.paperDim }}>
          <span>Target kelembapan</span>
          <span style={{ color: status.good, fontWeight: 700 }}>{TARGET}%</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 21, color: colors.paperDim }}>
          <span>Air dialirkan</span>
          <span style={{ color: colors.water, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{formatId(used, 1)} m³</span>
        </div>
        <div style={{ fontFamily: fonts.mono, fontSize: 15, color: colors.paperFaint, marginTop: 22, letterSpacing: '0.1em' }}>DATA ILUSTRASI</div>
      </div>
    </AbsoluteFill>
  );
};
