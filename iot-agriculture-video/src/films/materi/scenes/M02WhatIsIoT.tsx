import { AbsoluteFill, random } from 'remotion';
import { Mist } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { IoTNetwork, type NetworkLink, type NetworkNode } from '../../../components/IoTNetwork';
import { Shot } from '../../../components/Shot';
import { ChapterTitle, useProgress } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { colors, fonts } from '../../../styles/theme';
import { FourComponents } from '../components/ConceptDiagrams';
import { rel, sec, XF } from './common';

/** M2 · 00:35–01:20 — Apa itu IoT: definisi + 4 komponen (analogi tubuh). */
const SH = {
  field: { from: 0, d: sec(10) },
  parts: { from: sec(9.5), d: sec(35.5) + SCENE_TRANSITION_FRAMES },
} as const;

const NODES = Array.from({ length: 14 }, (_, i) => ({ id: `f${i}`, x: 14 + (i % 5) * 17 + random(`mf${i}`) * 8, y: 44 + Math.floor(i / 5) * 17 + random(`mg${i}`) * 8, at: 30 + i * 8 }));
const LINKS: NetworkLink[] = NODES.flatMap((n, i) => {
  const l: NetworkLink[] = [];
  if (i % 5 !== 4 && NODES[i + 1]) l.push({ from: n.id, to: `f${i + 1}`, at: n.at + 12 });
  if (NODES[i + 5]) l.push({ from: n.id, to: `f${i + 5}`, at: n.at + 18 });
  return l;
});

const Heading: React.FC<{ at: number }> = ({ at }) => {
  const p = useProgress(at, 20);
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, top: 120, textAlign: 'center', opacity: p, fontFamily: fonts.mono, fontSize: 24, letterSpacing: '0.3em', color: colors.rice }}>
      4 KOMPONEN UTAMA SISTEM IoT
    </div>
  );
};

export const M02WhatIsIoT: React.FC<SceneProps> = ({ scene }) => {
  const aerial = photo('baliAerial');
  const S = SH.parts.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Sawah terhubung" from={SH.field.from} durationInFrames={SH.field.d}>
        <CinematicPhoto
          src={aerial.src}
          width={aerial.width}
          height={aerial.height}
          durationInFrames={SH.field.d}
          grade="lush"
          camera={{ from: { x: 50, y: 55, zoom: 1.04 }, to: { x: 54, y: 60, zoom: 1.2 } }}
          shake={0.8}
          renderOverlay={(project) => {
            const nodes: NetworkNode[] = NODES.map((n) => ({ ...project(n.x, n.y), id: n.id, at: n.at }));
            return <IoTNetwork nodes={nodes} links={LINKS} opacity={0.85} />;
          }}
        />
        <Mist bands={[30, 50]} intensity={0.08} speed={0.5} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={20} hold={150} />
      </Shot>
      <Shot name="B · 4 komponen" from={SH.parts.from} durationInFrames={SH.parts.d} fadeIn={XF}>
        <Backdrop src={aerial.src} width={aerial.width} height={aerial.height} durationInFrames={SH.parts.d} camera={{ from: { x: 56, y: 60, zoom: 1.2 }, to: { x: 62, y: 62, zoom: 1.3 }, easing: LINEAR_DRIFT }} dim={0.66} />
        <Heading at={rel(11.5, S)} />
        <FourComponents at={[rel(16.75, S), rel(22.25, S), rel(27.75, S), rel(33.25, S)]} loopAt={rel(39.25, S)} />
      </Shot>
    </AbsoluteFill>
  );
};
