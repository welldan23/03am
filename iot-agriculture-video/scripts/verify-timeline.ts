/**
 * Verifikasi timeline tanpa render: durasi total, kontinuitas scene, kecocokan
 * dengan storyboard, aturan keterbacaan subtitle, dan keberadaan file aset.
 * Jalankan: npm run verify  (keluar dengan kode 1 jika ada yang gagal)
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCENE_TIMINGS } from '../src/data/scenes';
import { SUBTITLE_RULES, SUBTITLES } from '../src/data/subtitles';
import { FPS, HEIGHT, TOTAL_FRAMES, WIDTH } from '../src/data/video';
import { formatTc } from '../src/lib/time';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const errors: string[] = [];
const warn: string[] = [];
const ok = (msg: string): void => console.log(`  ✓ ${msg}`);
const check = (cond: boolean, msg: string): void => {
  if (cond) ok(msg);
  else errors.push(msg);
};

console.log('\n▶ Spesifikasi');
check(FPS === 24, `FPS = ${FPS} (harus 24)`);
check(WIDTH === 1920 && HEIGHT === 1080, `Resolusi ${WIDTH}×${HEIGHT} (harus 1920×1080, 16:9)`);
check(TOTAL_FRAMES === 7200, `Total frame = ${TOTAL_FRAMES} (harus 7.200 = 300 detik)`);

console.log('\n▶ Scene vs storyboard');
const STORYBOARD = [
  ['00:00', '00:30'],
  ['00:30', '01:10'],
  ['01:10', '01:50'],
  ['01:50', '02:30'],
  ['02:30', '03:10'],
  ['03:10', '03:50'],
  ['03:50', '04:30'],
  ['04:30', '05:00'],
] as const;
check(SCENE_TIMINGS.length === STORYBOARD.length, `Jumlah scene = ${SCENE_TIMINGS.length} (harus 8)`);
SCENE_TIMINGS.forEach((s, i) => {
  const sb = STORYBOARD[i];
  check(
    !!sb && s.start === sb[0] && s.end === sb[1],
    `Scene ${s.number} ${s.start}–${s.end} → frame ${s.startFrame}–${s.endFrame} (${s.durationInFrames}f) ${s.implemented ? '' : '[placeholder]'}`,
  );
  const next = SCENE_TIMINGS[i + 1];
  if (next) check(s.endFrame === next.startFrame, `  kontinu: akhir scene ${s.number} = awal scene ${next.number}`);
});
const first = SCENE_TIMINGS[0];
const last = SCENE_TIMINGS[SCENE_TIMINGS.length - 1];
check(first?.startFrame === 0, 'Scene pertama mulai di frame 0');
check(last?.endFrame === TOTAL_FRAMES, `Scene terakhir berakhir tepat di frame ${TOTAL_FRAMES}`);
const sum = SCENE_TIMINGS.reduce((a, s) => a + s.durationInFrames, 0);
check(sum === TOTAL_FRAMES, `Jumlah durasi semua scene = ${sum} frame`);

console.log('\n▶ Subtitle');
const R = SUBTITLE_RULES;
SUBTITLES.forEach((c, i) => {
  const dur = (c.endFrame - c.startFrame) / FPS;
  const chars = c.text.replace(/\n/g, ' ').length;
  const cps = chars / dur;
  const lines = c.text.split('\n');
  const scene = SCENE_TIMINGS.find((s) => s.id === c.scene);
  const label = `[${formatTc(c.startFrame)}→${formatTc(c.endFrame)}] "${c.text.replace(/\n/g, ' / ')}"`;
  if (dur < R.minDurationSec) errors.push(`${label}: durasi ${dur.toFixed(2)}s < ${R.minDurationSec}s`);
  if (cps > R.maxCharsPerSecond) errors.push(`${label}: ${cps.toFixed(1)} karakter/detik > ${R.maxCharsPerSecond}`);
  if (lines.length > R.maxLines) errors.push(`${label}: ${lines.length} baris > ${R.maxLines}`);
  lines.forEach((l) => {
    if (l.length > R.maxCharsPerLine) errors.push(`${label}: baris "${l}" ${l.length} karakter > ${R.maxCharsPerLine}`);
  });
  if (scene && (c.startFrame < scene.startFrame || c.endFrame > scene.endFrame)) {
    errors.push(`${label}: keluar dari rentang scene ${scene.number}`);
  }
  const prev = SUBTITLES[i - 1];
  if (prev && c.startFrame - prev.endFrame < R.minGapSec * FPS) {
    errors.push(`${label}: jeda dengan cue sebelumnya < ${R.minGapSec}s`);
  }
  if (c.endFrame > TOTAL_FRAMES) errors.push(`${label}: melewati akhir video`);
  console.log(`  · ${label} ${dur.toFixed(2)}s, ${cps.toFixed(1)} cps`);
});
SCENE_TIMINGS.filter((s) => s.implemented && !SUBTITLES.some((c) => c.scene === s.id)).forEach((s) =>
  warn.push(`Scene ${s.number} sudah diimplementasikan tapi belum punya subtitle`),
);

console.log('\n▶ Aset');
const credits = JSON.parse(readFileSync(path.join(root, 'src/data/credits.generated.json'), 'utf8')) as Array<{
  file: string;
  license: string;
  author: string;
}>;
credits.forEach((c) => {
  check(existsSync(path.join(root, 'public/assets', c.file)), `${c.file} ada (${c.license}, ${c.author})`);
  if (!c.author) warn.push(`${c.file}: nama pembuat kosong`);
});

const impl = SCENE_TIMINGS.filter((s) => s.implemented).length;
console.log(`\n▶ Progres: ${impl}/8 scene diimplementasikan`);
warn.forEach((w) => console.log(`  ! ${w}`));
if (errors.length) {
  console.error(`\n✗ ${errors.length} masalah:`);
  errors.forEach((e) => console.error(`  ✗ ${e}`));
  process.exit(1);
}
console.log('\n✓ Timeline valid.\n');
