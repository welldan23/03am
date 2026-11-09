import { AbsoluteFill, Sequence } from 'remotion';
import { FilmGrain, Vignette } from '../components/FilmLook';
import { PlaceholderScene } from '../components/PlaceholderScene';
import { SceneShell } from '../components/SceneShell';
import { Soundtrack } from '../components/Soundtrack';
import { Subtitles } from '../components/Subtitles';
import type { VoiceoverClip } from '../data/voiceover';
import { SCENE_TRANSITION_FRAMES } from '../data/video';
import type { Cue, FilmScene, MusicPlacement } from '../lib/film';
import type { SceneProps } from '../scenes/types';
import { ensureFontsLoaded } from '../styles/fonts';

ensureFontsLoaded();

export interface FilmDefinition {
  totalFrames: number;
  scenes: readonly FilmScene[];
  components: Readonly<Record<string, React.FC<SceneProps>>>;
  cues: readonly Cue[];
  music: readonly MusicPlacement[];
  voiceover: readonly VoiceoverClip[];
}

const LensFinish: React.FC = () => (
  <>
    <Vignette strength={0.5} />
    <FilmGrain opacity={0.06} />
  </>
);

const Body: React.FC<{ film: FilmDefinition; scene: FilmScene }> = ({ film, scene }) => {
  const C = film.components[scene.id];
  return C ? <C scene={scene} /> : <PlaceholderScene scene={scene} />;
};

/** Timeline penuh sebuah film — semua posisi berasal dari definisi film. */
export const FilmTimeline: React.FC<{ film: FilmDefinition }> = ({ film }) => (
  <AbsoluteFill style={{ backgroundColor: '#000' }}>
    {film.scenes.map((scene, i) => {
      const next = film.scenes[i + 1];
      const overhang = next ? SCENE_TRANSITION_FRAMES : 0;
      const length = Math.min(scene.durationInFrames + overhang, film.totalFrames - scene.startFrame);
      return (
        <Sequence key={scene.id} name={`${scene.number}. ${scene.title}`} from={scene.startFrame} durationInFrames={length}>
          <SceneShell
            durationInFrames={scene.durationInFrames}
            transitionFrames={SCENE_TRANSITION_FRAMES}
            transitionIn={scene.transitionIn}
            transitionOut={next?.transitionIn ?? null}
          >
            <Body film={film} scene={scene} />
          </SceneShell>
        </Sequence>
      );
    })}
    <LensFinish />
    <Subtitles cues={film.cues} />
    <Soundtrack tracks={film.music} clips={film.voiceover} />
  </AbsoluteFill>
);

/** Satu scene saja, untuk preview cepat di Studio. */
export const FilmSingleScene: React.FC<{ film: FilmDefinition; sceneId: string }> = ({ film, sceneId }) => {
  const scene = film.scenes.find((s) => s.id === sceneId);
  if (!scene) throw new Error(`Scene tidak dikenal: ${sceneId}`);
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <SceneShell
        durationInFrames={scene.durationInFrames}
        transitionFrames={SCENE_TRANSITION_FRAMES}
        transitionIn={scene.number === 1 ? 'fade' : 'cut'}
        transitionOut={null}
      >
        <Body film={film} scene={scene} />
      </SceneShell>
      <LensFinish />
      <Subtitles cues={film.cues} offset={scene.startFrame} />
      <Soundtrack offset={scene.startFrame} tracks={film.music} clips={film.voiceover} />
    </AbsoluteFill>
  );
};
