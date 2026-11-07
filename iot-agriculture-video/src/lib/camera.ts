import { Easing, interpolate } from 'remotion';

/**
 * Posisi kamera virtual di atas sebuah gambar.
 *  - x, y  : titik fokus dalam persen gambar (0–100). 50/50 = tengah.
 *  - zoom  : 1 = gambar pas menutupi frame (cover); >1 = lebih dekat.
 *  - rotate: derajat, untuk sedikit "dutch"/roll yang halus.
 */
export interface CameraPose {
  x: number;
  y: number;
  zoom: number;
  rotate?: number;
}

export interface CameraMove {
  from: CameraPose;
  to: CameraPose;
  /** Kurva gerak. Default: ease-in-out lembut seperti dolly/slider sungguhan. */
  easing?: (t: number) => number;
}

export const CINEMATIC_EASE = Easing.bezier(0.37, 0, 0.18, 1);
export const LINEAR_DRIFT = (t: number): number => t;

/** Interpolasi pose kamera pada progress 0–1. */
export const poseAt = (move: CameraMove, progress: number): Required<CameraPose> => {
  const t = (move.easing ?? CINEMATIC_EASE)(Math.min(1, Math.max(0, progress)));
  const lerp = (a: number, b: number): number => interpolate(t, [0, 1], [a, b]);
  return {
    x: lerp(move.from.x, move.to.x),
    y: lerp(move.from.y, move.to.y),
    zoom: lerp(move.from.zoom, move.to.zoom),
    rotate: lerp(move.from.rotate ?? 0, move.to.rotate ?? 0),
  };
};

/**
 * Getaran halus "kamera di tangan / gimbal" — beberapa sinus dengan frekuensi tak
 * sebanding supaya tidak terasa berulang. Amplitudo dalam piksel.
 */
export const handheld = (frame: number, amplitude = 2.5, seed = 0): { x: number; y: number; r: number } => {
  const f = frame + seed * 97;
  const x = Math.sin(f / 23.1) * 0.6 + Math.sin(f / 9.7 + 1.3) * 0.25 + Math.sin(f / 51.3 + 2.1) * 0.15;
  const y = Math.cos(f / 19.4 + 0.7) * 0.6 + Math.sin(f / 11.3 + 2.9) * 0.25 + Math.cos(f / 43.7) * 0.15;
  const r = Math.sin(f / 37.9 + 0.4) * 0.5 + Math.sin(f / 15.1) * 0.5;
  return { x: x * amplitude, y: y * amplitude, r: r * amplitude * 0.012 };
};

/**
 * Hitung transform CSS supaya titik fokus (x%, y%) gambar berada di tengah frame
 * pada zoom tertentu, tanpa pernah memperlihatkan tepi gambar.
 */
export const coverTransform = (
  pose: Required<CameraPose>,
  image: { width: number; height: number },
  frameSize: { width: number; height: number },
): { width: number; height: number; tx: number; ty: number; scale: number } => {
  const coverScale = Math.max(frameSize.width / image.width, frameSize.height / image.height);
  const w = image.width * coverScale;
  const h = image.height * coverScale;
  const scale = Math.max(1, pose.zoom);
  // Lebar/tinggi yang terlihat setelah zoom
  const visW = frameSize.width / scale;
  const visH = frameSize.height / scale;
  // Pusat yang diinginkan (dalam koordinat gambar ter-cover), dijepit agar tepi tidak kelihatan
  const cx = Math.min(w - visW / 2, Math.max(visW / 2, (pose.x / 100) * w));
  const cy = Math.min(h - visH / 2, Math.max(visH / 2, (pose.y / 100) * h));
  return {
    width: w,
    height: h,
    tx: frameSize.width / 2 - cx * scale,
    ty: frameSize.height / 2 - cy * scale,
    scale,
  };
};
