import { Audio, interpolate, Sequence, useVideoConfig } from 'remotion';
import { isLoopable, SFX_CUES, soundSrc } from '../data/sfx';
import { HAS_VOICEOVER } from '../data/voiceover';
import { speaking } from '../lib/voiceDuck';

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const;
/** Saat narator bicara, efek & suasana turun ke 45% supaya suara tetap jelas. */
const VO_DUCK = 0.55;

/** Semua efek suara & suasana dari data/sfx.ts, diposisikan di timeline utama. */
export const SoundEffects: React.FC<{ offset?: number }> = ({ offset = 0 }) => {
  const { durationInFrames } = useVideoConfig();
  return (
    <>
      {SFX_CUES.map((c) => {
        const from = c.startFrame - offset;
        if (from + c.durationInFrames <= 0 || from >= durationInFrames) return null;
        const skip = Math.max(0, -from);
        return (
          <Sequence key={c.key} name={`SFX ${c.sound}`} from={Math.max(0, from)} durationInFrames={c.durationInFrames - skip} layout="none">
            <Audio
              src={soundSrc(c.sound)}
              loop={isLoopable(c.sound)}
              trimBefore={isLoopable(c.sound) ? undefined : skip || undefined}
              volume={(f) => {
                const local = f + skip;
                const env =
                  c.fadeIn + c.fadeOut > 0
                    ? interpolate(local, [0, Math.max(1, c.fadeIn), c.durationInFrames - Math.max(1, c.fadeOut), c.durationInFrames], [0, 1, 1, 0], clamp)
                    : 1;
                const duck = HAS_VOICEOVER ? 1 - VO_DUCK * speaking(c.startFrame + local) : 1;
                return c.volume * env * duck;
              }}
            />
          </Sequence>
        );
      })}
    </>
  );
};
