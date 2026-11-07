#!/usr/bin/env node
/**
 * Generator efek suara sintetis — semua dihitung dari rumus (osilator, noise, filter),
 * TANPA sampel rekaman, jadi bebas lisensi & bisa dibuat ulang persis sama.
 * Hasil: public/assets/sfx/*.wav (48 kHz, 16-bit, stereo).
 *
 *   npm run make-sfx
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outDir = path.join(root, 'public/assets/sfx');
const SR = 48000;
const TAU = Math.PI * 2;

// PRNG deterministik supaya hasil selalu identik.
const rng = (seed) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

/** Filter biquad (RBJ) dengan frekuensi yang boleh berubah tiap sampel. */
const biquad = (type) => {
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  return (x, f, q = 0.8) => {
    const w = (TAU * Math.min(f, SR * 0.45)) / SR;
    const a = Math.sin(w) / (2 * q);
    const c = Math.cos(w);
    let b0, b1, b2;
    if (type === 'lp') [b0, b1, b2] = [(1 - c) / 2, 1 - c, (1 - c) / 2];
    else if (type === 'hp') [b0, b1, b2] = [(1 + c) / 2, -(1 + c), (1 + c) / 2];
    else [b0, b1, b2] = [a, 0, -a]; // band-pass
    const a0 = 1 + a, a1 = -2 * c, a2 = 1 - a;
    const y = (b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0;
    x2 = x1; x1 = x; y2 = y1; y1 = y;
    return y;
  };
};

const env = (t, attack, decay) => (t < attack ? t / attack : Math.exp(-(t - attack) / decay));
const smooth = (t) => t * t * (3 - 2 * t);

/** Render: fn(t, i) → [kiri, kanan]. Lalu dinormalisasi ke puncak `peak` dBFS. */
function render(name, seconds, fn, peakDb = -3) {
  const n = Math.round(seconds * SR);
  const L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const [l, r] = fn(i / SR, i);
    L[i] = l; R[i] = r;
  }
  let max = 1e-9;
  for (let i = 0; i < n; i++) max = Math.max(max, Math.abs(L[i]), Math.abs(R[i]));
  const g = 10 ** (peakDb / 20) / max;
  const buf = Buffer.alloc(44 + n * 4);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, L[i] * g)) * 32767), 44 + i * 4);
    buf.writeInt16LE(Math.round(Math.max(-1, Math.min(1, R[i] * g)) * 32767), 46 + i * 4);
  }
  writeFileSync(path.join(outDir, `${name}.wav`), buf);
  console.log(`  ✓ ${name}.wav (${seconds}s)`);
}

mkdirSync(outDir, { recursive: true });
console.log('Membuat efek suara sintetis…');

// Whoosh transisi: noise lewat band-pass yang menyapu naik-turun + panning kiri→kanan.
{
  const r = rng(1), bpL = biquad('bp'), bpR = biquad('bp');
  const D = 1.6;
  render('whoosh', D, (t) => {
    const p = t / D;
    const f = 250 + 2600 * Math.sin(Math.PI * smooth(p)) ** 2;
    const a = Math.sin(Math.PI * p) ** 2.2;
    const nz = r() * 2 - 1;
    const pan = smooth(p);
    return [bpL(nz, f, 0.9) * a * (1.2 - pan), bpR(nz, f * 1.03, 0.9) * a * (0.2 + pan)];
  }, -6);
}

// Dentum lembut untuk judul: sinus rendah yang turun nada + "udara" noise ber-low-pass.
{
  const r = rng(2), lp = biquad('lp');
  let ph = 0;
  render('impact', 3.5, (t) => {
    const f = 38 + 34 * Math.exp(-t * 6);
    ph += (TAU * f) / SR;
    const body = Math.sin(ph) * env(t, 0.01, 0.9);
    const air = lp(r() * 2 - 1, 900 * Math.exp(-t * 2) + 120) * env(t, 0.004, 0.35) * 0.9;
    const s = body + air;
    return [s, s * 0.96];
  }, -4);
}

// Tik UI: klik pendek bernada tinggi, sangat halus.
render('tick', 0.14, (t) => {
  const s = Math.sin(TAU * 2300 * t) * env(t, 0.001, 0.018) + Math.sin(TAU * 4600 * t) * env(t, 0.0005, 0.006) * 0.3;
  return [s, s];
}, -9);

