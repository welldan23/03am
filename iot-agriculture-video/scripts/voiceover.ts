/**
 * Alat voice-over (rekaman manual oleh narator).
 *
 *   npm run voiceover:script  → voiceover/NASKAH-VOICEOVER.md + voiceover/subtitles.srt
 *   npm run voiceover:scan    → pindai public/assets/voiceover/, ukur durasi tiap rekaman,
 *                               tulis src/data/voiceover.generated.json, beri peringatan
 *                               kalau rekaman menabrak kalimat berikutnya.
 *
 * Nama file rekaman = id kalimat: s1-01.wav, s1-02.wav, … (wav/mp3/m4a).
 * Alternatif: satu file utuh 5 menit bernama full.wav (mulai di 00:00).
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCENE_TIMINGS } from '../src/data/scenes';
import { SUBTITLES } from '../src/data/subtitles';
import { FPS, TOTAL_FRAMES } from '../src/data/video';
import { MATERI_CUES, MATERI_SCENES, MATERI_TOTAL_FRAMES } from '../src/films/materi/timeline';
import { formatTc } from '../src/lib/time';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cmd = process.argv[2];

/** Pilih film: tanpa argumen = film 5 menit, "materi" = film 8 menit. */
const FILMS = {
  utama: {
    title: 'IoT Pertanian Inovatif (5 menit)',
    scenes: SCENE_TIMINGS,
    cues: SUBTITLES,
    total: TOTAL_FRAMES,
    voDir: 'public/assets/voiceover',
    docDir: 'voiceover',
    json: 'src/data/voiceover.generated.json',
    arg: '',
  },
  materi: {
    title: 'IoT Pertanian Inovatif — Materi Lengkap (8 menit)',
    scenes: MATERI_SCENES,
    cues: MATERI_CUES,
    total: MATERI_TOTAL_FRAMES,
    voDir: 'public/assets/voiceover/materi',
    docDir: 'voiceover/materi',
    json: 'src/films/materi/voiceover.generated.json',
    arg: ' -- materi',
  },
} as const;
const filmKey = (process.argv[3] ?? 'utama') as keyof typeof FILMS;
const film = FILMS[filmKey];
if (!film) {
  console.log(`Film tidak dikenal: ${process.argv[3]}. Pilihan: ${Object.keys(FILMS).join(', ')}`);
  process.exit(1);
}
const SUBS: ReadonlyArray<{ id: string; scene: string; startFrame: number; endFrame: number; text: string }> = film.cues;
const SCENES: ReadonlyArray<{ id: string; number: number; title: string; start: string; end: string; endFrame: number }> = film.scenes;
const voDir = path.join(root, film.voDir);
const docDir = path.join(root, film.docDir);

/** Ruang bicara: dari awal kalimat sampai kalimat berikutnya mulai (atau scene berakhir). */
const slotEnd = (c: (typeof SUBS)[number], i: number): number => {
  const next = SUBS[i + 1];
  const scene = SCENES.find((s) => s.id === c.scene);
  const sceneEnd = scene?.endFrame ?? film.total;
  return Math.min(next && next.scene === c.scene ? next.startFrame : sceneEnd, film.total);
};
const sec = (f: number): string => (f / FPS).toFixed(1).replace('.', ',');
const srtTime = (f: number): string => {
  const ms = Math.round((f / FPS) * 1000);
  const h = String(Math.floor(ms / 3600000)).padStart(2, '0');
  const m = String(Math.floor((ms % 3600000) / 60000)).padStart(2, '0');
  const s = String(Math.floor((ms % 60000) / 1000)).padStart(2, '0');
  return `${h}:${m}:${s},${String(ms % 1000).padStart(3, '0')}`;
};

