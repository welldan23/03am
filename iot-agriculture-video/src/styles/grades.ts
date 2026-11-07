import type { CSSProperties } from 'react';

/**
 * Preset color grading. Dibuat dari filter CSS + lapisan warna (blend mode) di atas
 * foto asli — hanya mengatur nada warna, tidak "mengarang" isi gambar.
 */
export type GradeName = 'dawn' | 'natural' | 'lush' | 'golden' | 'title';

interface Grade {
  filter: string;
  /** Lapisan pewarna: bayangan sedikit teal, sorot sedikit hangat (look film). */
  wash: CSSProperties;
  /** Gradasi gelap atas/bawah untuk kedalaman & keterbacaan teks. */
  shade: string;
}

export const GRADES: Record<GradeName, Grade> = {
  dawn: {
    filter: 'contrast(1.08) saturate(0.95) brightness(0.98)',
    wash: {
      background: 'linear-gradient(180deg, rgba(255,190,140,0.20) 0%, rgba(40,70,90,0.18) 100%)',
      mixBlendMode: 'soft-light',
    },
    shade: 'linear-gradient(180deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0) 30%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.45) 100%)',
  },
  natural: {
    filter: 'contrast(1.06) saturate(0.9) brightness(0.97)',
    wash: {
      background: 'linear-gradient(180deg, rgba(255,214,170,0.16) 0%, rgba(30,60,60,0.20) 100%)',
      mixBlendMode: 'soft-light',
    },
    shade: 'linear-gradient(180deg, rgba(0,0,0,0.18) 0%, rgba(0,0,0,0) 28%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.5) 100%)',
  },
  lush: {
    filter: 'contrast(1.07) saturate(0.88) brightness(0.95) hue-rotate(-4deg)',
    wash: {
      background: 'linear-gradient(160deg, rgba(255,220,160,0.18) 0%, rgba(20,60,50,0.24) 100%)',
      mixBlendMode: 'soft-light',
    },
    shade: 'linear-gradient(180deg, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0) 30%, rgba(0,0,0,0) 58%, rgba(0,0,0,0.5) 100%)',
  },
  golden: {
    filter: 'contrast(1.05) saturate(0.92) brightness(0.98) sepia(0.08)',
    wash: {
      background: 'linear-gradient(200deg, rgba(255,190,110,0.26) 0%, rgba(60,50,40,0.18) 100%)',
      mixBlendMode: 'soft-light',
    },
    shade: 'linear-gradient(180deg, rgba(0,0,0,0.12) 0%, rgba(0,0,0,0) 30%, rgba(0,0,0,0) 58%, rgba(0,0,0,0.55) 100%)',
  },
  title: {
    filter: 'contrast(1.08) saturate(0.82) brightness(0.74)',
    wash: {
      background: 'linear-gradient(180deg, rgba(70,90,110,0.30) 0%, rgba(120,110,70,0.22) 100%)',
      mixBlendMode: 'soft-light',
    },
    shade: 'radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 0%, rgba(0,0,0,0.25) 55%, rgba(0,0,0,0.7) 100%)',
  },
};
