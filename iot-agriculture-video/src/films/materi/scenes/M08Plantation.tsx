import { AbsoluteFill } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { DroneSurveyHUD } from '../../../components/DroneGraphics';
import { IoTNetwork, type NetworkLink, type NetworkNode } from '../../../components/IoTNetwork';
import { LocationTag } from '../../../components/LocationTag';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { DiseaseRisk } from '../components/Plantation';
import { rel, sec, XF } from './common';

/** M8 · 05:25–06:10 — Contoh 4: kebun teh (cuaca → risiko jamur), drone, kebun cabai. */
const SH = {
  intro: { from: 0, d: sec(9) },
  risk: { from: sec(8.5), d: sec(15.5) },
  drone: { from: sec(23.5), d: sec(12.5) },
  chili: { from: sec(35.5), d: sec(9.5) + SCENE_TRANSITION_FRAMES },
} as const;

const CHILI_NODES = [
  { id: 'a', x: 18, y: 78, label: 'TANAH-01' },
  { id: 'b', x: 38, y: 70 },
  { id: 'c', x: 55, y: 82, label: 'TANAH-02' },
  { id: 'd', x: 72, y: 72 },
  { id: 'e', x: 88, y: 80, label: 'CUACA' },
];
const CHILI_LINKS: NetworkLink[] = CHILI_NODES.slice(1).map((n, i) => ({ from: CHILI_NODES[i]?.id ?? 'a', to: n.id, at: 40 + i * 10 }));

export const M08Plantation: React.FC<SceneProps> = ({ scene }) => {
  const mountain = photo('mTeaMountain');
  const sidamanik = photo('mTeaSidamanik');
  const wonosari = photo('mTeaWonosari');
  const chili = photo('mChiliField');
  const B = SH.risk.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Kebun teh" from={SH.intro.from} durationInFrames={SH.intro.d}>
        <CinematicPhoto src={mountain.src} width={mountain.width} height={mountain.height} durationInFrames={SH.intro.d} grade="lush" camera={{ from: { x: 45, y: 55, zoom: 1.04 }, to: { x: 52, y: 58, zoom: 1.16 }, easing: LINEAR_DRIFT }} parallax={{ horizon: 50, depth: 1.4 }} seed={81} />
        <Mist bands={[40, 55]} intensity={0.16} speed={0.4} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={110} />
        <LocationTag place="Kebun teh Danau Kembar" region="Solok, Sumatera Barat" delay={140} hold={70} />
      </Shot>
      <Shot name="B · Risiko jamur" from={SH.risk.from} durationInFrames={SH.risk.d} fadeIn={XF}>
        <Backdrop src={sidamanik.src} width={sidamanik.width} height={sidamanik.height} durationInFrames={SH.risk.d} camera={{ from: { x: 45, y: 55, zoom: 1.1 }, to: { x: 55, y: 55, zoom: 1.2 }, easing: LINEAR_DRIFT }} dim={0.66} />
        <DiseaseRisk highAt={rel(16.75, B)} alertAt={rel(22.25, B)} />
      </Shot>
      <Shot name="C · Drone" from={SH.drone.from} durationInFrames={SH.drone.d} fadeIn={XF}>
        <CinematicPhoto src={wonosari.src} width={wonosari.width} height={wonosari.height} durationInFrames={SH.drone.d} grade="natural" camera={{ from: { x: 50, y: 55, zoom: 1.12 }, to: { x: 54, y: 58, zoom: 1.18 }, easing: LINEAR_DRIFT }} shake={1.6} seed={82} />
        <DroneSurveyHUD start={20} duration={250} />
      </Shot>
      <Shot name="D · Kebun cabai" from={SH.chili.from} durationInFrames={SH.chili.d} fadeIn={XF} focusPull>
        <CinematicPhoto
          src={chili.src}
          width={chili.width}
          height={chili.height}
          durationInFrames={SH.chili.d}
          grade="golden"
          camera={{ from: { x: 45, y: 60, zoom: 1.06 }, to: { x: 52, y: 62, zoom: 1.16 } }}
          seed={83}
          renderOverlay={(project) => {
            const nodes: NetworkNode[] = CHILI_NODES.map((n, i) => ({ ...project(n.x, n.y), id: n.id, at: 20 + i * 8, label: n.label }));
            return <IoTNetwork nodes={nodes} links={CHILI_LINKS} opacity={0.85} />;
          }}
        />
        <SunGlow origin="85% 0%" strength={0.24} />
        <FloatingParticles seed="m-chili" count={26} opacity={0.3} />
      </Shot>
    </AbsoluteFill>
  );
};
