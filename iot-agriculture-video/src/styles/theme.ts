/**
 * Palet & tipografi. Arah visual: dokumenter alam yang hangat dan membumi —
 * hijau padi, tanah liat, langit pagi. Aksen data dibuat lembut (bukan neon).
 */
export const colors = {
  ink: '#0d1210',
  paper: '#f4f1ea',
  paperDim: 'rgba(244, 241, 234, 0.72)',
  paperFaint: 'rgba(244, 241, 234, 0.38)',
  rice: '#c9d96b', // hijau padi muda — aksen data utama
  riceDeep: '#5f7f3a',
  soil: '#8a5a3b',
  water: '#8fc3d1',
  sun: '#f2c27b',
  alert: '#e08a5f',
} as const;

export const fonts = {
  sans: '"Plus Jakarta Sans Variable", "Plus Jakarta Sans", system-ui, sans-serif',
  mono: '"JetBrains Mono Variable", "JetBrains Mono", ui-monospace, monospace',
} as const;

/** Area aman judul (title-safe) 1920×1080: margin 5% horizontal, 7,5% bawah. */
export const safe = {
  x: 96,
  top: 72,
  bottom: 81,
} as const;

export const textShadow = '0 2px 18px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.6)';

/** Bayangan lembut di belakang teks pojok — tetap terbaca di atas langit cerah. */
export const cornerScrim = 'radial-gradient(ellipse at center, rgba(0,0,0,0.38) 0%, rgba(0,0,0,0.18) 45%, rgba(0,0,0,0) 72%)';
