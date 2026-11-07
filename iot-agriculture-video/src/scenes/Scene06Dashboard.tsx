import { AbsoluteFill, Sequence } from 'remotion';
import { Backdrop } from '../components/Backdrop';
import { FarmDashboard, type DashCam } from '../components/FarmDashboard';
import { ChapterTitle } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import type { SceneProps } from './types';

/**
 * SCENE 6 · 03:10–03:50 — Dasbor pertanian cerdas.
 * Satu kanvas dasbor yang "difilmkan": ikhtisar → grafik kelembapan → peta &
 * peringatan → pemakaian air & prakiraan → kembali ke ikhtisar.
 */
const DASH_START = sec(3.5);

const CAMERA: readonly DashCam[] = [
  { at: DASH_START, cx: 960, cy: 560, zoom: 0.84 },
  { at: sec(9), cx: 960, cy: 545, zoom: 0.88 },
  { at: sec(11.5), cx: 530, cy: 545, zoom: 1.42 },
  { at: sec(16.5), cx: 560, cy: 545, zoom: 1.46 },
  { at: sec(18.5), cx: 1370, cy: 545, zoom: 1.38 },
  { at: sec(27), cx: 1390, cy: 545, zoom: 1.42 },
  { at: sec(29), cx: 960, cy: 905, zoom: 1.3 },
  { at: sec(34), cx: 990, cy: 905, zoom: 1.32 },
  { at: sec(36.5), cx: 960, cy: 560, zoom: 0.86 },
];

export const Scene06Dashboard: React.FC<SceneProps> = ({ scene }) => {
  const aerial = photo('baliAerial');
  const total = scene.durationInFrames + SCENE_TRANSITION_FRAMES;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Backdrop
        src={aerial.src}
        width={aerial.width}
        height={aerial.height}
        durationInFrames={total}
        camera={{ from: { x: 45, y: 50, zoom: 1.1 }, to: { x: 58, y: 54, zoom: 1.25 }, easing: LINEAR_DRIFT }}
        blur={22}
        dim={0.72}
      />
      <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={70} />
      {/* Dasbor mulai tersusun setelah judul bab keluar; waktu kamera tetap ditulis dalam waktu scene. */}
      <Sequence from={DASH_START} layout="none">
        <FarmDashboard camera={CAMERA.map((k) => ({ ...k, at: Math.max(0, k.at - DASH_START) }))} alertsAt={sec(23.5) - DASH_START} />
      </Sequence>
    </AbsoluteFill>
  );
};
