import { AbsoluteFill } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../components/Atmosphere';
import { Backdrop } from '../components/Backdrop';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { IrrigationSchematic } from '../components/IrrigationSchematic';
import { LocationTag } from '../components/LocationTag';
import { Shot } from '../components/Shot';
import { Callout, ChapterTitle } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import type { SceneProps } from './types';

/**
 * SCENE 4 · 01:50–02:30 — Irigasi otomatis.
 *  A  0–9.5s   Saluran subak (Babahan, Tabanan)
 *  B  9–28.5s  Skema: petak kering → katup terbuka → air hanya ke petak yang perlu → katup menutup
 *  C1 28–34.5s Irigasi tetes (Kerala, India)
 *  C2 34–40s   Penetes air close-up
 */
const XF = 12;
const SHOTS = {
  canal: { from: 0, duration: sec(9.5) },
  schematic: { from: sec(9), duration: sec(19.5) },
  drip: { from: sec(28), duration: sec(6.5) },
  emitter: { from: sec(34), duration: sec(6) + SCENE_TRANSITION_FRAMES },
} as const;

export const Scene04Irrigation: React.FC<SceneProps> = ({ scene }) => {
  const canal = photo('subakCanalFall');
  const stream = photo('subakStream');
  const drip = photo('dripKerala');
  const emitter = photo('dripEmitter');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Saluran subak" from={SHOTS.canal.from} durationInFrames={SHOTS.canal.duration}>
        <CinematicPhoto
          src={canal.src}
          width={canal.width}
          height={canal.height}
          durationInFrames={SHOTS.canal.duration}
          grade="lush"
          camera={{ from: { x: 50, y: 60, zoom: 1.04 }, to: { x: 44, y: 66, zoom: 1.2 } }}
          parallax={{ horizon: 45, depth: 1.5, feather: 18 }}
          seed={21}
        />
        <Mist bands={[70, 84]} intensity={0.14} speed={0.7} />
        <SunGlow origin="85% 0%" strength={0.22} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={96} />
        <LocationTag place="Subak Aya" region="Babahan, Tabanan, Bali" delay={126} hold={80} />
      </Shot>

      <Shot name="B · Skema irigasi" from={SHOTS.schematic.from} durationInFrames={SHOTS.schematic.duration} fadeIn={XF}>
        <Backdrop
          src={stream.src}
          width={stream.width}
          height={stream.height}
          durationInFrames={SHOTS.schematic.duration}
          camera={{ from: { x: 50, y: 55, zoom: 1.1 }, to: { x: 56, y: 55, zoom: 1.2 }, easing: LINEAR_DRIFT }}
          dim={0.66}
        />
        <IrrigationSchematic t={{ detectAt: 60, openAt: 156, closeAt: 312 }} />
      </Shot>

      <Shot name="C1 · Irigasi tetes" from={SHOTS.drip.from} durationInFrames={SHOTS.drip.duration} fadeIn={XF}>
        <CinematicPhoto
          src={drip.src}
          width={drip.width}
          height={drip.height}
          durationInFrames={SHOTS.drip.duration}
          grade="golden"
          camera={{ from: { x: 50, y: 52, zoom: 1.05 }, to: { x: 54, y: 60, zoom: 1.22 } }}
          parallax={{ horizon: 40, depth: 1.4, feather: 18 }}
          seed={22}
        />
        <FloatingParticles seed="drip" count={26} opacity={0.35} />
        <LocationTag place="Irigasi tetes" region="Kerala, India" delay={10} hold={120} />
      </Shot>

      <Shot name="C2 · Penetes" from={SHOTS.emitter.from} durationInFrames={SHOTS.emitter.duration} fadeIn={XF} focusPull>
        <CinematicPhoto
          src={emitter.src}
          width={emitter.width}
          height={emitter.height}
          durationInFrames={SHOTS.emitter.duration}
          grade="natural"
          camera={{ from: { x: 40, y: 40, zoom: 1.02 }, to: { x: 42, y: 42, zoom: 1.1 } }}
          shake={0.8}
          seed={23}
          renderOverlay={(project) => {
            const tip = project(38, 38);
            return <Callout {...tip} dx={-200} dy={-60} label="Penetes (emitter)" sub="air keluar setetes demi setetes" delay={26} />;
          }}
        />
      </Shot>
    </AbsoluteFill>
  );
};