// Blip data: dua nada naik (seperti notifikasi lembut).
render('blip', 0.22, (t) => {
  const f = t < 0.07 ? 1320 : 1760;
  const s = Math.sin(TAU * f * t) * env(t % 0.07, 0.002, 0.04) * (t < 0.14 ? 1 : 0.4);
  return [s, s];
}, -10);

// Alarm peringatan: dua nada turun, tidak menusuk.
render('alert', 0.7, (t) => {
  const f = t < 0.3 ? 880 : 660;
  const local = t < 0.3 ? t : t - 0.3;
  const s = (Math.sin(TAU * f * t) + 0.35 * Math.sin(TAU * f * 2 * t)) * env(local, 0.006, 0.12);
  return [s, s];
}, -8);

// Katup: bunyi mekanis "klek" — thump rendah + noise pendek ber-band-pass.
{
  const r = rng(3), bp = biquad('bp');
  render('valve', 0.6, (t) => {
    const thump = Math.sin(TAU * (160 - 80 * t) * t) * env(t, 0.002, 0.07);
    const click = bp(r() * 2 - 1, 2400, 2) * env(t, 0.0005, 0.02) * 3;
    const click2 = t > 0.09 ? bp(r() * 2 - 1, 1600, 2) * env(t - 0.09, 0.0005, 0.03) * 2 : 0;
    const s = thump + click + click2;
    return [s, s];
  }, -5);
}

// Tetesan air: nada yang cepat naik lalu meluruh ("plink").
{
  let ph = 0;
  render('drip', 0.35, (t) => {
    const f = 900 + 1700 * (1 - Math.exp(-t * 60));
    ph += (TAU * f) / SR;
    const s = Math.sin(ph) * env(t, 0.001, 0.05);
    return [s * 0.8, s];
  }, -10);
}

// Sapuan pemindai (peta tanaman): nada naik pelan dengan getaran, sangat tipis.
{
  let ph = 0;
  const D = 5;
  render('scan', D, (t) => {
    const p = t / D;
    const f = 320 + 900 * p;
    ph += (TAU * f) / SR;
    const trem = 0.6 + 0.4 * Math.sin(TAU * 7 * t);
    const a = Math.sin(Math.PI * p) ** 1.5;
    const s = (Math.sin(ph) + 0.25 * Math.sin(ph * 2)) * trem * a;
    return [s * (1 - p * 0.5), s * (0.5 + p * 0.5)];
  }, -14);
}

// Dengung drone (loop 4 detik mulus): harmonik baling-baling + modulasi + desis udara.
// Frekuensi dipilih kelipatan 0,25 Hz agar fase kembali tepat di ujung loop.
{
  const r = rng(4), lp = biquad('lp');
  const D = 4;
  const fund = [182.25, 197.5, 211.75, 224.0];
  render('drone-loop', D, (t) => {
    let s = 0;
    fund.forEach((f, k) => {
      const wob = 1 + 0.004 * Math.sin(TAU * (0.5 + k * 0.25) * t);
      for (let h = 1; h <= 5; h++) s += (Math.sin(TAU * f * h * wob * t + k) / h ** 1.3) * 0.25;
    });
    const air = lp(r() * 2 - 1, 1800) * 0.5;
    const am = 0.85 + 0.15 * Math.sin(TAU * 1.5 * t);
    return [(s + air) * am, (s * 0.97 + air) * am];
  }, -6);
}

// Angin (loop 10 detik): noise ber-low-pass dengan hembusan pelan. Ujung loop di-crossfade.
{
  const r = rng(5), lpL = biquad('lp'), lpR = biquad('lp');
  const D = 10, X = 1.5; // panjang crossfade
  const n = Math.round((D + X) * SR);
  const L = new Float32Array(n), R = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const gust = 0.55 + 0.3 * Math.sin(TAU * 0.13 * t) + 0.15 * Math.sin(TAU * 0.37 * t + 1);
    const f = 300 + 500 * gust;
    L[i] = lpL(r() * 2 - 1, f, 0.7) * gust;
    R[i] = lpR(r() * 2 - 1, f * 1.1, 0.7) * gust;
  }
  const m = Math.round(D * SR), xs = Math.round(X * SR);
  render('wind-loop', D, (_t, i) => {
    if (i < xs) {
      const k = i / xs;
      return [L[i] * k + L[i + m] * (1 - k), R[i] * k + R[i + m] * (1 - k)];
    }
    return [L[i], R[i]];
  }, -6);
}

console.log(`Selesai → ${path.relative(root, outDir)}/`);
