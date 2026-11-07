import { AbsoluteFill, Sequence } from 'remotion';
import { FloatingParticles, SunGlow } from '../components/Atmosphere';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { PointList, type Point } from '../components/PointList';
import { Shot } from '../components/Shot';
import { ChapterTitle } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import { colors, status } from '../styles/theme';
import type { SceneProps } from './types';

/**
 * SCENE 7 · 03:50–04:30 — Manfaat & tantangan.
 *  A1 0–10.5s   Bulir padi        ┐ daftar MANFAAT
 *  A2 10–20.5s  Aliran subak      ┘
 *  B1 20–30.5s  Tanah sawah retak ┐ daftar TANTANGAN
 *  B2 30–40s    Petani terasering ┘
 * Poin-poin sengaja kualitatif — tidak ada angka tanpa sumber.
 */
const XF = 12;
const SHOTS = {
  grain: { from: 0, duration: sec(10.5) },
  stream: { from: sec(10), duration: sec(10.5) },
  cracked: { from: sec(20), duration: sec(10.5) },
  farmer: { from: sec(30), duration: sec(10) + SCENE_TRANSITION_FRAMES },
} as const;

const BENEFITS: readonly Point[] = [
  { icon: 'drop', title: 'Hemat air', desc: 'air dialirkan hanya saat dibutuhkan', at: sec(1.5) },
  { icon: 'leaf', title: 'Pupuk tepat sasaran', desc: 'diberikan di titik yang memerlukan', at: sec(3.5) },
  { icon: 'chart', title: 'Panen lebih terprediksi', desc: 'keputusan berdasarkan data lapangan', at: sec(6.75) },
  { icon: 'alert', title: 'Deteksi dini', desc: 'kekeringan & hama terlihat lebih awal', at: sec(11.5) },
  { icon: 'phone', title: 'Kerja lebih ringan', desc: 'sawah dipantau dari jarak jauh', at: sec(16.75) },
];

const CHALLENGES: readonly Point[] = [
  { icon: 'coin', title: 'Biaya perangkat', desc: 'investasi awal masih terasa mahal', at: sec(1.5) },
  { icon: 'signal', title: 'Sinyal di pedesaan', desc: 'jaringan internet belum merata', at: sec(6.75) },
  { icon: 'people', title: 'Keterampilan digital', desc: 'petani perlu pelatihan & pendampingan', at: sec(12.25) },
  { icon: 'sensor', title: 'Perawatan alat', desc: 'sensor perlu dirawat & dikalibrasi', at: sec(15.5) },
];

const RightShade: React.FC = () => (
  <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0) 30%, rgba(0,0,0,0.6) 100%)' }} />
);

export const Scene07Benefits: React.FC<SceneProps> = ({ scene }) => {
  const grain = photo('riceGrainClose');
  const stream = photo('subakStream');
  const cracked = photo('crackedSoilTop');
  const farmer = photo('farmerTerraceWork');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A1 · Bulir padi" from={SHOTS.grain.from} durationInFrames={SHOTS.grain.duration}>
        <CinematicPhoto
          src={grain.src}
          width={grain.width}
          height={grain.height}
          durationInFrames={SHOTS.grain.duration}
          grade="golden"
          camera={{ from: { x: 30, y: 50, zoom: 1.06 }, to: { x: 36, y: 46, zoom: 1.2 } }}
          shake={1}
          seed={41}
        />
        <SunGlow origin="10% 10%" strength={0.3} />
        <FloatingParticles seed="grain" count={34} opacity={0.4} />
        <RightShade />
      </Shot>
      <Shot name="A2 · Aliran subak" from={SHOTS.stream.from} durationInFrames={SHOTS.stream.duration} fadeIn={XF}>
        <CinematicPhoto
          src={stream.src}
          width={stream.width}
          height={stream.height}
          durationInFrames={SHOTS.stream.duration}
          grade="lush"
          camera={{ from: { x: 40, y: 55, zoom: 1.08 }, to: { x: 34, y: 60, zoom: 1.2 }, easing: LINEAR_DRIFT }}
          parallax={{ horizon: 40, depth: 1.4, feather: 18 }}
          seed={42}
        />
        <RightShade />
      </Shot>
      <Shot name="B1 · Tanah retak" from={SHOTS.cracked.from} durationInFrames={SHOTS.cracked.duration} fadeIn={XF}>
        <CinematicPhoto
          src={cracked.src}
          width={cracked.width}
          height={cracked.height}
          durationInFrames={SHOTS.cracked.duration}
          grade="natural"
          camera={{ from: { x: 40, y: 50, zoom: 1.18 }, to: { x: 46, y: 50, zoom: 1.04 } }}
          shake={0.6}
          seed={43}
        />
        <RightShade />
      </Shot>
      <Shot name="B2 · Petani terasering" from={SHOTS.farmer.from} durationInFrames={SHOTS.farmer.duration} fadeIn={XF}>
        <CinematicPhoto
          src={farmer.src}
          width={farmer.width}
          height={farmer.height}
          durationInFrames={SHOTS.farmer.duration}
          grade="lush"
          camera={{ from: { x: 45, y: 45, zoom: 1.04 }, to: { x: 52, y: 42, zoom: 1.22 } }}
          parallax={{ horizon: 55, depth: 1.5, feather: 16 }}
          seed={44}
        />
        <RightShade />
      </Shot>

      <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={100} />
      <Sequence from={0} durationInFrames={sec(20.25)} layout="none">
        <PointList heading="MANFAAT" accent={status.good} points={BENEFITS} durationInFrames={sec(20.25)} />
      </Sequence>
      <Sequence from={sec(20)} durationInFrames={sec(20) + SCENE_TRANSITION_FRAMES} layout="none">
        <PointList heading="TANTANGAN" accent={colors.alert} points={CHALLENGES} durationInFrames={sec(20) + SCENE_TRANSITION_FRAMES} />
      </Sequence>
    </AbsoluteFill>
  );
};
