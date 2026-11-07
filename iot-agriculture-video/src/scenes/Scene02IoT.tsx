import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../components/Atmosphere';
import { Backdrop } from '../components/Backdrop';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { Icon, type IconName } from '../components/Icons';
import { IoTNetwork, type NetworkLink, type NetworkNode } from '../components/IoTNetwork';
import { Shot } from '../components/Shot';
import { ChapterTitle, easeOut } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import { colors, fonts, panel } from '../styles/theme';
import type { SceneProps } from './types';

/**
 * SCENE 2 · 00:30–01:10 — Apa itu Internet of Things?
 *  A  0–14s    Sawah Bali dari udara; titik sensor bermunculan dan saling terhubung
 *  B  13.5–31s Diagram alur: Sensor → Gateway → Cloud → Ponsel → (kembali) Aksi
 *  C  30.5–40s Terasering Jatiluwih yang "terhubung"
 */
const XF = 12;
const SHOTS = {
  field: { from: 0, duration: sec(14) },
  pipeline: { from: sec(13.5), duration: sec(17.5) },
  connected: { from: sec(30.5), duration: sec(9.5) + SCENE_TRANSITION_FRAMES },
} as const;

/** Grid sensor semi-acak di atas sawah (koordinat persen gambar). */
const FIELD_NODES = Array.from({ length: 14 }, (_, i) => ({
  id: `f${i}`,
  x: 14 + (i % 5) * 17 + random(`fx${i}`) * 8,
  y: 44 + Math.floor(i / 5) * 17 + random(`fy${i}`) * 8,
  at: 40 + i * 9,
}));
const FIELD_LINKS: NetworkLink[] = FIELD_NODES.flatMap((n, i) => {
  const links: NetworkLink[] = [];
  if (i % 5 !== 4 && FIELD_NODES[i + 1]) links.push({ from: n.id, to: `f${i + 1}`, at: n.at + 14 });
  if (FIELD_NODES[i + 5]) links.push({ from: n.id, to: `f${i + 5}`, at: n.at + 20 });
  return links;
});

interface Stage {
  icon: IconName;
  title: string;
  desc: string;
}
const STAGES: readonly Stage[] = [
  { icon: 'sensor', title: 'Sensor', desc: 'mengukur tanah,\nair, dan cuaca' },
  { icon: 'gateway', title: 'Gateway', desc: 'mengirim data\nsecara nirkabel' },
  { icon: 'cloud', title: 'Cloud', desc: 'menyimpan &\nmengolah data' },
  { icon: 'phone', title: 'Ponsel Petani', desc: 'menampilkan\ninformasi' },
];
const STAGE_X = [330, 750, 1170, 1590] as const;
const STAGE_Y = 430;
const STAGE_AT = [24, 114, 228, 276] as const; // muncul bergiliran mengikuti subtitle

