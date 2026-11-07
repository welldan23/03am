#!/usr/bin/env node
// Cek kesiapan render Lambda TANPA menghubungi AWS: versi paket, kredensial (hanya ada/tidak),
// dan ukuran folder public/ yang akan diunggah.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8'));
const all = { ...pkg.dependencies, ...pkg.devDependencies };
const remotionPkgs = Object.entries(all).filter(([k]) => k === 'remotion' || k.startsWith('@remotion/'));
const versions = new Set(remotionPkgs.map(([, v]) => v));

const dirSize = (dir) =>
  readdirSync(dir, { withFileTypes: true }).reduce((sum, e) => {
    const p = path.join(dir, e.name);
    return sum + (e.isDirectory() ? dirSize(p) : statSync(p).size);
  }, 0);

console.log('\nPreflight AWS Lambda (offline, tanpa biaya)\n');
console.log(`• Paket Remotion  : ${remotionPkgs.map(([k, v]) => `${k}@${v}`).join(', ')}`);
console.log(`  versi seragam   : ${versions.size === 1 ? 'ya ✓' : 'TIDAK ✗ — samakan semua versi @remotion/*'}`);
console.log(`• Kredensial AWS  : ${process.env.REMOTION_AWS_ACCESS_KEY_ID ? 'ada' : 'belum diset'} (nilai tidak ditampilkan)`);
console.log(`• Region          : ${process.env.REMOTION_AWS_REGION ?? 'ap-southeast-1 (default)'}`);
console.log(`• Ukuran public/  : ${(dirSize(path.join(root, 'public')) / 1024 / 1024).toFixed(1)} MB (ikut diunggah ke S3)`);
console.log('• Font            : dibundel lokal (@fontsource) — tidak butuh internet saat render');
console.log('\nLangkah berikut ada di README → "Render di cloud (AWS Lambda)".\n');
process.exit(versions.size === 1 ? 0 : 1);
