import type { SceneId } from '../data/scenes';
import { Scene01Intro } from './Scene01Intro';
import { Scene02IoT } from './Scene02IoT';
import { Scene03Sensors } from './Scene03Sensors';
import { Scene04Irrigation } from './Scene04Irrigation';
import { Scene05Drones } from './Scene05Drones';
import { Scene06Dashboard } from './Scene06Dashboard';
import { Scene07Benefits } from './Scene07Benefits';
import { Scene08Future } from './Scene08Future';
import type { SceneProps } from './types';

/**
 * Registry scene → komponen. Scene yang tidak ada di sini otomatis dirender
 * sebagai PlaceholderScene, sehingga timeline penuh selalu bisa di-preview.
 */
export const SCENE_COMPONENTS: Partial<Record<SceneId, React.FC<SceneProps>>> = {
  intro: Scene01Intro,
  'iot-basics': Scene02IoT,
  sensors: Scene03Sensors,
  irrigation: Scene04Irrigation,
  drones: Scene05Drones,
  dashboard: Scene06Dashboard,
  benefits: Scene07Benefits,
  future: Scene08Future,
};