const Pipeline: React.FC = () => {
  const frame = useCurrentFrame();
  const actionP = interpolate(frame, [336, 376], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
  const loopLen = 1400;
  return (
    <AbsoluteFill>
      <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
        {STAGE_X.slice(0, -1).map((x, i) => {
          const nx = STAGE_X[i + 1] ?? x;
          const at = (STAGE_AT[i + 1] ?? 0) - 20;
          const p = interpolate(frame, [at, at + 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          const x1 = x + 82;
          const x2 = nx - 82;
          return (
            <g key={x}>
              <line x1={x1} x2={x1 + (x2 - x1) * p} y1={STAGE_Y} y2={STAGE_Y} stroke={colors.paper} strokeOpacity={0.45} strokeWidth={2} strokeDasharray="2 8" strokeLinecap="round" />
              {p >= 1
                ? [0, 1, 2].map((k) => {
                    const t = ((frame - at + k * 14) % 42) / 42;
                    return <circle key={k} cx={x1 + (x2 - x1) * t} cy={STAGE_Y} r={5} fill={colors.rice} opacity={Math.sin(t * Math.PI)} />;
                  })
                : null}
            </g>
          );
        })}
        {/* Jalur kembali: informasi menjadi tindakan di lahan */}
        <path
          d={`M ${STAGE_X[3]} ${STAGE_Y + 96} C ${STAGE_X[3]} 760, ${STAGE_X[0]} 760, ${STAGE_X[0]} ${STAGE_Y + 96}`}
          fill="none"
          stroke={colors.sun}
          strokeOpacity={0.8}
          strokeWidth={2}
          strokeDasharray={loopLen}
          strokeDashoffset={loopLen * (1 - actionP)}
        />
        {actionP > 0.98 ? <path d={`M ${STAGE_X[0] - 9} ${STAGE_Y + 112} L ${STAGE_X[0]} ${STAGE_Y + 96} L ${STAGE_X[0] + 9} ${STAGE_Y + 112}`} fill="none" stroke={colors.sun} strokeWidth={2} /> : null}
      </svg>
      {actionP > 0 ? (
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 718,
            textAlign: 'center',
            opacity: actionP,
            fontFamily: fonts.sans,
            fontSize: 26,
            fontWeight: 600,
            color: colors.sun,
            letterSpacing: '0.04em',
          }}
        >
          Aksi di lahan: menyiram, memupuk, waspada
        </div>
      ) : null}
      {STAGES.map((s, i) => {
        const at = STAGE_AT[i] ?? 0;
        const p = interpolate(frame, [at, at + 22], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
        const x = STAGE_X[i] ?? 0;
        const pulse = (((frame - at) % 50) / 50) * (p >= 1 ? 1 : 0);
        return (
          <div key={s.title} style={{ position: 'absolute', left: x - 140, top: STAGE_Y - 82, width: 280, textAlign: 'center', opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>
            <div style={{ position: 'relative', width: 164, height: 164, margin: '0 auto' }}>
              <div style={{ position: 'absolute', inset: 0, ...panel, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon name={s.icon} size={70} />
              </div>
              <div style={{ position: 'absolute', inset: -pulse * 18, borderRadius: '50%', border: `1.5px solid ${colors.rice}`, opacity: (1 - pulse) * 0.6 }} />
            </div>
            <div style={{ fontFamily: fonts.mono, fontSize: 16, letterSpacing: '0.2em', color: colors.rice, marginTop: 22 }}>0{i + 1}</div>
            <div style={{ fontFamily: fonts.sans, fontSize: 32, fontWeight: 700, color: colors.paper, marginTop: 4 }}>{s.title}</div>
            <div style={{ fontFamily: fonts.sans, fontSize: 21, color: colors.paperDim, marginTop: 6, whiteSpace: 'pre-line', lineHeight: 1.35 }}>{s.desc}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const Scene02IoT: React.FC<SceneProps> = ({ scene }) => {
  const aerial = photo('baliAerial');
  const terraces = photo('jatiluwihWide');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Sawah terhubung" from={SHOTS.field.from} durationInFrames={SHOTS.field.duration}>
        <CinematicPhoto
          src={aerial.src}
          width={aerial.width}
          height={aerial.height}
          durationInFrames={SHOTS.field.duration}
          grade="lush"
          camera={{ from: { x: 50, y: 55, zoom: 1.04 }, to: { x: 54, y: 60, zoom: 1.2 } }}
          shake={0.8}
          renderOverlay={(project) => {
            const nodes: NetworkNode[] = FIELD_NODES.map((n) => ({ ...project(n.x, n.y), id: n.id, at: n.at }));
            return <IoTNetwork nodes={nodes} links={FIELD_LINKS} opacity={0.85} />;
          }}
        />
        <Mist bands={[30, 50]} intensity={0.08} speed={0.5} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={30} hold={120} />
      </Shot>

      <Shot name="B · Alur data" from={SHOTS.pipeline.from} durationInFrames={SHOTS.pipeline.duration} fadeIn={XF}>
        <Backdrop
          src={aerial.src}
          width={aerial.width}
          height={aerial.height}
          durationInFrames={SHOTS.pipeline.duration}
          camera={{ from: { x: 56, y: 60, zoom: 1.2 }, to: { x: 60, y: 62, zoom: 1.3 }, easing: LINEAR_DRIFT }}
          dim={0.62}
        />
        <Pipeline />
      </Shot>

      <Shot name="C · Sawah berbicara" from={SHOTS.connected.from} durationInFrames={SHOTS.connected.duration} fadeIn={XF} focusPull>
        <CinematicPhoto
          src={terraces.src}
          width={terraces.width}
          height={terraces.height}
          durationInFrames={SHOTS.connected.duration}
          grade="golden"
          camera={{ from: { x: 62, y: 50, zoom: 1.25 }, to: { x: 46, y: 54, zoom: 1.12 }, easing: LINEAR_DRIFT }}
          parallax={{ horizon: 44, depth: 1.4, feather: 18 }}
          seed={7}
          renderOverlay={(project) => {
            const pts = [
              { id: 'a', x: 22, y: 62, label: 'KELEMBAPAN 42%' },
              { id: 'b', x: 40, y: 48 },
              { id: 'c', x: 55, y: 66, label: 'SUHU 29°C' },
              { id: 'd', x: 70, y: 52 },
              { id: 'e', x: 84, y: 70, label: 'HUJAN 0 MM' },
            ];
            const nodes: NetworkNode[] = pts.map((n, i) => ({ ...project(n.x, n.y), id: n.id, at: 14 + i * 10, label: n.label }));
            const links: NetworkLink[] = pts.slice(1).map((n, i) => ({ from: pts[i]?.id ?? 'a', to: n.id, at: 30 + i * 10 }));
            return <IoTNetwork nodes={nodes} links={links} opacity={0.8} />;
          }}
        />
        <SunGlow origin="80% 5%" strength={0.28} />
        <FloatingParticles seed="iot-c" count={30} opacity={0.35} />
      </Shot>
    </AbsoluteFill>
  );
};
