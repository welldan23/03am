import { AbsoluteFill } from 'remotion';
import { FloatingParticles } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { PointList } from '../../../components/PointList';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { status } from '../../../styles/theme';
import { Greenhouse } from '../components/Greenhouse';
import { rel, sec, XF } from './common';

/** M6 · 03:45–04:35 — Contoh 2: greenhouse & hidroponik (iklim mikro + nutrisi otomatis). */
const SH = {
  intro: { from: 0, d: sec(8) },
  gh: { from: sec(7.5), d: sec(30.5) },
  result: { from: sec(37.5), d: sec(12.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const M06Greenhouse: React.FC<SceneProps> = ({ scene }) => {
  const farmer = photo('hydroponicFarmer');
  const gh = photo('greenhouseWide');
  const rows = photo('hydroponicRows');
  const B = SH.gh.from / 24;
  const C = SH.result.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Hidroponik" from={SH.intro.from} durationInFrames={SH.intro.d}>
        <CinematicPhoto src={farmer.src} width={farmer.width} height={farmer.height} durationInFrames={SH.intro.d} grade="natural" camera={{ from: { x: 50, y: 50, zoom: 1.04 }, to: { x: 52, y: 44, zoom: 1.18 } }} seed={61} />
        <FloatingParticles seed="m-hydro" count={20} opacity={0.3} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={140} />
      </Shot>
      <Shot name="B · Greenhouse" from={SH.gh.from} durationInFrames={SH.gh.d} fadeIn={XF}>
        <Backdrop src={gh.src} width={gh.width} height={gh.height} durationInFrames={SH.gh.d} camera={{ from: { x: 45, y: 50, zoom: 1.1 }, to: { x: 55, y: 52, zoom: 1.2 }, easing: LINEAR_DRIFT }} dim={0.72} />
        <Greenhouse
          t={{
            fanOn: rel(13.75, B),
            fanOff: rel(21.0, B),
            mistOff: rel(19.5, B),
            ecLowAt: rel(24.0, B),
            doseOn: rel(29.5, B),
            doseOff: rel(34.0, B),
          }}
        />
      </Shot>
      <Shot name="C · Hasil" from={SH.result.from} durationInFrames={SH.result.d} fadeIn={XF} focusPull>
        <CinematicPhoto src={rows.src} width={rows.width} height={rows.height} durationInFrames={SH.result.d} grade="lush" camera={{ from: { x: 40, y: 55, zoom: 1.12 }, to: { x: 30, y: 55, zoom: 1.16 }, easing: LINEAR_DRIFT }} seed={62} />
        <PointList
          heading="HASILNYA"
          accent={status.good}
          durationInFrames={SH.result.d}
          points={[
            { icon: 'phone', title: 'Dipantau dari ponsel', desc: 'meski jauh dari kebun', at: rel(38.25, C) },
            { icon: 'leaf', title: 'Tanaman tumbuh seragam', desc: 'iklim mikro selalu terjaga', at: rel(41.25, C) },
            { icon: 'drop', title: 'Nutrisi tidak terbuang', desc: 'dosis A/B sesuai kebutuhan', at: rel(43.5, C) },
          ]}
        />
      </Shot>
    </AbsoluteFill>
  );
};
