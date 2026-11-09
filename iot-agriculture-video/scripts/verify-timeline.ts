/**
 * Verifikasi timeline tanpa render: durasi total, kontinuitas scene, kecocokan
 * dengan storyboard, aturan keterbacaan subtitle, dan keberadaan file aset.
 * Jalankan: npm run verify  (keluar dengan kode 1 jika ada yang gagal)
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCENE_TIMINGS } from '../src/data/scenes';
import { SFX_CUES } from '../src/data/sfx';
import { SUBTITLE_RULES, SUBTITLES } from '../src/data/subtitles';
import { FPS, HEIGHT, TOTAL_FRAMES, WIDTH } from '../src/data/video';
import { formatTc } from '../src/lib/time';
import { MATERI_CUES, MATERI_MUSIC, MATERI_SCENES, MATERI_TOTAL_FRAMES } from '../src/films/materi/timeline';

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
  id: string;
  file: string;
  license: string;
  author: string;
}>;
credits.forEach((c) => {
  check(existsSync(path.join(root, 'public/assets', c.file)), `${c.file} ada (${c.license}, ${c.author})`);
  if (!c.author) warn.push(`${c.file}: nama pembuat kosong`);
});

// Setiap photo('id') di kode harus ada di kredit — kalau tidak, render gagal di tengah jalan.
const listTsx = (dir: string): string[] =>
  readdirSync(dir).flatMap((n) => {
    const p = path.join(dir, n);
    return statSync(p).isDirectory() ? listTsx(p) : /\.tsx?$/.test(n) ? [p] : [];
  });
const knownIds = new Set(credits.map((c) => c.id));
for (const f of listTsx(path.join(root, 'src'))) {
  for (const m of readFileSync(f, 'utf8').matchAll(/photo\('([^']+)'\)/g)) {
    check(knownIds.has(m[1] ?? ''), `photo('${m[1]}') di ${path.relative(root, f)} terdaftar`);
  }
}

// ── Film 2: Materi lengkap 8 menit ─────────────────────────────────────
console.log('\n▶ Film 2 · Materi lengkap (8 menit)');
check(MATERI_TOTAL_FRAMES === 11520, `Total frame = ${MATERI_TOTAL_FRAMES} (harus 11.520 = 480 detik)`);
check(MATERI_SCENES[0]?.startFrame === 0, 'Scene pertama mulai di frame 0');
check(MATERI_SCENES[MATERI_SCENES.length - 1]?.endFrame === MATERI_TOTAL_FRAMES, 'Scene terakhir berakhir tepat di akhir film');
MATERI_SCENES.forEach((sc, i) => {
  const nx = MATERI_SCENES[i + 1];
  if (nx && sc.endFrame !== nx.startFrame) errors.push(`Film 2: scene ${sc.number} tidak bersambung dengan scene ${nx.number}`);
});
ok(`${MATERI_SCENES.length} scene bersambung, jumlah durasi ${MATERI_SCENES.reduce((a, x) => a + x.durationInFrames, 0)} frame`);
let filmErr = 0;
MATERI_CUES.forEach((c, i) => {
  const dur = (c.endFrame - c.startFrame) / FPS;
  const cps = c.text.replace(/\n/g, ' ').length / dur;
  const lines = c.text.split('\n');
  const sc = MATERI_SCENES.find((x) => x.id === c.scene);
  const label = `Film 2 [${formatTc(c.startFrame)}] "${c.text.replace(/\n/g, ' / ')}"`;
  const fail = (m: string): void => {
    errors.push(`${label}: ${m}`);
    filmErr++;
  };
  if (dur < R.minDurationSec) fail(`durasi ${dur.toFixed(2)}s`);
  if (cps > R.maxCharsPerSecond) fail(`${cps.toFixed(1)} karakter/detik`);
  if (lines.length > R.maxLines) fail(`${lines.length} baris`);
  lines.forEach((l) => l.length > R.maxCharsPerLine && fail(`baris ${l.length} karakter`));
  if (sc && (c.startFrame < sc.startFrame || c.endFrame > sc.endFrame)) fail('keluar dari rentang scene');
  const prev = MATERI_CUES[i - 1];
  if (prev && c.startFrame - prev.endFrame < R.minGapSec * FPS) fail('jeda terlalu dekat');
});
if (!filmErr) ok(`${MATERI_CUES.length} subtitle lolos aturan keterbacaan`);
MATERI_MUSIC.forEach((m) =>
  check(m.trimBeforeFrames >= 0 && m.startFrame + m.durationInFrames <= MATERI_TOTAL_FRAMES, `Musik ${m.creditId}: ${formatTc(m.startFrame)} → ${formatTc(m.startFrame + m.durationInFrames)}`),
);

console.log('\n▶ Efek suara');
const sfxFiles = ['whoosh', 'impact', 'tick', 'blip', 'alert', 'valve', 'drip', 'scan', 'drone-loop', 'wind-loop'];
sfxFiles.forEach((f) => check(existsSync(path.join(root, 'public/assets/sfx', `${f}.wav`)), `sfx/${f}.wav ada`));
const badSfx = SFX_CUES.filter((c) => c.startFrame < 0 || c.startFrame >= TOTAL_FRAMES || c.volume <= 0 || c.volume > 1);
check(badSfx.length === 0, `${SFX_CUES.length} cue efek suara di dalam durasi film & volume 0–1`);

const impl = SCENE_TIMINGS.filter((s) => s.implemented).length;
console.log(`\n▶ Progres: ${impl}/8 scene diimplementasikan`);
warn.forEach((w) => console.log(`  ! ${w}`));
if (errors.length) {
  console.error(`\n✗ ${errors.length} masalah:`);
  errors.forEach((e) => console.error(`  ✗ ${e}`));
  process.exit(1);
}
console.log('\n✓ Timeline valid.\n');
