import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import type { TransitionStyle } from '../data/scenes';

interface SceneShellProps {
  /** Panjang scene menurut storyboard (frame). */
  durationInFrames: number;
  /** Panjang transisi (frame). Scene yang keluar tetap dirender selama ini di bawah scene baru. */
  transitionFrames: number;
  transitionIn: TransitionStyle | null;
  transitionOut: TransitionStyle | null;
  children: React.ReactNode;
}

const ease = Easing.bezier(0.45, 0, 0.2, 1);

/**
 * Pembungkus scene di timeline utama.
 *
 * Model transisi: scene baru MULAI di timecode storyboard-nya dan selesai masuk
 * `transitionFrames` kemudian. Scene lama diperpanjang sepanjang itu dan tetap
 * bergerak di bawahnya — jadi frame 0 setiap scene = timecode storyboard, dan
 * total durasi timeline tetap tepat 7.200 frame.
 */
export const SceneShell: React.FC<SceneShellProps> = ({
  durationInFrames,
  transitionFrames: T,
  transitionIn,
  transitionOut,
  children,
}) => {
  const frame = useCurrentFrame();
  const p = T > 0 ? interpolate(frame, [0, T], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease }) : 1;

  let opacity = 1;
  let filter: string | undefined;
  let transform: string | undefined;
  let mask: string | undefined;
  let black = 0;

  switch (transitionIn) {
    case 'fade':
      opacity = p;
      break;
    case 'blur-dissolve':
      opacity = p;
      filter = p < 1 ? `blur(${(1 - p) * 14}px)` : undefined;
      transform = p < 1 ? `scale(${1 + (1 - p) * 0.035})` : undefined;
      break;
    case 'dip-to-black':
      // Paruh pertama: scene lama meredup (lihat transitionOut). Paruh kedua: scene ini muncul dari hitam.
      opacity = p < 0.5 ? 0 : 1;
      black = p < 0.5 ? 1 : 1 - (p - 0.5) * 2;
      break;
    case 'light-wipe': {
      if (p < 1) {
        const edge = -25 + p * 150;
        mask = `linear-gradient(100deg, #000 ${edge - 25}%, transparent ${edge}%)`;
      }
      break;
    }
    case 'cut':
    case null:
      break;
  }

  // Scene yang KELUAR hanya bertindak untuk dip-to-black: meredup di paruh pertama transisi.
  if (transitionOut === 'dip-to-black' && T > 0) {
    black = Math.max(
      black,
      interpolate(frame, [durationInFrames, durationInFrames + T / 2], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      }),
    );
  }

  return (
    <AbsoluteFill style={{ opacity, filter, transform, maskImage: mask, WebkitMaskImage: mask }}>
      {children}
      {black > 0 ? <AbsoluteFill style={{ backgroundColor: '#000', opacity: black }} /> : null}
    </AbsoluteFill>
  );
};
