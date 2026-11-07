import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from 'remotion';
import { colors, fonts } from '../styles/theme';

interface TitleSequenceProps {
  kicker: string;
  title: string;
  subtitle: string;
  /** Total durasi tampil (frame) — untuk drift skala pelan. */
  durationInFrames: number;
}

const reveal = Easing.bezier(0.16, 1, 0.3, 1); // cepat lalu mendarat lembut
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;

/**
 * Judul sinematik: kicker berjarak lebar → garis tipis tumbuh dari tengah →
 * kata-kata judul naik dari balik masker satu per satu → subjudul fokus-masuk.
 */
export const TitleSequence: React.FC<TitleSequenceProps> = ({ kicker, title, subtitle, durationInFrames }) => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, durationInFrames], [1, 1.025]);

  const kickerP = interpolate(frame, [0, 26], [0, 1], { ...clamp, easing: reveal });
  const lineP = interpolate(frame, [12, 44], [0, 1], { ...clamp, easing: reveal });
  const subP = interpolate(frame, [52, 80], [0, 1], { ...clamp, easing: reveal });
  const words = title.split(' ');

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', fontFamily: fonts.sans }}>
      <div style={{ transform: `scale(${drift})`, textAlign: 'center', color: colors.paper }}>
        <div
          style={{
            opacity: kickerP * 0.85,
            fontSize: 22,
            fontWeight: 500,
            letterSpacing: `${0.75 - kickerP * 0.3}em`,
            marginBottom: 30,
            paddingLeft: '0.45em',
            textTransform: 'uppercase',
          }}
        >
          {kicker}
        </div>
        <div style={{ display: 'flex', gap: 36, justifyContent: 'center' }}>
          {words.map((w, i) => {
            const p = interpolate(frame, [20 + i * 7, 46 + i * 7], [0, 1], { ...clamp, easing: reveal });
            return (
              <span key={w} style={{ display: 'inline-block', overflow: 'hidden', padding: '0.06em 0' }}>
                <span
                  style={{
                    display: 'inline-block',
                    transform: `translateY(${(1 - p) * 110}%)`,
                    fontSize: 116,
                    fontWeight: 800,
                    lineHeight: 1,
                    letterSpacing: '0.03em',
                    textShadow: '0 6px 40px rgba(0,0,0,0.45)',
                  }}
                >
                  {w}
                </span>
              </span>
            );
          })}
        </div>
        <div
          style={{
            height: 2,
            width: 620 * lineP,
            margin: '34px auto 30px',
            background: `linear-gradient(90deg, rgba(201,217,107,0), ${colors.rice}, rgba(201,217,107,0))`,
          }}
        />
        <div
          style={{
            opacity: subP,
            filter: `blur(${(1 - subP) * 8}px)`,
            fontSize: 44,
            fontWeight: 400,
            letterSpacing: `${0.12 - subP * 0.06}em`,
            color: colors.paper,
          }}
        >
          {subtitle}
        </div>
      </div>
    </AbsoluteFill>
  );
};
