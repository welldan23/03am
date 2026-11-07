import { AbsoluteFill } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../components/Atmosphere';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { CropHealthMap, DroneSurveyHUD } from '../components/DroneGraphics';
import { LocationTag } from '../components/LocationTag';
import { Shot } from '../components/Shot';
import { ChapterTitle } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import type { SceneProps } from './types';

/**
 * SCENE 5 · 02:30–03:10 — Drone pertanian.
 *  A  0–8s     Drone menyemprot sawah
 *  B  7.5–20s  Sawah Bali dari udara + HUD survei (rute zig-zag, telemetri)
 *  C  19.5–32s Petak sawah dari atas + peta kesehatan tanaman
 *  D  31.5–40s Drone bekerja di sawah
 */
const XF = 12;
const SHOTS = {
  spray: { from: 0, duration: sec(8) },
  survey: { from: sec(7.5), duration: sec(12.5) },
  health: { from: sec(19.5), duration: sec(12.5) },
  field: { from: sec(31.5), duration: sec(8.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const Scene05Drones: React.FC<SceneProps> = ({ scene }) => {
  const spray = photo('droneSprayPaddy');
  const aerial = photo('baliAerial');
  const topDown = photo('paddyTopDown');
  const droneField = photo('droneRiceField');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Drone menyemprot" from={SHOTS.spray.from} durationInFrames={SHOTS.spray.duration}>
        <CinematicPhoto
          src={spray.src}
          width={spray.width}
          height={spray.height}
          durationInFrames={SHOTS.spray.duration}
          grade="lush"
          camera={{ from: { x: 40, y: 52, zoom: 1.04 }, to: { x: 42, y: 50, zoom: 1.22 } }}
          parallax={{ horizon: 50, depth: 1.6, feather: 16 }}
          seed={31}
        />
        <Mist bands={[52, 62]} intensity={0.16} speed={0.9} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={110} />
      </Shot>

      <Shot name="B · Survei udara" from={SHOTS.survey.from} durationInFrames={SHOTS.survey.duration} fadeIn={XF}>
        <CinematicPhoto
          src={aerial.src}
          width={aerial.width}
          height={aerial.height}
          durationInFrames={SHOTS.survey.duration}
          grade="natural"
          camera={{ from: { x: 50, y: 50, zoom: 1.12 }, to: { x: 54, y: 56, zoom: 1.18 }, easing: LINEAR_DRIFT }}
          shake={1.8}
          seed={32}
        />
        <DroneSurveyHUD start={24} duration={250} />
      </Shot>

      <Shot name="C · Peta kesehatan" from={SHOTS.health.from} durationInFrames={SHOTS.health.duration} fadeIn={XF}>
        <CinematicPhoto
          src={topDown.src}
          width={topDown.width}
          height={topDown.height}
          durationInFrames={SHOTS.health.duration}
          grade="natural"
          camera={{ from: { x: 50, y: 50, zoom: 1.04 }, to: { x: 52, y: 50, zoom: 1.1 }, easing: LINEAR_DRIFT }}
          shake={0.6}
          seed={33}
        />
        <CropHealthMap sweepFrom={20} calloutAt={160} />
      </Shot>

      <Shot name="D · Drone di sawah" from={SHOTS.field.from} durationInFrames={SHOTS.field.duration} fadeIn={XF} focusPull>
        <CinematicPhoto
          src={droneField.src}
          width={droneField.width}
          height={droneField.height}
          durationInFrames={SHOTS.field.duration}
          grade="golden"
          camera={{ from: { x: 55, y: 45, zoom: 1.1 }, to: { x: 50, y: 48, zoom: 1.24 } }}
          parallax={{ horizon: 42, depth: 1.5, feather: 16 }}
          seed={34}
        />
        <SunGlow origin="20% 0%" strength={0.26} />
        <FloatingParticles seed="dronefield" count={30} opacity={0.35} />
        <LocationTag place="Drone di sawah padi" region="Aomori, Jepang" delay={14} hold={110} />
      </Shot>
    </AbsoluteFill>
  );
};
