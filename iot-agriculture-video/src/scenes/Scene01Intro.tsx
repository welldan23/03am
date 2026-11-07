import { AbsoluteFill, Sequence } from 'remotion';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { FloatingParticles, Mist, SunGlow } from '../components/Atmosphere';
import { IoTNetwork, type NetworkLink, type NetworkNode } from '../components/IoTNetwork';
import { LocationTag } from '../components/LocationTag';
import { Shot } from '../components/Shot';
import { StatCallout } from '../components/StatCallout';
import { TitleSequence } from '../components/TitleSequence';
import { photo } from '../data/assets';
import { FACTS } from '../data/facts';
import { SCENE_TRANSITION_FRAMES, VIDEO_SUBTITLE, VIDEO_TITLE } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import type { SceneProps } from './types';

/**
 * SCENE 1 · 00:00–00:30 — Pengantar sinematik pertanian Indonesia.
 *
 *  A  00:00–00:05.5  Fajar di sawah (push-in pelan, kabut berlapis)
 *  B  00:05–00:11.5  Jatiluwih, Bali (pan lateral + parallax terasering)
 *  C  00:11–00:17    Tegallalang, Bali (tilt-down + push-in)
 *  D  00:16.5–00:22.5 Petani panen, Jawa Tengah (push-in ke subjek)
 *  E  00:22–00:30    Sekuens judul di atas panorama Jatiluwih + teaser jaringan IoT
 *
 * Setiap shot tumpang-tindih 12 frame untuk crossfade lembut.
 */

const XF = 12; // panjang crossfade antar-shot

const SHOTS = {
  dawn: { from: 0, duration: sec(5.5) },
  jatiluwih: { from: sec(5), duration: sec(6.5) },
  tegallalang: { from: sec(11), duration: sec(6) },
  farmer: { from: sec(16.5), duration: sec(6) },
  title: { from: sec(22), duration: sec(8) + SCENE_TRANSITION_FRAMES },
} as const;

// Titik-titik sensor di terasering panorama (koordinat persen gambar).
const TEASER_NODES: ReadonlyArray<{ id: string; x: number; y: number; at: number; label?: string }> = [
  { id: 'n1', x: 34, y: 84, at: 92, label: 'TANAH-01' },
  { id: 'n2', x: 42, y: 76, at: 100 },
  { id: 'n3', x: 50, y: 88, at: 106, label: 'AIR-02' },
  { id: 'n4', x: 58, y: 78, at: 114 },
  { id: 'n5', x: 66, y: 86, at: 120, label: 'CUACA-03' },
  { id: 'gw', x: 51, y: 70, at: 126 },
];
const TEASER_LINKS: readonly NetworkLink[] = [
  { from: 'n1', to: 'n2', at: 108 },
  { from: 'n2', to: 'gw', at: 116 },
  { from: 'n3', to: 'gw', at: 122 },
  { from: 'n4', to: 'gw', at: 128 },
  { from: 'n5', to: 'n4', at: 134 },
];

