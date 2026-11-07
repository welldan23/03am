import { AbsoluteFill, random, useCurrentFrame } from 'remotion';
import { GRAIN_TEXTURE } from '../data/assets';

/** Butiran film halus: tekstur noise kecil yang digeser acak tiap frame. */
export const FilmGrain: React.FC<{ opacity?: number }> = ({ opacity = 0.07 }) => {
  const frame = useCurrentFrame();
  const ox = Math.floor(random(`gx-${frame}`) * 256);
  const oy = Math.floor(random(`gy-${frame}`) * 256);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        backgroundImage: `url(${GRAIN_TEXTURE})`,
        backgroundSize: '256px 256px',
        backgroundPosition: `${ox}px ${oy}px`,
        mixBlendMode: 'overlay',
        opacity,
      }}
    />
  );
};

/** Vinyet lensa — menggelapkan sudut supaya mata tertuju ke tengah. */
export const Vignette: React.FC<{ strength?: number }> = ({ strength = 0.55 }) => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      background: `radial-gradient(ellipse 75% 70% at 50% 48%, rgba(0,0,0,0) 55%, rgba(0,0,0,${strength}) 100%)`,
    }}
  />
);
