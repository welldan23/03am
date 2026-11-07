import { interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts } from '../styles/theme';

export interface NetworkNode {
  id: string;
  x: number; // piksel layar
  y: number;
  label?: string;
  /** Frame munculnya node (relatif ke awal komponen). */
  at: number;
}

export interface NetworkLink {
  from: string;
  to: string;
  at: number;
}

interface IoTNetworkProps {
  nodes: readonly NetworkNode[];
  links: readonly NetworkLink[];
  /** Opasitas keseluruhan — jaga lembut agar foto tetap jadi bintang utama. */
  opacity?: number;
  color?: string;
  /** Tampilkan "paket data" yang mengalir di sepanjang koneksi. */
  packets?: boolean;
}

const DRAW = 18; // lama garis koneksi tergambar (frame)

/**
 * Jaringan IoT: node sensor dengan denyut halus + garis koneksi yang tergambar
 * bertahap + paket data kecil yang mengalir. Dibuat tipis & tenang, bukan hologram.
 */
export const IoTNetwork: React.FC<IoTNetworkProps> = ({
  nodes,
  links,
  opacity = 0.75,
  color = colors.paper,
  packets = true,
}) => {
  const frame = useCurrentFrame();
  const byId = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, overflow: 'visible', opacity }}>
      {links.map((l, i) => {
        const a = byId.get(l.from);
        const b = byId.get(l.to);
        if (!a || !b) return null;
        const t = interpolate(frame, [l.at, l.at + DRAW], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        if (t <= 0) return null;
        const len = Math.hypot(b.x - a.x, b.y - a.y);
        // Lengkungan halus — seperti tautan radio, bukan kabel lurus.
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2 - len * 0.12;
        const d = `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`;
        const pk = ((frame - l.at - DRAW + i * 11) % 48) / 48;
        const showPk = packets && frame > l.at + DRAW;
        const px = (1 - pk) ** 2 * a.x + 2 * (1 - pk) * pk * mx + pk ** 2 * b.x;
        const py = (1 - pk) ** 2 * a.y + 2 * (1 - pk) * pk * my + pk ** 2 * b.y;
        return (
          <g key={`${l.from}-${l.to}`}>
            <path
              d={d}
              fill="none"
              stroke={color}
              strokeOpacity={0.55}
              strokeWidth={1.4}
              strokeDasharray={`${len * 1.1}`}
              strokeDashoffset={len * 1.1 * (1 - t)}
            />
            {showPk ? <circle cx={px} cy={py} r={3} fill={colors.rice} opacity={Math.sin(pk * Math.PI)} /> : null}
          </g>
        );
      })}
      {nodes.map((n, i) => {
        const t = interpolate(frame, [n.at, n.at + 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        if (t <= 0) return null;
        const pulse = ((frame - n.at + i * 9) % 60) / 60;
        return (
          <g key={n.id} opacity={t}>
            <circle cx={n.x} cy={n.y} r={6 + pulse * 26} fill="none" stroke={color} strokeOpacity={0.5 * (1 - pulse)} strokeWidth={1.2} />
            <circle cx={n.x} cy={n.y} r={5.5 * t} fill={color} />
            <circle cx={n.x} cy={n.y} r={2.2} fill={colors.riceDeep} />
            {n.label ? (
              <text
                x={n.x + 14}
                y={n.y - 12}
                fill={color}
                fillOpacity={0.85 * t}
                style={{ fontFamily: fonts.mono, fontSize: 15, letterSpacing: '0.08em' }}
              >
                {n.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};
