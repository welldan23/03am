import { AbsoluteFill } from 'remotion';
import { FloatingParticles, SunGlow } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { LocationTag } from '../../../components/LocationTag';
import { Shot } from '../../../components/Shot';
import { Callout, ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { CattleCollarPanel, PondMonitor } from '../components/Livestock';
import { rel, sec, XF } from './common';

/** M7 · 04:35–05:25 — Contoh 3: kalung sensor sapi & tambak udang (oksigen, kincir, pakan). */
const SH = {
  barn: { from: 0, d: sec(6.5) },
  cow: { from: sec(6), d: sec(16) },
  pond: { from: sec(21.5), d: sec(6.5) },
  monitor: { from: sec(27.5), d: sec(22.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const M07Livestock: React.FC<SceneProps> = ({ scene }) => {
  const barn = photo('mCattleBarn');
  const cow = photo('mCattlePasture');
  const pond = photo('mShrimpPond');
  const juwana = photo('mFishpondJuwana');
  const B = SH.cow.from / 24;
  const D = SH.monitor.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Kandang" from={SH.barn.from} durationInFrames={SH.barn.d}>
        <CinematicPhoto src={barn.src} width={barn.width} height={barn.height} durationInFrames={SH.barn.d} grade="golden" camera={{ from: { x: 40, y: 55, zoom: 1.06 }, to: { x: 34, y: 58, zoom: 1.18 } }} seed={71} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={8} hold={120} />
      </Shot>
      <Shot name="B · Kalung sensor" from={SH.cow.from} durationInFrames={SH.cow.d} fadeIn={XF}>
        <CinematicPhoto
          src={cow.src}
          width={cow.width}
          height={cow.height}
          durationInFrames={SH.cow.d}
          grade="lush"
          camera={{ from: { x: 58, y: 52, zoom: 1.05 }, to: { x: 57, y: 53, zoom: 1.14 }, easing: LINEAR_DRIFT }}
          shake={0.8}
          seed={72}
          renderOverlay={(project) => <Callout {...project(42, 54)} dx={-120} dy={190} label="Kalung sensor" sub="GPS · sensor gerak · suhu" delay={rel(6.75, B)} />}
        />
        <SunGlow origin="10% 0%" strength={0.24} />
        <CattleCollarPanel alertAt={rel(11.75, B)} />
      </Shot>
      <Shot name="C · Tambak" from={SH.pond.from} durationInFrames={SH.pond.d} fadeIn={XF}>
        <CinematicPhoto src={pond.src} width={pond.width} height={pond.height} durationInFrames={SH.pond.d} grade="natural" camera={{ from: { x: 50, y: 55, zoom: 1.04 }, to: { x: 55, y: 58, zoom: 1.16 } }} seed={73} />
        <FloatingParticles seed="m-pond" count={20} opacity={0.25} />
        <LocationTag place="Tambak udang" region="Padang Pariaman, Sumatera Barat" delay={8} hold={120} />
      </Shot>
      <Shot name="D · Monitor tambak" from={SH.monitor.from} durationInFrames={SH.monitor.d} fadeIn={XF}>
        <Backdrop src={juwana.src} width={juwana.width} height={juwana.height} durationInFrames={SH.monitor.d} camera={{ from: { x: 45, y: 50, zoom: 1.1 }, to: { x: 55, y: 52, zoom: 1.2 }, easing: LINEAR_DRIFT }} dim={0.72} />
        <PondMonitor t={{ sensorAt: rel(33.25, D), aeratorAt: rel(38.75, D), feederAt: rel(44.25, D) }} />
      </Shot>
    </AbsoluteFill>
  );
};
