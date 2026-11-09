import { Composition, Folder } from 'remotion';
import { IoTAgriculture, SingleScene } from './compositions/IoTAgriculture';
import { MateriScene, MateriTimeline } from './films/materi/compositions';
import { MATERI_SCENES, MATERI_TOTAL_FRAMES } from './films/materi/timeline';
import { SCENE_TIMINGS } from './data/scenes';
import { FPS, HEIGHT, TOTAL_FRAMES, WIDTH } from './data/video';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="IoTAgriculture"
      component={IoTAgriculture}
      durationInFrames={TOTAL_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
    <Folder name="Per-Scene">
      {SCENE_TIMINGS.map((scene) => (
        <Composition
          key={scene.id}
          id={scene.compositionId}
          component={SingleScene}
          defaultProps={{ sceneId: scene.id }}
          durationInFrames={scene.durationInFrames}
          fps={FPS}
          width={WIDTH}
          height={HEIGHT}
        />
      ))}
    </Folder>

    {/* Film 2 — materi lengkap 8 menit */}
    <Composition
      id="MateriIoT8Menit"
      component={MateriTimeline}
      durationInFrames={MATERI_TOTAL_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
    <Folder name="Materi-Per-Scene">
      {MATERI_SCENES.map((scene) => (
        <Composition
          key={scene.id}
          id={scene.compositionId}
          component={MateriScene}
          defaultProps={{ sceneId: scene.id }}
          durationInFrames={scene.durationInFrames}
          fps={FPS}
          width={WIDTH}
          height={HEIGHT}
        />
      ))}
    </Folder>
  </>
);