export const Scene01Intro: React.FC<SceneProps> = () => {
  const dawn = photo('dawnPaddy');
  const jatiluwih = photo('jatiluwihWide');
  const tegallalang = photo('tegallalang');
  const farmer = photo('farmerHarvest');
  const panorama = photo('jatiluwihPanorama');

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {/* A — Fajar */}
      <Shot name="A · Fajar" from={SHOTS.dawn.from} durationInFrames={SHOTS.dawn.duration}>
        <CinematicPhoto
          src={dawn.src}
          width={dawn.width}
          height={dawn.height}
          durationInFrames={SHOTS.dawn.duration}
          grade="dawn"
          camera={{ from: { x: 46, y: 56, zoom: 1.02 }, to: { x: 50, y: 60, zoom: 1.13 } }}
          parallax={{ horizon: 63, depth: 1.7, feather: 16 }}
          shake={1.2}
        />
        <SunGlow origin="38% 52%" strength={0.3} />
        <Mist bands={[58, 70, 84]} intensity={0.2} speed={0.4} />
        <FloatingParticles seed="dawn" count={30} opacity={0.35} wind={0.5} />
      </Shot>

      {/* B — Jatiluwih */}
      <Shot name="B · Jatiluwih" from={SHOTS.jatiluwih.from} durationInFrames={SHOTS.jatiluwih.duration} fadeIn={XF}>
        <CinematicPhoto
          src={jatiluwih.src}
          width={jatiluwih.width}
          height={jatiluwih.height}
          durationInFrames={SHOTS.jatiluwih.duration}
          grade="lush"
          camera={{ from: { x: 36, y: 56, zoom: 1.16 }, to: { x: 60, y: 54, zoom: 1.2 }, easing: LINEAR_DRIFT }}
          parallax={{ horizon: 44, depth: 1.45, feather: 18 }}
          seed={2}
        />
        <Mist bands={[34, 46]} intensity={0.12} speed={0.6} />
        <FloatingParticles seed="jati" count={24} opacity={0.3} wind={1.1} />
        <LocationTag place="Jatiluwih" region="Tabanan, Bali" coords="8°22′ LS · 115°08′ BT" delay={16} hold={118} />
        <StatCallout fact={FACTS.riceFieldArea} delay={38} hold={96} align="right" />
      </Shot>

      {/* C — Tegallalang */}
      <Shot name="C · Tegallalang" from={SHOTS.tegallalang.from} durationInFrames={SHOTS.tegallalang.duration} fadeIn={XF}>
        <CinematicPhoto
          src={tegallalang.src}
          width={tegallalang.width}
          height={tegallalang.height}
          durationInFrames={SHOTS.tegallalang.duration}
          grade="lush"
          camera={{ from: { x: 48, y: 34, zoom: 1.08 }, to: { x: 54, y: 56, zoom: 1.24 } }}
          parallax={{ horizon: 40, depth: 1.35, feather: 20 }}
          seed={3}
        />
        <SunGlow origin="10% 0%" strength={0.22} />
        <FloatingParticles seed="tegal" count={28} opacity={0.32} wind={0.8} />
        <LocationTag place="Tegallalang" region="Gianyar, Bali" coords="8°26′ LS · 115°17′ BT" delay={14} hold={104} />
      </Shot>

      {/* D — Petani */}
      <Shot name="D · Petani" from={SHOTS.farmer.from} durationInFrames={SHOTS.farmer.duration} fadeIn={XF}>
        <CinematicPhoto
          src={farmer.src}
          width={farmer.width}
          height={farmer.height}
          durationInFrames={SHOTS.farmer.duration}
          grade="golden"
          camera={{ from: { x: 52, y: 52, zoom: 1.02 }, to: { x: 58, y: 56, zoom: 1.22 } }}
          parallax={{ horizon: 52, depth: 1.5, feather: 14 }}
          seed={4}
        />
        <SunGlow origin="92% 4%" strength={0.32} />
        <FloatingParticles seed="harvest" count={52} opacity={0.5} wind={1.3} />
        <LocationTag place="Desa Tersidilor" region="Jawa Tengah" delay={14} hold={104} />
        <StatCallout fact={FACTS.farmHouseholds} delay={30} hold={92} align="right" />
      </Shot>

      {/* E — Judul */}
      <Shot name="E · Judul" from={SHOTS.title.from} durationInFrames={SHOTS.title.duration} fadeIn={18} focusPull>
        <CinematicPhoto
          src={panorama.src}
          width={panorama.width}
          height={panorama.height}
          durationInFrames={SHOTS.title.duration}
          grade="title"
          camera={{ from: { x: 40, y: 55, zoom: 1.0 }, to: { x: 56, y: 56, zoom: 1.08 }, easing: LINEAR_DRIFT }}
          parallax={{ horizon: 48, depth: 1.4, feather: 18 }}
          shake={0.8}
          seed={5}
          renderOverlay={(project) => {
            const nodes: NetworkNode[] = TEASER_NODES.map((n) => ({ ...project(n.x, n.y), id: n.id, at: n.at, label: n.label }));
            return <IoTNetwork nodes={nodes} links={TEASER_LINKS} opacity={0.8} />;
          }}
        />
        <Mist bands={[52, 66]} intensity={0.1} speed={0.3} />
        <Sequence from={10} layout="none">
          <TitleSequence
            kicker="Sebuah dokumenter edukasi"
            title={VIDEO_TITLE}
            subtitle={VIDEO_SUBTITLE}
            durationInFrames={SHOTS.title.duration - 10}
          />
        </Sequence>
      </Shot>
    </AbsoluteFill>
  );
};
