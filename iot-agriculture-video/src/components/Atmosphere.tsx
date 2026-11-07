import { AbsoluteFill, interpolate, random, useCurrentFrame } from 'remotion';

interface MistProps {
  /** Opasitas maksimum kabut (0–1). Jaga tetap rendah supaya natural. */
  intensity?: number;
  /** Posisi vertikal pita kabut (persen layar). */
  bands?: readonly number[];
  color?: string;
  /** Kecepatan dasar (px/frame). Pita yang lebih rendah = lebih dekat = lebih cepat. */
  speed?: number;
}

/** Kabut pagi berlapis — tiap pita bergerak dengan kecepatan berbeda (parallax). */
export const Mist: React.FC<MistProps> = ({
  intensity = 0.22,
  bands = [42, 58, 74],
  color = '255,250,240',
  speed = 0.35,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'screen' }}>
      {bands.map((top, i) => {
        const depth = 0.6 + i * 0.5;
        const x = -400 + ((frame * speed * depth + i * 530) % 2400);
        const breathe = 0.75 + 0.25 * Math.sin(frame / (40 + i * 13) + i);
        return (
          <div
            key={top}
            style={{
              position: 'absolute',
              top: `${top}%`,
              left: x - 1200,
              width: 3600,
              height: 260 + i * 70,
              transform: 'translateY(-50%)',
              background: `radial-gradient(ellipse at 30% 50%, rgba(${color},${intensity * breathe}) 0%, rgba(${color},0) 60%), radial-gradient(ellipse at 75% 55%, rgba(${color},${intensity * 0.8 * breathe}) 0%, rgba(${color},0) 55%)`,
              filter: `blur(${30 + i * 10}px)`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

interface ParticlesProps {
  count?: number;
  seed?: string;
  /** Arah angin (px/frame) untuk partikel terdekat. */
  wind?: number;
  opacity?: number;
}

/**
 * Debu/serbuk sari melayang dengan 3 tingkat kedalaman: partikel dekat lebih besar,
 * lebih kabur, dan bergerak lebih cepat. Posisi deterministik (random(seed)).
 */
export const FloatingParticles: React.FC<ParticlesProps> = ({
  count = 46,
  seed = 'dust',
  wind = 0.9,
  opacity = 0.5,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      {Array.from({ length: count }, (_, i) => {
        const depth = random(`${seed}-d-${i}`); // 0 = jauh, 1 = dekat
        const size = 2 + depth * depth * 9;
        const x0 = random(`${seed}-x-${i}`) * 2100 - 90;
        const y0 = random(`${seed}-y-${i}`) * 1080;
        const x = ((x0 + frame * wind * (0.25 + depth)) % 2100) - 90;
        const y = y0 + Math.sin(frame / (30 + depth * 40) + i) * (8 + depth * 20) - frame * 0.08 * (0.3 + depth);
        const twinkle = interpolate(Math.sin(frame / 17 + i * 1.7), [-1, 1], [0.35, 1]);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x,
              top: ((y % 1120) + 1120) % 1120 - 20,
              width: size,
              height: size,
              borderRadius: '50%',
              background: 'rgba(255,244,220,1)',
              opacity: opacity * twinkle * (0.3 + depth * 0.7),
              filter: `blur(${depth > 0.7 ? (depth - 0.7) * 10 : 0.4}px)`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

interface LightLeakProps {
  /** Opasitas puncak. */
  strength?: number;
  /** Sudut asal cahaya, misal 'top right'. */
  origin?: string;
  color?: string;
}

/** Bocoran cahaya matahari hangat yang "bernafas" pelan — seperti flare lensa nyata. */
export const SunGlow: React.FC<LightLeakProps> = ({
  strength = 0.35,
  origin = '85% 8%',
  color = '255,196,128',
}) => {
  const frame = useCurrentFrame();
  const pulse = 0.82 + 0.18 * Math.sin(frame / 48);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        mixBlendMode: 'screen',
        background: `radial-gradient(circle at ${origin}, rgba(${color},${strength * pulse}) 0%, rgba(${color},${strength * 0.35 * pulse}) 22%, rgba(${color},0) 55%)`,
      }}
    />
  );
};
