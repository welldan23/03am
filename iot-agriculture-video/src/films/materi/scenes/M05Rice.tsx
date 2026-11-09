import { AbsoluteFill, Sequence } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../../../components/Atmosphere';
import { Backdrop } from '../../../components/Backdrop';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { LocationTag } from '../../../components/LocationTag';
import { PointList } from '../../../components/PointList';
import { Shot } from '../../../components/Shot';
import { ChapterTitle } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../../../data/video';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { status } from '../../../styles/theme';
import { AwdPaddy } from '../components/AwdPaddy';
import { rel, sec, XF } from './common';

/** M5 · 02:50–03:45 — Contoh 1: sawah padi hemat air dengan AWD + sensor pipa. */
const SH = {
  intro: { from: 0, d: sec(9) },
  awd: { from: sec(8.5), d: sec(31.5) },
  result: { from: sec(39.5), d: sec(15.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const M05Rice: React.FC<SceneProps> = ({ scene }) => {
  const terr = photo('tegallalang');
  const stream = photo('subakStream');
  const canal = photo('subakCanalFall');
  const B = SH.awd.from / 24;
  const C = SH.result.from / 24;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Sawah" from={SH.intro.from} durationInFrames={SH.intro.d}>
        <CinematicPhoto src={terr.src} width={terr.width} height={terr.height} durationInFrames={SH.intro.d} grade="lush" camera={{ from: { x: 52, y: 60, zoom: 1.1 }, to: { x: 56, y: 66, zoom: 1.24 } }} seed={51} />
        <Mist bands={[60, 76]} intensity={0.12} speed={0.5} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={150} />
      </Shot>
      <Shot name="B · AWD" from={SH.awd.from} durationInFrames={SH.awd.d} fadeIn={XF}>
        <Backdrop src={stream.src} width={stream.width} height={stream.height} durationInFrames={SH.awd.d} camera={{ from: { x: 50, y: 55, zoom: 1.1 }, to: { x: 56, y: 55, zoom: 1.2 }, easing: LINEAR_DRIFT }} dim={0.7} />
        <AwdPaddy
          t={{
            pipeAt: rel(15.25, B),
            sensorAt: rel(20.75, B),
            dryFrom: rel(21.0, B),
            thresholdAt: rel(26.25, B),
            gateAt: rel(31.75, B),
            refilledAt: rel(35.0, B),
            savingAt: rel(36.75, B),
          }}
        />
      </Shot>
      <Shot name="C · Hasil" from={SH.result.from} durationInFrames={SH.result.d} fadeIn={XF} focusPull>
        <CinematicPhoto src={canal.src} width={canal.width} height={canal.height} durationInFrames={SH.result.d} grade="lush" camera={{ from: { x: 44, y: 62, zoom: 1.06 }, to: { x: 40, y: 66, zoom: 1.2 } }} seed={52} />
        <SunGlow origin="80% 0%" strength={0.24} />
        <FloatingParticles seed="m-canal" count={24} opacity={0.3} />
        <LocationTag place="Subak Aya" region="Babahan, Tabanan, Bali" delay={10} hold={130} />
        <Sequence from={0} layout="none">
          <PointList
            heading="HASILNYA"
            accent={status.good}
            durationInFrames={SH.result.d}
            points={[
              { icon: 'drop', title: 'Air irigasi lebih hemat', desc: 'menurut IRRI hingga sekitar 30%', at: rel(40, C) },
              { icon: 'leaf', title: 'Panen tetap terjaga', desc: 'dengan ambang aman −15 cm', at: rel(42.25, C) },
              { icon: 'cloud', title: 'Emisi metana berkurang', desc: 'sawah tidak terus tergenang', at: rel(44.5, C) },
              { icon: 'phone', title: 'Dipantau dari rumah', desc: 'tak perlu bolak-balik ke sawah', at: rel(47.75, C) },
            ]}
          />
        </Sequence>
      </Shot>
    </AbsoluteFill>
  );
};
