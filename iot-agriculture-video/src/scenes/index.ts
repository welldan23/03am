import type { SceneId } from '../data/scenes';
import { Scene01Intro } from './Scene01Intro';
import type { SceneProps } from './types';

/**
 * Registry scene → komponen. Scene yang belum ada di sini otomatis dirender
 * sebagai PlaceholderScene, sehingga timeline penuh selalu bisa di-preview.
 */
export const SCENE_COMPONENTS: Partial<Record<SceneId, React.FC<SceneProps>>> = {
  intro: Scene01Intro,
};
