import { AbsoluteFill, interpolate, useCurrentFrame } from 'remotion';
import { AUDIO_CREDITS, PHOTO_CREDITS } from '../data/assets';
import { FACTS } from '../data/facts';
import { SFX_ENABLED } from '../data/sfx';
import { VIDEO_SUBTITLE, VIDEO_TITLE } from '../data/video';
import { colors, fonts } from '../styles/theme';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/**
 * Kredit penutup. Atribusi foto CC BY / CC BY-SA WAJIB tampil — daftar ini dibaca
 * langsung dari credits.generated.json supaya tidak pernah ketinggalan.
 */
interface EndCreditsProps {
  durationInFrames: number;
  /** Foto yang dipakai film ini. Default: foto film 5 menit (images/s*). */
  photoIds?: readonly string[];
  /** Lagu yang dipakai. Default: lagu film 5 menit. */
  musicIds?: readonly string[];
  title?: string;
  subtitle?: string;
  /** Sumber angka faktual yang tampil di film ini. */
  factSources?: readonly string[];
}

export const EndCredits: React.FC<EndCreditsProps> = ({
  durationInFrames,
  photoIds,
  musicIds = ['musicAffirmations'],
  title = VIDEO_TITLE,
  subtitle = VIDEO_SUBTITLE,
  factSources,
}) => {
  const frame = useCurrentFrame();
  const bg = interpolate(frame, [0, 14], [0, 1], clamp);
  const inP = interpolate(frame, [8, 32], [0, 1], clamp);
  const listP = interpolate(frame, [18, 44], [0, 1], clamp);
  const out = interpolate(frame, [durationInFrames - 30, durationInFrames - 4], [1, 0], clamp);
  // Hapus duplikat pembuat+lisensi agar daftar ringkas.
  const photos = photoIds ? PHOTO_CREDITS.filter((c) => photoIds.includes(c.id)) : PHOTO_CREDITS.filter((c) => c.file.startsWith('images/s'));
  const lines = [...new Map(photos.map((c) => [`${c.author}|${c.license}`, c])).values()];
  const half = Math.ceil(lines.length / 2);
  const cols = [lines.slice(0, half), lines.slice(half)];
  const sources = factSources ?? [...new Set(Object.values(FACTS).map((f) => f.source))];

  return (
    <AbsoluteFill style={{ backgroundColor: '#070a08', opacity: Math.min(bg, out), fontFamily: fonts.sans, color: colors.paper, alignItems: 'center' }}>
      <div style={{ marginTop: 70, textAlign: 'center', opacity: inP }}>
        <div style={{ fontSize: 46, fontWeight: 800, letterSpacing: '0.04em' }}>{title}</div>
        <div style={{ fontSize: 24, color: colors.paperDim, marginTop: 10 }}>{subtitle}</div>
      </div>
      <div style={{ marginTop: 36, fontFamily: fonts.mono, fontSize: 17, letterSpacing: '0.3em', color: colors.rice, opacity: listP }}>FOTO</div>
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
      <div style={{ marginTop: 26, fontFamily: fonts.mono, fontSize: 17, letterSpacing: '0.3em', color: colors.rice, opacity: listP }}>{SFX_ENABLED ? 'MUSIK & SUARA' : 'MUSIK'}</div>
      {AUDIO_CREDITS.filter((a) => musicIds.includes(a.id)).map((a) => (
        <div key={a.id} style={{ marginTop: 10, fontSize: 21, opacity: listP }}>
          “{a.title.replace(/^.* - /, '').replace(/\.[a-z0-9]+$/i, '')}” — {a.author} <span style={{ fontFamily: fonts.mono, fontSize: 16, color: colors.paperDim }}>· {a.license}</span>
        </div>
      ))}
      {SFX_ENABLED ? (
      <div style={{ marginTop: 10, fontSize: 18, color: colors.paperDim, opacity: listP }}>
        Suara alam:{' '}
        {AUDIO_CREDITS.filter((a) => a.id.startsWith('amb'))
          .map((a) => `${a.author} (${a.license})`)
          .join(' · ')}{' '}
        · Efek sintetis buatan sendiri
      </div>
      ) : null}
      <div style={{ marginTop: 22, fontSize: 18, color: colors.paperDim, textAlign: 'center', lineHeight: 1.6, opacity: listP }}>
        Foto dari Wikimedia Commons; daftar lengkap judul & tautan di CREDITS.md. Foto CC BY-SA yang diolah dibagikan dengan lisensi yang sama.
        <br />
        Sumber angka: {sources.join(' · ')} · Angka bertanda “data ilustrasi” adalah contoh.
        <br />
        Font Plus Jakarta Sans & JetBrains Mono (SIL OFL) · Dibuat dengan Remotion
      </div>
    </AbsoluteFill>
  );
};
