import { AbsoluteFill, interpolate, Sequence, useCurrentFrame } from 'remotion';

interface ShotProps {
  /** Frame mulai (relatif ke scene). */
  from: number;
  durationInFrames: number;
  /** Lama crossfade masuk/keluar (frame). Shot berikutnya sebaiknya mulai `fadeIn` frame lebih awal. */
  fadeIn?: number;
  fadeOut?: number;
  /** Zoom kecil + blur saat masuk, seperti fokus lensa "mendarat". */
  focusPull?: boolean;
  name?: string;
  children: React.ReactNode;
}

const ShotInner: React.FC<Omit<ShotProps, 'from' | 'name'>> = ({
  durationInFrames,
  fadeIn = 0,
  fadeOut = 0,
  focusPull = false,
  children,
}) => {
  const frame = useCurrentFrame();
  const inOpacity = fadeIn > 0 ? interpolate(frame, [0, fadeIn], [0, 1], { extrapolateRight: 'clamp' }) : 1;
  const outOpacity =
    fadeOut > 0
      ? interpolate(frame, [durationInFrames - fadeOut, durationInFrames], [1, 0], { extrapolateLeft: 'clamp' })
      : 1;
  const blur = focusPull ? interpolate(frame, [0, Math.max(1, fadeIn)], [8, 0], { extrapolateRight: 'clamp' }) : 0;
  return (
    <AbsoluteFill style={{ opacity: Math.min(inOpacity, outOpacity), filter: blur > 0.05 ? `blur(${blur}px)` : undefined }}>
      {children}
    </AbsoluteFill>
  );
};

/** Satu "shot" di dalam scene: Sequence + crossfade lembut. */
export const Shot: React.FC<ShotProps> = ({ from, durationInFrames, name, ...rest }) => (
  <Sequence from={from} durationInFrames={durationInFrames} name={name} layout="none">
    <ShotInner durationInFrames={durationInFrames} {...rest} />
  </Sequence>
);
