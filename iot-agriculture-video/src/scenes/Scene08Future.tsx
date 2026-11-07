import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from 'remotion';
import { FloatingParticles, Mist, SunGlow } from '../components/Atmosphere';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { EndCredits } from '../components/EndCredits';
import { Shot } from '../components/Shot';
import { ChapterTitle, easeOut } from '../components/ui';
import { photo } from '../data/assets';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import { colors, fonts } from '../styles/theme';
import type { SceneProps } from './types';

/**
 * SCENE 8 · 04:30–05:00 — Masa depan pertanian cerdas (scene terakhir, tanpa overhang).
 *  A  0–7s      Petani hidroponik
 *  B  6.5–12.5s Deretan pakcoy hidroponik
 *  C  12–20.5s  Petani & gunung saat fajar + pesan penutup
 *  D  20–30s    Kredit penutup → hitam
 */
const XF = 12;
const SHOTS = {
  hydro: { from: 0, duration: sec(7) },
  rows: { from: sec(6.5), duration: sec(6) },
  dawn: { from: sec(12), duration: sec(8.5) },
  credits: { from: sec(20), duration: sec(10) },
} as const;

const ClosingLines: React.FC = () => {
  const frame = useCurrentFrame();
  const l1 = interpolate(frame, [20, 50], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
  const l2 = interpolate(frame, [70, 104], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', fontFamily: fonts.sans, color: colors.paper, textAlign: 'center' }}>
      <div style={{ opacity: l1, transform: `translateY(${(1 - l1) * 14}px)`, filter: `blur(${(1 - l1) * 6}px)`, fontSize: 64, fontWeight: 700, textShadow: '0 4px 40px rgba(0,0,0,0.6)' }}>
        Teknologi tidak menggantikan petani.
      </div>
      <div style={{ opacity: l2, transform: `translateY(${(1 - l2) * 14}px)`, filter: `blur(${(1 - l2) * 6}px)`, fontSize: 40, fontWeight: 400, marginTop: 26, color: colors.paper, textShadow: '0 4px 30px rgba(0,0,0,0.6)' }}>
        Ia membantu mereka membaca alam dengan lebih baik.
      </div>
    </AbsoluteFill>
  );
};

export const Scene08Future: React.FC<SceneProps> = ({ scene }) => {
  const hydro = photo('hydroponicFarmer');
  const rows = photo('hydroponicRows');
  const dawn = photo('farmerMountainDawn');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Hidroponik" from={SHOTS.hydro.from} durationInFrames={SHOTS.hydro.duration}>
        <CinematicPhoto
          src={hydro.src}
          width={hydro.width}
          height={hydro.height}
          durationInFrames={SHOTS.hydro.duration}
          grade="natural"
          camera={{ from: { x: 50, y: 50, zoom: 1.04 }, to: { x: 52, y: 42, zoom: 1.2 } }}
          seed={51}
        />
        <FloatingParticles seed="hydro" count={24} opacity={0.3} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={110} />
      </Shot>
      <Shot name="B · Deretan pakcoy" from={SHOTS.rows.from} durationInFrames={SHOTS.rows.duration} fadeIn={XF}>
        <CinematicPhoto
          src={rows.src}
          width={rows.width}
          height={rows.height}
          durationInFrames={SHOTS.rows.duration}
          grade="lush"
          camera={{ from: { x: 40, y: 55, zoom: 1.12 }, to: { x: 60, y: 55, zoom: 1.16 }, easing: LINEAR_DRIFT }}
          parallax={{ horizon: 45, depth: 1.4, feather: 18 }}
          seed={52}
        />
      </Shot>
      <Shot name="C · Fajar & pesan" from={SHOTS.dawn.from} durationInFrames={SHOTS.dawn.duration} fadeIn={18} focusPull>
        <CinematicPhoto
          src={dawn.src}
          width={dawn.width}
          height={dawn.height}
          durationInFrames={SHOTS.dawn.duration}
          grade="dawn"
          camera={{ from: { x: 50, y: 45, zoom: 1.0 }, to: { x: 54, y: 42, zoom: 1.12 } }}
          parallax={{ horizon: 58, depth: 1.5, feather: 14 }}
          seed={53}
        />
        <SunGlow origin="30% 30%" strength={0.35} />
        <Mist bands={[58, 70]} intensity={0.18} speed={0.35} />
        <AbsoluteFill style={{ backgroundColor: 'rgba(0,0,0,0.25)' }} />
        <ClosingLines />
      </Shot>
      <Sequence name="D · Kredit" from={SHOTS.credits.from} durationInFrames={SHOTS.credits.duration}>
        <EndCredits durationInFrames={SHOTS.credits.duration} />
      </Sequence>
    </AbsoluteFill>
  );
};
