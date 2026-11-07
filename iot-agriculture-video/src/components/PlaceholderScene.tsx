import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import type { SceneTiming } from '../data/scenes';
import { formatTc } from '../lib/time';
import { colors, fonts } from '../styles/theme';

/**
 * Penanda scene yang BELUM diimplementasikan. Sengaja polos supaya jelas di
 * preview bahwa ini bukan hasil akhir; timeline 7.200 frame tetap utuh.
 */
export const PlaceholderScene: React.FC<{ scene: SceneTiming }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const progress = frame / scene.durationInFrames;
  return (
    <AbsoluteFill
      style={{
        background: 'radial-gradient(ellipse at 50% 40%, #1d2621 0%, #0b0f0d 75%)',
        justifyContent: 'center',
        alignItems: 'center',
        fontFamily: fonts.sans,
        color: colors.paper,
      }}
    >
      <div style={{ textAlign: 'center', opacity: interpolate(frame, [0, 20], [0, 1], { extrapolateRight: 'clamp' }) }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 22, letterSpacing: '0.3em', color: colors.rice }}>
          SCENE {scene.number} · {scene.kicker.toUpperCase()}
        </div>
        <div style={{ fontSize: 84, fontWeight: 700, marginTop: 24 }}>{scene.title}</div>
        <div style={{ fontFamily: fonts.mono, fontSize: 24, marginTop: 24, color: colors.paperDim }}>
          {scene.start} – {scene.end} · {scene.durationInFrames} frame
        </div>
        <div style={{ fontSize: 26, marginTop: 40, color: colors.paperFaint }}>
          Belum diimplementasikan — menunggu review Scene 1
        </div>
      </div>
      <div style={{ position: 'absolute', left: 0, bottom: 0, height: 4, width: `${progress * 100}%`, background: colors.riceDeep }} />
      <div style={{ position: 'absolute', right: 40, bottom: 24, fontFamily: fonts.mono, fontSize: 18, color: colors.paperFaint }}>
        {formatTc(scene.startFrame + frame)}
      </div>
    </AbsoluteFill>
  );
};
