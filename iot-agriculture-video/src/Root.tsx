import { Composition, Folder } from 'remotion';
import { IoTAgriculture, SingleScene } from './compositions/IoTAgriculture';
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
  </>
);
