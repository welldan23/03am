import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from 'remotion';
import { Mist, SunGlow } from '../../../components/Atmosphere';
import { CinematicPhoto } from '../../../components/CinematicPhoto';
import { EndCredits } from '../../../components/EndCredits';
import { Shot } from '../../../components/Shot';
import { easeOut } from '../../../components/ui';
import { photo } from '../../../data/assets';
import { LINEAR_DRIFT } from '../../../lib/camera';
import type { SceneProps } from '../../../scenes/types';
import { colors, fonts } from '../../../styles/theme';
import { MATERI_FACT_SOURCES, MATERI_SUBTITLE, MATERI_TITLE } from '../timeline';
import { sec, XF } from './common';

/** M11 · 07:35–08:00 — Pesan penutup → ajakan → kredit → hitam. */
const SH = {
  dawn: { from: 0, d: sec(9.5) },
  pano: { from: sec(9), d: sec(6.5) },
  credits: { from: sec(15), d: sec(10) },
} as const;

/** Foto yang dipakai film 8 menit (untuk kredit). */
export const MATERI_PHOTOS = [
  'dawnPaddy', 'jatiluwihWide', 'farmerHarvest', 'crackedSoilTop', 'jatiluwihPanorama', 'baliAerial', 'soilProbe', 'tegallalang',
  'subakStream', 'subakCanalFall', 'hydroponicFarmer', 'greenhouseWide', 'hydroponicRows', 'mCattleBarn', 'mCattlePasture',
  'mShrimpPond', 'mFishpondJuwana', 'mTeaMountain', 'mTeaSidamanik', 'mTeaWonosari', 'mChiliField', 'riceGrainClose',
  'farmerTerraceWork', 'farmerMountainDawn',
] as const;

const Lines: React.FC = () => {
  const f = useCurrentFrame();
  const l1 = interpolate(f, [20, 50], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
  const l2 = interpolate(f, [70, 104], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut });
  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', fontFamily: fonts.sans, color: colors.paper, textAlign: 'center' }}>
      <div style={{ opacity: l1, transform: `translateY(${(1 - l1) * 14}px)`, filter: `blur(${(1 - l1) * 6}px)`, fontSize: 64, fontWeight: 700, textShadow: '0 4px 40px rgba(0,0,0,0.6)' }}>Teknologi tidak menggantikan petani.</div>
      <div style={{ opacity: l2, transform: `translateY(${(1 - l2) * 14}px)`, filter: `blur(${(1 - l2) * 6}px)`, fontSize: 40, marginTop: 26, textShadow: '0 4px 30px rgba(0,0,0,0.6)' }}>
        Ia membantu mereka membaca alam dengan lebih baik.
      </div>
    </AbsoluteFill>
  );
};

export const M11Closing: React.FC<SceneProps> = () => {
  const dawn = photo('farmerMountainDawn');
  const pano = photo('jatiluwihPanorama');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Pesan" from={SH.dawn.from} durationInFrames={SH.dawn.d}>
        <CinematicPhoto src={dawn.src} width={dawn.width} height={dawn.height} durationInFrames={SH.dawn.d} grade="dawn" camera={{ from: { x: 50, y: 45, zoom: 1.0 }, to: { x: 54, y: 42, zoom: 1.12 } }} parallax={{ horizon: 58, depth: 1.5 }} seed={111} />
        <SunGlow origin="30% 30%" strength={0.35} />
        <Mist bands={[58, 70]} intensity={0.18} speed={0.35} />
        <AbsoluteFill style={{ backgroundColor: 'rgba(0,0,0,0.25)' }} />
        <Lines />
      </Shot>
      <Shot name="B · Ajakan" from={SH.pano.from} durationInFrames={SH.pano.d} fadeIn={XF}>
        <CinematicPhoto src={pano.src} width={pano.width} height={pano.height} durationInFrames={SH.pano.d} grade="golden" camera={{ from: { x: 60, y: 55, zoom: 1.0 }, to: { x: 46, y: 56, zoom: 1.06 }, easing: LINEAR_DRIFT }} seed={112} />
      </Shot>
      <Sequence name="C · Kredit" from={SH.credits.from} durationInFrames={SH.credits.d}>
        <EndCredits
          durationInFrames={SH.credits.d}
          photoIds={MATERI_PHOTOS}
          musicIds={['musicChasingDaylight', 'musicAffirmations']}
          title={MATERI_TITLE}
          subtitle={MATERI_SUBTITLE}
          factSources={MATERI_FACT_SOURCES}
        />
      </Sequence>
    </AbsoluteFill>
  );
};
