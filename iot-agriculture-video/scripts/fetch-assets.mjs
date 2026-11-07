#!/usr/bin/env node
// Unduh foto berlisensi bebas dari Wikimedia Commons + catat kredit lisensinya.
// Hasil: public/assets/<file> dan src/data/credits.generated.json.
// Aman dijalankan ulang: file yang sudah ada dilewati kecuali pakai --force.
import { readFile, writeFile, mkdir, access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const force = process.argv.includes('--force');
const UA = 'IoTPertanianDocBuilder/0.1 (educational documentary; Remotion)';
const API = 'https://commons.wikimedia.org/w/api.php';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const stripHtml = (s = '') => s.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

async function fetchRetry(url, asJson) {
  for (let i = 0; i < 5; i++) {
    const res = await fetch(url, { headers: { 'User-Agent': UA } });
    if (res.ok) {
      if (!asJson) return Buffer.from(await res.arrayBuffer());
      const text = await res.text();
      try {
        return JSON.parse(text);
      } catch {
        /* rate-limit page in plain text: retry */
      }
    }
    const wait = 2000 * 2 ** i;
    console.warn(`  ! gagal (${res.status}), coba lagi dalam ${wait / 1000}s`);
    await sleep(wait);
  }
  throw new Error(`Tidak bisa mengambil ${url}`);
}

const exists = (p) => access(p).then(() => true, () => false);

const { assets } = JSON.parse(await readFile(path.join(root, 'scripts/asset-sources.json'), 'utf8'));
const credits = [];

for (const a of assets) {
  const params = new URLSearchParams({
    action: 'query',
    titles: a.commonsTitle,
    prop: 'imageinfo',
    iiprop: 'url|size|extmetadata',
    iiurlwidth: String(a.width),
    iiextmetadatafilter: 'LicenseShortName|LicenseUrl|Artist|ImageDescription',
    format: 'json',
  });
  console.log(`• ${a.id}: ${a.commonsTitle}`);
  const data = await fetchRetry(`${API}?${params}`, true);
  const page = Object.values(data.query.pages)[0];
  if (!page.imageinfo) throw new Error(`File tidak ditemukan: ${a.commonsTitle}`);
  const info = page.imageinfo[0];
  const meta = info.extmetadata ?? {};
  const license = meta.LicenseShortName?.value ?? 'unknown';
  if (!/^(CC0|CC BY|Public domain)/i.test(license)) {
    throw new Error(`Lisensi tidak diizinkan untuk ${a.commonsTitle}: ${license}`);
  }
  const out = path.join(root, 'public/assets', a.file);
  await mkdir(path.dirname(out), { recursive: true });
  if (force || !(await exists(out))) {
    const buf = await fetchRetry(info.thumburl ?? info.url, false);
    await writeFile(out, buf);
    console.log(`  ↳ disimpan ${a.file} (${Math.round(buf.length / 1024)} KB)`);
  } else {
    console.log('  ↳ sudah ada, dilewati');
  }
  credits.push({
    id: a.id,
    file: a.file,
    title: a.commonsTitle.replace(/^File:/, ''),
    author: stripHtml(meta.Artist?.value),
    license,
    licenseUrl: meta.LicenseUrl?.value ?? null,
    sourceUrl: info.descriptionurl,
    width: info.thumbwidth ?? info.width,
    height: info.thumbheight ?? info.height,
  });
  await sleep(1500);
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
      `| \`${c.file}\` | ${c.title} | ${c.author || '—'} | ${c.licenseUrl ? `[${c.license}](${c.licenseUrl})` : c.license} | [Wikimedia Commons](${c.sourceUrl}) |`,
  ),
  '',
  'Foto dengan lisensi CC BY-SA: versi yang di-grade/di-crop di video ini juga dibagikan di bawah lisensi yang sama.',
  '',
];
await mkdir(path.join(root, 'public/assets/credits'), { recursive: true });
await writeFile(path.join(root, 'public/assets/credits/CREDITS.md'), md.join('\n'));
console.log(`\nSelesai: ${credits.length} aset, kredit di src/data/credits.generated.json`);
