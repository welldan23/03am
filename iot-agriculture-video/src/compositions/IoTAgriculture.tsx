import { AbsoluteFill, Sequence } from 'remotion';
import { FilmGrain, Vignette } from '../components/FilmLook';
import { PlaceholderScene } from '../components/PlaceholderScene';
import { SceneShell } from '../components/SceneShell';
import { SoundEffects } from '../components/SoundEffects';
import { Soundtrack } from '../components/Soundtrack';
import { Subtitles } from '../components/Subtitles';
import { SCENE_TIMINGS, type SceneTiming } from '../data/scenes';
import { SFX_ENABLED } from '../data/sfx';
import { SUBTITLES } from '../data/subtitles';
import { SCENE_TRANSITION_FRAMES, TOTAL_FRAMES } from '../data/video';
import { SCENE_COMPONENTS } from '../scenes';
import { ensureFontsLoaded } from '../styles/fonts';

ensureFontsLoaded();

const SceneBody: React.FC<{ scene: SceneTiming }> = ({ scene }) => {
  const Component = SCENE_COMPONENTS[scene.id];
  return Component ? <Component scene={scene} /> : <PlaceholderScene scene={scene} />;
};

/** Lapisan "lensa" global: sama di semua scene supaya grading terasa satu film. */
const LensFinish: React.FC = () => (
  <>
    <Vignette strength={0.5} />
    <FilmGrain opacity={0.06} />
  </>
);

/**
 * Timeline utama 7.200 frame. Semua posisi berasal dari data/scenes.ts —
 * komponen ini hanya merakit, tidak menyimpan angka waktu sendiri.
 */
export const IoTAgriculture: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    {SCENE_TIMINGS.map((scene, i) => {
      const next = SCENE_TIMINGS[i + 1];
      // Scene diperpanjang selama transisi ke scene berikutnya (kecuali scene terakhir).
      const overhang = next ? SCENE_TRANSITION_FRAMES : 0;
      const length = Math.min(scene.durationInFrames + overhang, TOTAL_FRAMES - scene.startFrame);
      return (
        <Sequence
          key={scene.id}
          name={`${scene.number}. ${scene.title}`}
          from={scene.startFrame}
          durationInFrames={length}
        >
          <SceneShell
            durationInFrames={scene.durationInFrames}
            transitionFrames={SCENE_TRANSITION_FRAMES}
            transitionIn={scene.transitionIn}
            transitionOut={next?.transitionIn ?? null}
          >
            <SceneBody scene={scene} />
          </SceneShell>
        </Sequence>
      );
    })}
    <LensFinish />
    <Subtitles cues={SUBTITLES} />
    <Soundtrack />
    {SFX_ENABLED ? <SoundEffects /> : null}
  </AbsoluteFill>
);

/**
 * Satu scene saja (untuk preview & render cepat per-scene di Studio).
 * Subtitle tetap memakai waktu absolut lewat `offset`.
 */
export const SingleScene: React.FC<{ sceneId: SceneTiming['id'] }> = ({ sceneId }) => {
  const scene = SCENE_TIMINGS.find((s) => s.id === sceneId);
  if (!scene) throw new Error(`Scene tidak dikenal: ${sceneId}`);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <SceneShell
        durationInFrames={scene.durationInFrames}
        transitionFrames={SCENE_TRANSITION_FRAMES}
        transitionIn={scene.number === 1 ? 'fade' : 'cut'}
        transitionOut={null}
      >
        <SceneBody scene={scene} />
      </SceneShell>
      <LensFinish />
      <Subtitles cues={SUBTITLES} offset={scene.startFrame} />
      <Soundtrack offset={scene.startFrame} />
      {SFX_ENABLED ? <SoundEffects offset={scene.startFrame} /> : null}
    </AbsoluteFill>
  );
};
