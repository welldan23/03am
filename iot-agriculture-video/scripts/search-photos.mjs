#!/usr/bin/env node
/**
 * Cari foto berlisensi bebas di Wikimedia Commons + Openverse (tanpa API key).
 *
 *   npm run search-photos -- "agricultural drone"            # cari, tampilkan daftar bernomor
 *   npm run search-photos -- "agricultural drone" --sheet    # + lembar kontak JPG buat dilihat
 *   npm run search-photos -- --pick 3 --id droneSpray --file images/s5-drone-spray.jpg
 *                                                            # ambil hasil no. 3 ke asset-sources.json
 *   npm run fetch-assets                                     # lalu unduh + catat kreditnya
 *
 * Opsi: --min-width=2400 (default; foto lebih kecil pecah saat di-zoom di 1080p), --limit=12
 */
import { execFileSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { http, searchCommons, searchOpenverse } from './lib/sources.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cacheDir = path.join(root, '.cache');
const cacheFile = path.join(cacheDir, 'last-search.json');
const sourcesFile = path.join(root, 'scripts/asset-sources.json');

const argv = process.argv.slice(2);
const opt = (name) => {
  const i = argv.findIndex((a) => a === `--${name}` || a.startsWith(`--${name}=`));
  if (i < 0) return undefined;
  const a = argv[i];
  return a.includes('=') ? a.split('=').slice(1).join('=') : argv[i + 1];
};
const has = (name) => argv.includes(`--${name}`);

// ── Mode ambil (--pick) ─────────────────────────────────────────────────
if (opt('pick')) {
  const n = Number(opt('pick'));
  const id = opt('id');
  const file = opt('file');
  if (!id || !/^[a-zA-Z][a-zA-Z0-9]*$/.test(id)) throw new Error('--id wajib, format camelCase (contoh: droneSpray)');
  if (!file || !/^images\/[a-z0-9-]+\.(jpg|jpeg|png)$/.test(file)) {
    throw new Error('--file wajib, contoh: images/s5-drone-spray.jpg');
  }
  const cache = JSON.parse(await readFile(cacheFile, 'utf8'));
  const hit = cache.results.find((r) => r.n === n);
  if (!hit) throw new Error(`Tidak ada hasil no. ${n} di pencarian terakhir ("${cache.query}")`);
  const sources = JSON.parse(await readFile(sourcesFile, 'utf8'));
  if (sources.assets.some((a) => a.id === id)) throw new Error(`id "${id}" sudah dipakai`);
  if (sources.assets.some((a) => a.file === file)) throw new Error(`file "${file}" sudah dipakai`);
  const width = Math.min(hit.width, Number(opt('width') ?? 3600));
  const entry =
    hit.provider === 'commons'
      ? { id, commonsTitle: hit.ref, file, width }
      : { id, openverseId: hit.ref, file, width, note: `${hit.source}: ${hit.title}` };
  sources.assets.push(entry);
  await writeFile(sourcesFile, JSON.stringify(sources, null, 2) + '\n');
  console.log(`✓ Ditambahkan: ${id} ← ${hit.title} (${hit.license}, ${hit.author || 'tanpa nama'})`);
  console.log('  Lanjut: npm run fetch-assets');
  process.exit(0);
}

// ── Mode cari ───────────────────────────────────────────────────────────
const query = argv.filter((a, i) => !a.startsWith('--') && !argv[i - 1]?.match(/^--(min-width|limit)$/)).join(' ').trim();
if (!query) {
  console.log('Pakai: npm run search-photos -- "kata kunci" [--sheet] [--min-width=2400] [--limit=12]');
  console.log('Tips: kata kunci bahasa Inggris biasanya dapat hasil lebih banyak.');
  process.exit(1);
}
const minWidth = Number(opt('min-width') ?? 2400);
const limit = Number(opt('limit') ?? 12);

const all = [];
const providerErrors = [];
for (const [name, fn] of [
  ['Commons', searchCommons],
  ['Openverse', searchOpenverse],
]) {
  try {
    all.push(...(await fn(query, limit)));
  } catch (err) {
    providerErrors.push(`${name}: ${err instanceof Error ? err.message : err}`); // satu sumber mati tidak menghentikan yang lain
  }
}

const rejected = { license: 0, small: 0 };
const usable = all.filter((r) => {
  if (!r.license) return (rejected.license++, false);
  if (r.width < minWidth) return (rejected.small++, false);
  return true;
});
// Lisensi paling longgar dulu, lalu yang paling besar.
const rank = (l) => (/^(CC0|Public domain)/i.test(l) ? 0 : /SA/.test(l) ? 2 : 1);
usable.sort((a, b) => rank(a.license) - rank(b.license) || b.width - a.width);
const results = usable.slice(0, limit).map((r, i) => ({ n: i + 1, ...r }));

await mkdir(cacheDir, { recursive: true });
await writeFile(cacheFile, JSON.stringify({ query, at: new Date().toISOString(), results }, null, 2));

console.log(`\nHasil untuk "${query}" (lebar ≥ ${minWidth}px)\n`);
for (const r of results) {
  const src = r.provider === 'commons' ? 'commons' : r.source;
  console.log(`${String(r.n).padStart(2)}. [${src}] ${r.title.slice(0, 70)}`);
  console.log(`    ${r.width}×${r.height} · ${r.license} · ${(r.author || '—').slice(0, 50)}`);
  console.log(`    ${r.pageUrl}`);
}
if (!results.length) console.log('(tidak ada hasil yang lolos — coba kata kunci lain atau --min-width lebih kecil)');
console.log(`\nDibuang: ${rejected.license} lisensi tidak bebas/tidak jelas, ${rejected.small} terlalu kecil.`);
providerErrors.forEach((e) => console.log(`! ${e}`));

if (has('sheet') && results.length) {
  // Lembar kontak: thumbnail bernomor dalam satu JPG, untuk memilih secara visual.
  const dir = path.join(cacheDir, 'thumbs');
  await mkdir(dir, { recursive: true });
  const files = [];
  for (const r of results) {
    try {
      const buf = await http(r.thumb, { json: false, tries: 3 });
      const f = path.join(dir, `${String(r.n).padStart(2, '0')}.jpg`);
      await writeFile(f, buf);
      files.push(f);
    } catch {
      /* thumbnail gagal: lewati saja */
    }
  }
  const out = path.join(cacheDir, 'contact-sheet.jpg');
  const inputs = files.flatMap((f) => ['-i', f]);
  const cols = 4;
  const scaled = files
    .map((f, i) => `[${i}]scale=480:300:force_original_aspect_ratio=increase,crop=480:300,drawtext=text='${Number(path.basename(f, '.jpg'))}':x=12:y=10:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.6[v${i}]`)
    .join(';');
  const layout = files.map((_, i) => `${(i % cols) * 480}_${Math.floor(i / cols) * 300}`).join('|');
  const filter = files.length > 1 ? `${scaled};${files.map((_, i) => `[v${i}]`).join('')}xstack=inputs=${files.length}:layout=${layout}:fill=black` : scaled.replace(/\[v0\]$/, '');
  try {
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...inputs, '-filter_complex', filter, '-frames:v', '1', out]);
    console.log(`\nLembar kontak: ${out}`);
  } catch {
    console.log('\n(ffmpeg tidak tersedia/gagal — lembar kontak dilewati; thumbnail ada di .cache/thumbs)');
  }
}
console.log('\nAmbil: npm run search-photos -- --pick <no> --id <namaCamelCase> --file images/<nama>.jpg\n');