if (cmd === 'script') {
  mkdirSync(docDir, { recursive: true });
  const lines: string[] = [
    `# Naskah Voice-Over — ${film.title}`,
    '',
    'Dibuat otomatis oleh `npm run voiceover:script` dari `src/data/subtitles.ts`. Jangan diedit manual —',
    'ubah teksnya di `subtitles.ts`, lalu jalankan ulang perintahnya.',
    '',
    '## Cara merekam',
    '',
    '1. Rekam **satu file per kalimat**, beri nama sesuai kolom **ID** (contoh `s1-01.wav`).',
    '   Format: WAV/MP3/M4A, 48 kHz atau 44,1 kHz, mono atau stereo.',
    '2. Mulai bicara langsung (jeda hening di awal maks. ±0,2 detik) — rekaman diputar tepat',
    '   saat subtitle kalimat itu muncul.',
    '3. Usahakan durasi bicara **≤ kolom "Ruang bicara"**. Ruang = sampai kalimat berikutnya mulai.',
    '   Kalimat bertanda ⚠ cukup padat: baca sedikit lebih cepat atau ringkas jedanya.',
    `4. Taruh semua file di \`${film.voDir}/\`, lalu jalankan:`,
    `   \`npm run voiceover:scan${film.arg}\` → cek peringatan → render.`,
    '5. Musik otomatis mengecil jadi latar, dan "minggir" lagi setiap kamu bicara.',
    '',
    'Alternatif: rekam satu file utuh 5 menit sambil menonton video, beri nama `full.wav`.',
    '',
    'Tips: ruangan sunyi (lemari baju penuh baju = peredam bagus), mikrofon ±15 cm dari mulut,',
    'nada santai seperti bercerita, bukan membaca berita.',
    '',
  ];
  for (const scene of SCENES) {
    const cues = SUBS.map((c, i) => ({ c, i })).filter(({ c }) => c.scene === scene.id);
    if (!cues.length) continue;
    lines.push(`## Scene ${scene.number} · ${scene.title} (${scene.start}–${scene.end})`, '');
    lines.push('| ID | Mulai | Ruang bicara | Teks |', '|---|---|---|---|');
    for (const { c, i } of cues) {
      const room = slotEnd(c, i) - c.startFrame;
      const chars = c.text.replace(/\n/g, ' ').length;
      const tight = chars / (room / FPS) > 14 ? ' ⚠' : '';
      lines.push(`| \`${c.id}\` | ${formatTc(c.startFrame).slice(0, 5)} | ${sec(room)} dtk${tight} | ${c.text.replace(/\n/g, ' ')} |`);
    }
    lines.push('');
  }
  writeFileSync(path.join(docDir, 'NASKAH-VOICEOVER.md'), lines.join('\n'));
  const srt = SUBS.map((c, i) => `${i + 1}\n${srtTime(c.startFrame)} --> ${srtTime(c.endFrame)}\n${c.text}\n`).join('\n');
  writeFileSync(path.join(docDir, 'subtitles.srt'), srt);
  console.log(`✓ ${SUBS.length} kalimat → ${film.docDir}/NASKAH-VOICEOVER.md & ${film.docDir}/subtitles.srt`);
} else if (cmd === 'scan') {
  mkdirSync(voDir, { recursive: true });
  const files = existsSync(voDir) ? readdirSync(voDir).filter((f) => /\.(wav|mp3|m4a)$/i.test(f)) : [];
  const probe = (f: string): number =>
    Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path.join(voDir, f)]).toString().trim());
  const clips: Array<{ id: string; file: string; startFrame: number; durationInFrames: number }> = [];
  const warnings: string[] = [];
  const known = new Set(SUBS.map((c) => c.id));
  for (const f of files.sort()) {
    const id = f.replace(/\.[^.]+$/, '');
    if (id === 'full') {
      clips.push({ id, file: `${film.voDir.replace('public/assets/', '')}/${f}`, startFrame: 0, durationInFrames: Math.min(film.total, Math.round(probe(f) * FPS)) });
      continue;
    }
    if (!known.has(id)) {
      warnings.push(`${f}: tidak ada kalimat dengan id "${id}" — dilewati`);
      continue;
    }
    const i = SUBS.findIndex((c) => c.id === id);
    const cue = SUBS[i];
    if (!cue) continue;
    const dur = Math.round(probe(f) * FPS);
    const room = slotEnd(cue, i) - cue.startFrame;
    if (dur > room) warnings.push(`${f}: ${sec(dur)} dtk, ruangnya ${sec(room)} dtk → menabrak kalimat berikutnya ${sec(dur - room)} dtk`);
    clips.push({ id, file: `${film.voDir.replace('public/assets/', '')}/${f}`, startFrame: cue.startFrame, durationInFrames: dur });
  }
  if (clips.some((c) => c.id === 'full') && clips.length > 1) {
    warnings.push('Ada full.* DAN file per kalimat — pakai salah satu saja (suara bisa dobel).');
  }
  writeFileSync(path.join(root, film.json), JSON.stringify(clips, null, 2) + '\n');
  const missing = SUBS.filter((c) => !clips.some((k) => k.id === c.id || k.id === 'full')).map((c) => c.id);
  console.log(`✓ ${clips.length} rekaman terdeteksi → ${film.json}`);
  if (clips.length && missing.length) console.log(`  Belum direkam (${missing.length}): ${missing.join(', ')}`);
  warnings.forEach((w) => console.log(`  ! ${w}`));
} else {
  console.log('Pakai: npm run voiceover:script | npm run voiceover:scan');
  process.exit(1);
}
