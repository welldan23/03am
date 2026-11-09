import { AbsoluteFill } from 'remotion';
import { FloatingParticles, SunGlow } from '../../../components/Atmosphere';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { PointList } from '../../../components/PointList';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { colors, status } from '../../../styles/theme';
import { rel, sec, XF } from './common';

/** M10 · 06:55–07:35 — Manfaat, tantangan, dan 4 langkah memulai. Kualitatif, tanpa angka tanpa sumber. */
const SH = {
  benefits: { from: 0, d: sec(14) },
  challenges: { from: sec(13.5), d: sec(13.5) },
  start: { from: sec(26.5), d: sec(13.5) + SCENE_TRANSITION_FRAMES },
} as const;

const Shade: React.FC = () => <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0) 30%, rgba(0,0,0,0.62) 100%)' }} />;

export const M10Start: React.FC<SceneProps> = ({ scene }) => {
  const grain = photo('riceGrainClose');
  const cracked = photo('crackedSoilTop');
  const farmer = photo('farmerTerraceWork');
  const B = SH.challenges.from / 24;
  const C = SH.start.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Manfaat" from={SH.benefits.from} durationInFrames={SH.benefits.d}>
        <CinematicPhoto src={grain.src} width={grain.width} height={grain.height} durationInFrames={SH.benefits.d} grade="golden" camera={{ from: { x: 30, y: 50, zoom: 1.06 }, to: { x: 36, y: 46, zoom: 1.2 } }} shake={1} seed={101} />
        <SunGlow origin="10% 10%" strength={0.3} />
        <FloatingParticles seed="m-grain" count={30} opacity={0.4} />
        <Shade />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={8} hold={90} />
        <PointList
          heading="MANFAAT"
          accent={status.good}
          durationInFrames={SH.benefits.d}
          points={[
            { icon: 'drop', title: 'Air & pupuk lebih hemat', desc: 'diberikan sesuai kebutuhan', at: rel(1.25, 0) },
            { icon: 'alert', title: 'Masalah terdeteksi dini', desc: 'kekeringan, hama, penyakit', at: rel(3.0, 0) },
            { icon: 'chart', title: 'Hasil panen lebih terjaga', desc: 'keputusan berdasarkan data', at: rel(6.25, 0) },
            { icon: 'people', title: 'Kerja lebih efisien', desc: 'pantau lahan dari jarak jauh', at: rel(9.0, 0) },
          ]}
        />
      </Shot>
      <Shot name="B · Tantangan" from={SH.challenges.from} durationInFrames={SH.challenges.d} fadeIn={XF}>
        <CinematicPhoto src={cracked.src} width={cracked.width} height={cracked.height} durationInFrames={SH.challenges.d} grade="natural" camera={{ from: { x: 40, y: 50, zoom: 1.18 }, to: { x: 46, y: 50, zoom: 1.04 }, easing: LINEAR_DRIFT }} shake={0.6} seed={102} />
        <Shade />
        <PointList
          heading="TANTANGAN"
          accent={colors.alert}
          durationInFrames={SH.challenges.d}
          points={[
            { icon: 'coin', title: 'Biaya perangkat', desc: 'investasi awal masih terasa mahal', at: rel(14.25, B) },
            { icon: 'signal', title: 'Sinyal belum merata', desc: 'terutama di desa terpencil', at: rel(19.5, B) },
            { icon: 'people', title: 'Perlu pendampingan', desc: 'pelatihan membaca & memakai data', at: rel(22.0, B) },
          ]}
        />
      </Shot>
      <Shot name="C · Cara memulai" from={SH.start.from} durationInFrames={SH.start.d} fadeIn={XF}>
        <CinematicPhoto src={farmer.src} width={farmer.width} height={farmer.height} durationInFrames={SH.start.d} grade="lush" camera={{ from: { x: 45, y: 45, zoom: 1.04 }, to: { x: 52, y: 42, zoom: 1.2 } }} parallax={{ horizon: 55, depth: 1.5 }} seed={103} />
        <Shade />
        <PointList
          heading="CARA MEMULAI"
          accent={colors.sun}
          durationInFrames={SH.start.d}
          points={[
            { icon: 'target', title: 'Pilih satu masalah utama', desc: 'mis. air, hama, atau pupuk', at: rel(27.5, C) },
            { icon: 'sensor', title: 'Mulai 1–2 sensor sederhana', desc: 'yang langsung menjawab masalah itu', at: rel(32.5, C) },
            { icon: 'people', title: 'Patungan lewat kelompok tani', desc: 'biaya & ilmu ditanggung bersama', at: rel(34.5, C) },
            { icon: 'steps', title: 'Perluas sedikit demi sedikit', desc: 'setelah hasilnya terbukti', at: rel(37.0, C) },
          ]}
        />
      </Shot>
    </AbsoluteFill>
  );
};
