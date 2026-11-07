import { AbsoluteFill } from 'remotion';
import type { CameraMove } from '../lib/camera';
import type { GradeName } from '../styles/grades';
import { CinematicPhoto } from './CinematicPhoto';

interface BackdropProps {
  src: string;
  width: number;
  height: number;
  durationInFrames: number;
  camera: CameraMove;
  grade?: GradeName;
  /** Seberapa kabur & gelap — latar untuk grafik, bukan subjek utama. */
  blur?: number;
  dim?: number;
}

/** Foto asli yang dikaburkan & digelapkan sebagai latar diagram/dasbor. */
export const Backdrop: React.FC<BackdropProps> = ({ blur = 16, dim = 0.55, grade = 'natural', ...photo }) => (
  <AbsoluteFill>
    <AbsoluteFill style={{ filter: `blur(${blur}px)`, transform: 'scale(1.06)' }}>
      <CinematicPhoto {...photo} grade={grade} shake={0.6} />
    </AbsoluteFill>
    <AbsoluteFill style={{ backgroundColor: `rgba(6,10,8,${dim})` }} />
  </AbsoluteFill>
);
