import type { CSSProperties } from 'react';
import { AbsoluteFill, Img, useCurrentFrame, useVideoConfig } from 'remotion';
import { coverTransform, handheld, poseAt, type CameraMove } from '../lib/camera';
import { GRADES, type GradeName } from '../styles/grades';

/** Selisih maksimum lapisan depan vs latar — cukup untuk terasa dalam, terlalu kecil untuk tampak dobel. */
const MAX_FG_SHIFT_PX = 3;
const MAX_FG_SCALE = 1.003;

export interface ParallaxOptions {
  /** Garis horizon (persen tinggi gambar). Area di bawahnya = lapisan depan. */
  horizon: number;
  /** Seberapa jauh lapisan depan bergerak lebih cepat dari latar (1 = tidak ada parallax). */
  depth: number;
  /** Lebar gradasi masker antar-lapisan (persen). Makin lebar makin halus sambungannya. */
  feather?: number;
}

export interface CinematicPhotoProps {
  src: string;
  width: number;
  height: number;
  camera: CameraMove;
  /** Durasi shot dalam frame (progress kamera 0→1 sepanjang durasi ini). */
  durationInFrames: number;
  grade?: GradeName;
  parallax?: ParallaxOptions;
  /** Amplitudo getaran gimbal (px). 0 = tripod/slider mulus. */
  shake?: number;
  seed?: number;
  style?: CSSProperties;
  /**
   * Lapisan grafis yang "menempel" pada foto (ikut pan/zoom kamera). `project`
   * mengubah koordinat persen gambar → piksel layar.
   */
  renderOverlay?: (project: (xPct: number, yPct: number) => { x: number; y: number }) => React.ReactNode;
}

/**
 * Foto asli + gerak kamera virtual (push-in, pan, tilt) + parallax 2.5D.
 *
 * Parallax: foto yang sama ditumpuk dua kali. Lapisan depan (di bawah horizon)
 * dimasker dengan gradasi lembut lalu digerakkan sedikit lebih jauh daripada
 * latar. Hasilnya kesan kedalaman seperti kamera slider, tanpa memalsukan isi foto.
 */
export const CinematicPhoto: React.FC<CinematicPhotoProps> = ({
  src,
  width,
  height,
  camera,
  durationInFrames,
  grade = 'natural',
  parallax,
  shake = 1.6,
  seed = 0,
  style,
  renderOverlay,
}) => {
  const frame = useCurrentFrame();
  const { width: W, height: H } = useVideoConfig();
  const progress = frame / Math.max(1, durationInFrames - 1);
  const pose = poseAt(camera, progress);
  const g = GRADES[grade];
  const jitter = handheld(frame, shake, seed);

  // Sedikit overscan agar rotasi/goyangan tidak memperlihatkan tepi.
  const overscan = 1.035;
  const base = coverTransform({ ...pose, zoom: pose.zoom * overscan }, { width, height }, { width: W, height: H });

  const layerStyle = (t: ReturnType<typeof coverTransform>): CSSProperties => ({
    position: 'absolute',
    left: 0,
    top: 0,
    width: t.width,
    height: t.height,
    transformOrigin: '0 0',
    transform: `translate3d(${t.tx}px, ${t.ty}px, 0) scale(${t.scale})`,
    filter: g.filter,
    willChange: 'transform',
  });

  let foreground: React.ReactNode = null;
  if (parallax) {
    // Lapisan depan: pergeseran dari titik awal diperbesar sebesar `depth`,
    // ditambah sedikit zoom ekstra — benda dekat terasa bergerak lebih cepat.
    const start = poseAt(camera, 0);
    const fgPose = {
      x: start.x + (pose.x - start.x) * parallax.depth,
      y: start.y + (pose.y - start.y) * parallax.depth,
      zoom: (start.zoom + (pose.zoom - start.zoom) * parallax.depth) * overscan * 1.01,
      rotate: pose.rotate,
    };
    const raw = coverTransform(fgPose, { width, height }, { width: W, height: H });
    // Batasi selisih antar-lapisan. Kalau terlalu jauh, objek yang melintasi
    // horizon (pohon kelapa, orang) tampak dobel di area gradasi masker.
    const lim = (v: number, max: number): number => Math.max(-max, Math.min(max, v));
    const scaleRatio = Math.max(1 / MAX_FG_SCALE, Math.min(MAX_FG_SCALE, raw.scale / base.scale));
    const fg = {
      ...base,
      scale: base.scale * scaleRatio,
      // Zoom ekstra dipusatkan di tengah layar supaya tidak menggeser gambar.
      tx: W / 2 - (W / 2 - base.tx) * scaleRatio + lim(raw.tx - base.tx, MAX_FG_SHIFT_PX),
      ty: H / 2 - (H / 2 - base.ty) * scaleRatio + lim(raw.ty - base.ty, MAX_FG_SHIFT_PX),
    };
    const feather = parallax.feather ?? 14;
    // Posisi horizon di layar mengikuti transform lapisan depan.
    const horizonPx = fg.ty + (parallax.horizon / 100) * fg.height * fg.scale;
    const hPct = (horizonPx / H) * 100;
    const mask = `linear-gradient(180deg, transparent ${hPct - feather / 2}%, #000 ${hPct + feather / 2}%)`;
    foreground = (
      <AbsoluteFill style={{ maskImage: mask, WebkitMaskImage: mask }}>
        <Img src={src} style={layerStyle(fg)} />
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#000', ...style }}>
      <AbsoluteFill
        style={{
          transform: `translate(${jitter.x}px, ${jitter.y}px) rotate(${pose.rotate + jitter.r}deg)`,
        }}
      >
        <Img src={src} style={layerStyle(base)} />
        {foreground}
        {renderOverlay
          ? renderOverlay((xPct, yPct) => ({
              x: base.tx + (xPct / 100) * base.width * base.scale,
              y: base.ty + (yPct / 100) * base.height * base.scale,
            }))
          : null}
      </AbsoluteFill>
      <AbsoluteFill style={g.wash} />
      <AbsoluteFill style={{ background: g.shade }} />
    </AbsoluteFill>
  );
};
