import { AbsoluteFill, Sequence } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../../../components/Atmosphere';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { IoTNetwork, type NetworkLink, type NetworkNode } from '../../../components/IoTNetwork';
import { LocationTag } from '../../../components/LocationTag';
import { Shot } from '../../../components/Shot';
import { StatCallout } from '../../../components/StatCallout';
import { TitleSequence } from '../../../components/TitleSequence';
import { photo } from '../../../data/assets';
import { FACTS } from '../../../data/facts';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { MATERI_SUBTITLE, MATERI_TITLE } from '../timeline';
import { sec, XF } from './common';

/**
 * M1 · 00:00–00:35 — Pembuka: pertanian Indonesia & tantangannya, lalu judul.
 *  A 0–7 fajar · B 6.5–13 Jatiluwih · C 12.5–19 petani · D 18.5–25 tanah retak · E 24.5–35 judul
 */
const SH = {
  dawn: { from: 0, d: sec(7) },
  terraces: { from: sec(6.5), d: sec(6.5) },
  farmer: { from: sec(12.5), d: sec(6.5) },
  dry: { from: sec(18.5), d: sec(6.5) },
  title: { from: sec(24.5), d: sec(10.5) + SCENE_TRANSITION_FRAMES },
} as const;

const NODES = [
  { id: 'a', x: 30, y: 82, label: 'TANAH' },
  { id: 'b', x: 42, y: 74 },
  { id: 'c', x: 52, y: 86, label: 'AIR' },
  { id: 'd', x: 62, y: 76 },
  { id: 'e', x: 72, y: 84, label: 'CUACA' },
  { id: 'g', x: 51, y: 68 },
];
const LINKS: NetworkLink[] = [
  { from: 'a', to: 'b', at: 130 },
  { from: 'b', to: 'g', at: 138 },
  { from: 'c', to: 'g', at: 144 },
  { from: 'd', to: 'g', at: 150 },
  { from: 'e', to: 'd', at: 156 },
];

export const M01Opening: React.FC<SceneProps> = () => {
  const dawn = photo('dawnPaddy');
  const terr = photo('jatiluwihWide');
  const farmer = photo('farmerHarvest');
  const dry = photo('crackedSoilTop');
  const pano = photo('jatiluwihPanorama');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Fajar" from={SH.dawn.from} durationInFrames={SH.dawn.d}>
        <CinematicPhoto src={dawn.src} width={dawn.width} height={dawn.height} durationInFrames={SH.dawn.d} grade="dawn" camera={{ from: { x: 46, y: 56, zoom: 1.02 }, to: { x: 50, y: 60, zoom: 1.14 } }} parallax={{ horizon: 63, depth: 1.7 }} shake={1.2} />
        <SunGlow origin="38% 52%" strength={0.3} />
        <Mist bands={[58, 70, 84]} intensity={0.2} speed={0.4} />
        <FloatingParticles seed="m-dawn" count={30} opacity={0.35} wind={0.5} />
      </Shot>
      <Shot name="B · Jatiluwih" from={SH.terraces.from} durationInFrames={SH.terraces.d} fadeIn={XF}>
        <CinematicPhoto src={terr.src} width={terr.width} height={terr.height} durationInFrames={SH.terraces.d} grade="lush" camera={{ from: { x: 36, y: 56, zoom: 1.16 }, to: { x: 58, y: 54, zoom: 1.2 }, easing: LINEAR_DRIFT }} parallax={{ horizon: 44, depth: 1.45 }} seed={2} />
        <LocationTag place="Jatiluwih" region="Tabanan, Bali" coords="8°22′ LS · 115°08′ BT" delay={16} hold={120} />
        <StatCallout fact={FACTS.riceFieldArea} delay={34} hold={100} />
      </Shot>
      <Shot name="C · Petani" from={SH.farmer.from} durationInFrames={SH.farmer.d} fadeIn={XF}>
        <CinematicPhoto src={farmer.src} width={farmer.width} height={farmer.height} durationInFrames={SH.farmer.d} grade="golden" camera={{ from: { x: 52, y: 52, zoom: 1.02 }, to: { x: 58, y: 56, zoom: 1.2 } }} parallax={{ horizon: 52, depth: 1.5 }} seed={4} />
        <SunGlow origin="92% 4%" strength={0.3} />
        <FloatingParticles seed="m-harvest" count={46} opacity={0.45} wind={1.3} />
        <LocationTag place="Desa Tersidilor" region="Jawa Tengah" delay={14} hold={110} />
        <StatCallout fact={FACTS.farmHouseholds} delay={30} hold={100} />
      </Shot>
      <Shot name="D · Tanah retak" from={SH.dry.from} durationInFrames={SH.dry.d} fadeIn={XF}>
        <CinematicPhoto src={dry.src} width={dry.width} height={dry.height} durationInFrames={SH.dry.d} grade="golden" camera={{ from: { x: 50, y: 50, zoom: 1.22 }, to: { x: 46, y: 52, zoom: 1.06 } }} shake={0.8} seed={9} />
      </Shot>
      <Shot name="E · Judul" from={SH.title.from} durationInFrames={SH.title.d} fadeIn={18} focusPull>
        <CinematicPhoto
          src={pano.src}
          width={pano.width}
          height={pano.height}
          durationInFrames={SH.title.d}
          grade="title"
          camera={{ from: { x: 40, y: 55, zoom: 1.0 }, to: { x: 57, y: 56, zoom: 1.08 }, easing: LINEAR_DRIFT }}
          shake={0.8}
          seed={5}
          renderOverlay={(project) => {
            const nodes: NetworkNode[] = NODES.map((n, i) => ({ ...project(n.x, n.y), id: n.id, at: 110 + i * 7, label: n.label }));
            return <IoTNetwork nodes={nodes} links={LINKS} opacity={0.8} />;
          }}
        />
        <Mist bands={[52, 66]} intensity={0.1} speed={0.3} />
        <Sequence from={10} layout="none">
          <TitleSequence kicker="Materi edukasi lengkap" title={MATERI_TITLE} subtitle={MATERI_SUBTITLE} durationInFrames={SH.title.d - 10} />
        </Sequence>
      </Shot>
    </AbsoluteFill>
  );
};
