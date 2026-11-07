#!/usr/bin/env node
// Unduh foto dari scripts/asset-sources.json (Wikimedia Commons / Openverse) dan
// catat kredit lisensinya. Hasil: public/assets/<file>, src/data/credits.generated.json,
// public/assets/credits/CREDITS.md. File yang sudah ada dilewati kecuali --force.
// --optimize: perkecil juga file lama yang lebarnya > 3200px.
import { execFileSync } from 'node:child_process';
import { access, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { imageSize } from './lib/image-size.mjs';
import { commonsInfo, http, openverseInfo } from './lib/sources.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const force = process.argv.includes('--force');
const optimizeExisting = process.argv.includes('--optimize');
// 3200px cukup untuk zoom kamera ~1,6× di 1080p; lebih besar hanya memperberat repo & upload Lambda.
// Tapi tinggi minimal 1600px tetap dijaga — panorama ultra-lebar butuh tinggi untuk menutup 1080p.
const MAX_WIDTH = 3200;
const MIN_HEIGHT = 1600;

/** Perkecil JPEG yang terlalu lebar (butuh ffmpeg; kalau tidak ada, file dibiarkan). */
function optimize(file, { width, height }) {
  const target = Math.max(MAX_WIDTH, Math.round((MIN_HEIGHT * width) / height));
  if (width <= target || !/\.jpe?g$/i.test(file)) return false;
  const tmp = `${file}.tmp.jpg`;
  try {
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', file, '-vf', `scale=${target}:-2:flags=lanczos`, '-q:v', '3', tmp]);
  } catch {
    console.log('  ! ffmpeg tidak tersedia — foto tidak diperkecil');
    return false;
  }
  return rename(tmp, file).then(() => true);
}
const exists = (p) => access(p).then(() => true, () => false);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { assets } = JSON.parse(await readFile(path.join(root, 'scripts/asset-sources.json'), 'utf8'));
const credits = [];
const failed = [];

for (const a of assets) {
  const label = a.commonsTitle ?? `openverse:${a.openverseId}`;
  console.log(`• ${a.id}: ${label}`);
  try {
    let info;
    if (a.commonsTitle) info = await commonsInfo(a.commonsTitle, a.width ?? 3600);
    else if (a.openverseId) info = await openverseInfo(a.openverseId);
    else throw new Error('entri butuh commonsTitle atau openverseId');

    if (!info.license) throw new Error(`lisensi ditolak: "${info.licenseRaw || 'tidak ada'}"`);

    const out = path.join(root, 'public/assets', a.file);
    await mkdir(path.dirname(out), { recursive: true });

    if (a.kind === 'audio') {
      // Audio: unduh file asli lalu ubah ke MP3 192 kbps (didukung Chrome & Remotion).
      if (force || !(await exists(out))) {
        const src = await http(info.downloadUrl, { json: false });
        const tmp = `${out}.src`;
        await writeFile(tmp, src);
        execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', tmp, '-vn', '-c:a', 'libmp3lame', '-b:a', '192k', out]);
        await rm(tmp, { force: true });
        console.log(`  ↳ disimpan ${a.file}`);
      } else {
        console.log('  ↳ sudah ada, dilewati');
      }
      credits.push({
        id: a.id,
        kind: 'audio',
        file: a.file,
        provider: 'wikimedia-commons',
        title: info.title,
        author: info.author,
        license: info.license,
        licenseUrl: info.licenseUrl ?? null,
        sourceUrl: info.pageUrl,
        width: 0,
        height: 0,
        durationSec: info.duration,
      });
      await sleep(1200);
      continue;
    }

    let buf;
    const fresh = force || !(await exists(out));
    if (fresh) {
      buf = await http(info.downloadUrl, { json: false });
      await writeFile(out, buf);
    } else {
      buf = await readFile(out);
    }
    if ((fresh || optimizeExisting) && (await optimize(out, imageSize(buf)))) buf = await readFile(out);
    console.log(fresh ? `  ↳ disimpan ${a.file} (${Math.round(buf.length / 1024)} KB)` : '  ↳ sudah ada, dilewati');
    // Dimensi diambil dari file sebenarnya — metadata sumber kadang tidak cocok.
    const { width, height } = imageSize(buf);
    if (width < 1920) console.log(`  ! hanya ${width}px — akan pecah kalau di-zoom di 1080p`);

    credits.push({
      id: a.id,
      kind: 'image',
      file: a.file,
      provider: a.commonsTitle ? 'wikimedia-commons' : `openverse/${info.source}`,
      title: info.title,
      author: info.author,
      license: info.license,
      licenseUrl: info.licenseUrl ?? null,
      sourceUrl: info.pageUrl,
      width,
      height,
    });
  } catch (err) {
    console.error(`  ✗ ${err instanceof Error ? err.message : err}`);
    failed.push(a.id);
  }
  await sleep(1200);
}

if (failed.length) {
  // Jangan menulis kredit setengah jadi: lebih baik gagal jelas daripada aset tanpa atribusi.
  console.error(`\n✗ Gagal: ${failed.join(', ')}. Kredit TIDAK diperbarui. Coba lagi sebentar lagi (rate limit) atau hapus entrinya.`);
  process.exit(1);
}

await writeFile(path.join(root, 'src/data/credits.generated.json'), JSON.stringify(credits, null, 2) + '\n');

const md = [
  '# Kredit Aset',
  '',
  'File ini dibuat otomatis oleh `npm run fetch-assets`. Jangan diedit manual.',
  '',
  '| File | Judul asli | Pembuat | Lisensi | Sumber |',
  '|---|---|---|---|---|',
  ...credits.map(
    (c) =>
      `| \`${c.file}\` | ${c.title.replace(/\|/g, '/')} | ${c.author || '—'} | ${c.licenseUrl ? `[${c.license}](${c.licenseUrl})` : c.license} | [${c.provider}](${c.sourceUrl}) |`,
  ),
  '',
  'Foto dengan lisensi CC BY-SA: versi yang di-grade/di-crop di video ini juga dibagikan di bawah lisensi yang sama.',
  '',
];
await mkdir(path.join(root, 'public/assets/credits'), { recursive: true });
await writeFile(path.join(root, 'public/assets/credits/CREDITS.md'), md.join('\n'));
console.log(`\nSelesai: ${credits.length} aset, kredit di src/data/credits.generated.json`);
