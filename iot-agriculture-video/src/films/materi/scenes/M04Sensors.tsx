import { AbsoluteFill } from 'remotion';
import { FloatingParticles } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { SensorGallery } from '../components/SensorGallery';
import { rel, sec, XF } from './common';

/** M4 · 02:05–02:50 — Galeri 8 jenis sensor (bergiliran mengikuti subtitle). */
const SH = {
  probe: { from: 0, d: sec(8) },
  gallery: { from: sec(7.5), d: sec(37.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const M04Sensors: React.FC<SceneProps> = ({ scene }) => {
  const probe = photo('soilProbe');
  const cracked = photo('crackedSoilTop');
  const B = SH.gallery.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Probe" from={SH.probe.from} durationInFrames={SH.probe.d}>
        <CinematicPhoto src={probe.src} width={probe.width} height={probe.height} durationInFrames={SH.probe.d} grade="lush" camera={{ from: { x: 34, y: 50, zoom: 1.06 }, to: { x: 38, y: 46, zoom: 1.22 } }} seed={12} />
        <FloatingParticles seed="m-probe" count={20} opacity={0.3} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={140} />
      </Shot>
      <Shot name="B · Galeri sensor" from={SH.gallery.from} durationInFrames={SH.gallery.d} fadeIn={XF}>
        <Backdrop src={cracked.src} width={cracked.width} height={cracked.height} durationInFrames={SH.gallery.d} camera={{ from: { x: 50, y: 50, zoom: 1.1 }, to: { x: 54, y: 50, zoom: 1.2 }, easing: LINEAR_DRIFT }} blur={20} dim={0.72} />
        <SensorGallery activeAt={Array.from({ length: 8 }, (_, i) => rel(8.0 + 4.6 * i, B))} />
      </Shot>
    </AbsoluteFill>
  );
};
