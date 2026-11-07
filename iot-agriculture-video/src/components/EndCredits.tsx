import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { CREDITS } from '../data/assets';
import { FACTS } from '../data/facts';
import { VIDEO_SUBTITLE, VIDEO_TITLE } from '../data/video';
import { colors, fonts } from '../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/**
 * Kredit penutup. Atribusi foto CC BY / CC BY-SA WAJIB tampil — daftar ini dibaca
 * langsung dari credits.generated.json supaya tidak pernah ketinggalan.
 */
export const EndCredits: React.FC<{ durationInFrames: number }> = ({ durationInFrames }) => {
  const frame = useCurrentFrame();
  const bg = interpolate(frame, [0, 14], [0, 1], clamp);
  const inP = interpolate(frame, [8, 32], [0, 1], clamp);
  const listP = interpolate(frame, [18, 44], [0, 1], clamp);
  const out = interpolate(frame, [durationInFrames - 30, durationInFrames - 4], [1, 0], clamp);
  // Hapus duplikat pembuat+lisensi agar daftar ringkas.
  const lines = [...new Map(CREDITS.map((c) => [`${c.author}|${c.license}`, c])).values()];
  const half = Math.ceil(lines.length / 2);
  const cols = [lines.slice(0, half), lines.slice(half)];
  const sources = [...new Set(Object.values(FACTS).map((f) => f.source))];

  return (
    <AbsoluteFill style={{ backgroundColor: '#070a08', opacity: Math.min(bg, out), fontFamily: fonts.sans, color: colors.paper, alignItems: 'center' }}>
      <div style={{ marginTop: 92, textAlign: 'center', opacity: inP }}>
        <div style={{ fontSize: 46, fontWeight: 800, letterSpacing: '0.04em' }}>{VIDEO_TITLE}</div>
        <div style={{ fontSize: 24, color: colors.paperDim, marginTop: 10 }}>{VIDEO_SUBTITLE}</div>
      </div>
      <div style={{ marginTop: 46, fontFamily: fonts.mono, fontSize: 17, letterSpacing: '0.3em', color: colors.rice, opacity: listP }}>FOTO</div>
      <div style={{ display: 'flex', gap: 90, marginTop: 18, opacity: listP }}>
        {cols.map((col, i) => (
          <div key={i} style={{ width: 640 }}>
            {col.map((c) => (
              <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 19, lineHeight: '30px', borderBottom: '1px solid rgba(244,241,234,0.06)' }}>
                <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 430 }}>{c.author || 'Tanpa nama'}</span>
                <span style={{ fontFamily: fonts.mono, fontSize: 16, color: colors.paperDim }}>{c.license}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 26, fontSize: 18, color: colors.paperDim, textAlign: 'center', lineHeight: 1.6, opacity: listP }}>
        Foto dari Wikimedia Commons; daftar lengkap judul & tautan di CREDITS.md. Foto CC BY-SA yang diolah dibagikan dengan lisensi yang sama.
        <br />
        Sumber angka: {sources.join(' · ')} · Angka bertanda “data ilustrasi” adalah contoh.
        <br />
        Font Plus Jakarta Sans & JetBrains Mono (SIL OFL) · Dibuat dengan Remotion
      </div>
    </AbsoluteFill>
  );
};
