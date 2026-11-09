import { AbsoluteFill } from 'remotion';
import { Backdrop } from '../../../components/Backdrop';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { ConnectivityCompare, LayerStack } from '../components/ConceptDiagrams';
import { rel, sec, XF } from './common';

/** M3 · 01:20–02:05 — 4 lapisan arsitektur, lalu perbandingan jaringan. */
const SH = {
  layers: { from: 0, d: sec(25) },
  nets: { from: sec(24.5), d: sec(20.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const M03Architecture: React.FC<SceneProps> = ({ scene }) => {
  const terr = photo('jatiluwihWide');
  const aerial = photo('baliAerial');
  const B = SH.nets.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Lapisan" from={SH.layers.from} durationInFrames={SH.layers.d}>
        <Backdrop src={terr.src} width={terr.width} height={terr.height} durationInFrames={SH.layers.d} camera={{ from: { x: 40, y: 50, zoom: 1.15 }, to: { x: 52, y: 52, zoom: 1.25 }, easing: LINEAR_DRIFT }} dim={0.66} />
        <LayerStack at={[rel(6.25, 0), rel(11.25, 0), rel(15.75, 0), rel(20.75, 0)]} flowAt={rel(21.75, 0)} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={110} />
      </Shot>
      <Shot name="B · Jaringan" from={SH.nets.from} durationInFrames={SH.nets.d} fadeIn={XF}>
        <Backdrop src={aerial.src} width={aerial.width} height={aerial.height} durationInFrames={SH.nets.d} camera={{ from: { x: 45, y: 50, zoom: 1.12 }, to: { x: 55, y: 54, zoom: 1.2 }, easing: LINEAR_DRIFT }} dim={0.7} />
        <ConnectivityCompare
          appearAt={rel(25.25, B)}
          focus={[
            [rel(31.25, B), [0]],
            [rel(36.5, B), [1, 2]],
            [rel(41, B), [3]],
          ]}
        />
      </Shot>
    </AbsoluteFill>
  );
};
