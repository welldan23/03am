// Font dibundel lokal lewat @fontsource (lisensi OFL) — tidak butuh internet saat
// render, jadi aman untuk render lokal maupun AWS Lambda.
import '@fontsource-variable/plus-jakarta-sans';
import '@fontsource-variable/jetbrains-mono';
import { continueRender, delayRender } from 'remotion';

const FONT_PROBES = [
  '400 40px "Plus Jakarta Sans Variable"',
  '700 40px "Plus Jakarta Sans Variable"',
  '400 20px "JetBrains Mono Variable"',
];

let started = false;

/** Tahan render sampai font siap, agar frame pertama tidak memakai font cadangan. */
export const ensureFontsLoaded = (): void => {
  if (started || typeof document === 'undefined') return;
  started = true;
  const handle = delayRender('Memuat font');
  Promise.all(FONT_PROBES.map((f) => document.fonts.load(f)))
    .then(() => continueRender(handle))
    .catch((err: unknown) => {
      console.error('Font gagal dimuat', err);
      continueRender(handle);
    });
};
