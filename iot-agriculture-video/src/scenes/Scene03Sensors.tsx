import { AbsoluteFill } from 'remotion';
import { FloatingParticles, SunGlow } from '../components/Atmosphere';
import { Backdrop } from '../components/Backdrop';
import { CinematicPhoto } from '../components/CinematicPhoto';
import { Icon } from '../components/Icons';
import { Shot } from '../components/Shot';
import { SoilCrossSection } from '../components/SoilCrossSection';
import { Callout, ChapterTitle, IllustrativeTag, Metric, Panel } from '../components/ui';
import { photo } from '../data/assets';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import { LINEAR_DRIFT } from '../lib/camera';
import { sec } from '../lib/time';
import { colors, status } from '../styles/theme';
import type { SceneProps } from './types';

/**
 * SCENE 3 · 01:10–01:50 — Sensor tanah & lingkungan.
 *  A  0–11s    Stasiun sensor bertenaga surya + label bagian-bagiannya
 *  B  10.5–28s Penampang tanah: probe 3 kedalaman, air meresap ke zona akar
 *  C  27.5–40s Probe di tanah + panel data lingkungan
 */
const XF = 12;
const SHOTS = {
  station: { from: 0, duration: sec(11) },
  soil: { from: sec(10.5), duration: sec(17.5) },
  probe: { from: sec(27.5), duration: sec(12.5) + SCENE_TRANSITION_FRAMES },
} as const;

export const Scene03Sensors: React.FC<SceneProps> = ({ scene }) => {
  const mast = photo('solarSensorMast');
  const cracked = photo('crackedSoilTop');
  const probe = photo('soilProbe');
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <Shot name="A · Stasiun sensor" from={SHOTS.station.from} durationInFrames={SHOTS.station.duration}>
        <CinematicPhoto
          src={mast.src}
          width={mast.width}
          height={mast.height}
          durationInFrames={SHOTS.station.duration}
          grade="natural"
          camera={{ from: { x: 46, y: 42, zoom: 1.02 }, to: { x: 47, y: 38, zoom: 1.16 } }}
          parallax={{ horizon: 52, depth: 1.5, feather: 16 }}
          seed={11}
          renderOverlay={(project) => {
            const panelPt = project(43.7, 17);
            const arm = project(53, 26);
            const box = project(44, 60);
            return (
              <>
                <Callout {...panelPt} dx={150} dy={-30} label="Panel surya" sub="daya mandiri di tengah sawah" delay={130} />
                <Callout {...arm} dx={170} dy={70} label="Sensor cuaca" sub="suhu, kelembapan, angin, hujan" delay={150} />
                <Callout {...box} dx={-170} dy={-40} label="Modul pemancar" sub="mengirim data ke gateway" delay={170} />
              </>
            );
          }}
        />
        <SunGlow origin="70% 0%" strength={0.24} />
        <ChapterTitle kicker={scene.kicker} title={scene.title} delay={10} hold={100} />
      </Shot>

      <Shot name="B · Penampang tanah" from={SHOTS.soil.from} durationInFrames={SHOTS.soil.duration} fadeIn={XF}>
        <Backdrop
          src={cracked.src}
          width={cracked.width}
          height={cracked.height}
          durationInFrames={SHOTS.soil.duration}
          camera={{ from: { x: 50, y: 50, zoom: 1.1 }, to: { x: 54, y: 50, zoom: 1.2 }, easing: LINEAR_DRIFT }}
          blur={20}
          dim={0.7}
        />
        <SoilCrossSection wetAt={80} />
      </Shot>

      <Shot name="C · Data lingkungan" from={SHOTS.probe.from} durationInFrames={SHOTS.probe.duration} fadeIn={XF} focusPull>
        <CinematicPhoto
          src={probe.src}
          width={probe.width}
          height={probe.height}
          durationInFrames={SHOTS.probe.duration}
          grade="lush"
          camera={{ from: { x: 30, y: 50, zoom: 1.08 }, to: { x: 38, y: 46, zoom: 1.22 } }}
          seed={12}
        />
        <AbsoluteFill style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0) 35%, rgba(0,0,0,0.55) 100%)' }} />
        <FloatingParticles seed="probe" count={20} opacity={0.3} />
        {[
          { label: 'Suhu tanah', value: 27.4, unit: '°C', dec: 1, icon: 'sun' as const, accent: colors.sun },
          { label: 'pH tanah', value: 6.3, unit: '', dec: 1, icon: 'leaf' as const, accent: status.good },
          { label: 'Kelembapan udara', value: 78, unit: '%', dec: 0, icon: 'drop' as const, accent: colors.water },
        ].map((m, i) => (
          <Panel key={m.label} x={1290} y={150 + i * 205} w={470} h={180} delay={30 + i * 26}>
            <div style={{ display: 'flex', gap: 22, alignItems: 'center' }}>
              <Icon name={m.icon} size={52} color={m.accent} />
              <Metric label={m.label} value={m.value} unit={m.unit} decimals={m.dec} delay={36 + i * 26} accent={m.accent} />
            </div>
          </Panel>
        ))}
        <IllustrativeTag x={1290} y={770} delay={110} />
      </Shot>
    </AbsoluteFill>
  );
};
