import { tc } from '../lib/time';

export type TransitionStyle = 'cut' | 'fade' | 'blur-dissolve' | 'dip-to-black' | 'light-wipe';

export type SceneId =
  | 'intro'
  | 'iot-basics'
  | 'sensors'
  | 'irrigation'
  | 'drones'
  | 'dashboard'
  | 'benefits'
  | 'future';

export interface SceneConfig {
  id: SceneId;
  number: number;
  /** Nama komposisi mandiri di Remotion Studio (huruf, angka, dan '-'). */
  compositionId: string;
  title: string;
  kicker: string;
  /** Rentang waktu storyboard, format mm:ss. */
  start: string;
  end: string;
  /** Transisi yang dipakai saat scene ini MASUK (scene pertama selalu fade dari hitam). */
  transitionIn: TransitionStyle;
  /** false = masih placeholder; diganti saat scene diimplementasikan. */
  implemented: boolean;
}

export const SCENES: readonly SceneConfig[] = [
  {
    id: 'intro',
    number: 1,
    compositionId: 'Scene1-Intro',
    title: 'Sawah Nusantara',
    kicker: 'Pengantar',
    start: '00:00',
    end: '00:30',
    transitionIn: 'fade',
    implemented: true,
  },
  {
    id: 'iot-basics',
    number: 2,
    compositionId: 'Scene2-IoT',
    title: 'Apa Itu Internet of Things?',
    kicker: 'Bab 1',
    start: '00:30',
    end: '01:10',
    transitionIn: 'dip-to-black',
    implemented: false,
  },
  {
    id: 'sensors',
    number: 3,
    compositionId: 'Scene3-Sensors',
    title: 'Sensor Tanah & Lingkungan',
    kicker: 'Bab 2',
    start: '01:10',
    end: '01:50',
    transitionIn: 'blur-dissolve',
    implemented: false,
  },
  {
    id: 'irrigation',
    number: 4,
    compositionId: 'Scene4-Irrigation',
    title: 'Irigasi Otomatis',
    kicker: 'Bab 3',
    start: '01:50',
    end: '02:30',
    transitionIn: 'light-wipe',
    implemented: false,
  },
  {
    id: 'drones',
    number: 5,
    compositionId: 'Scene5-Drones',
    title: 'Drone Pertanian',
    kicker: 'Bab 4',
    start: '02:30',
    end: '03:10',
    transitionIn: 'blur-dissolve',
    implemented: false,
  },
  {
    id: 'dashboard',
    number: 6,
    compositionId: 'Scene6-Dashboard',
    title: 'Dasbor Pertanian Cerdas',
    kicker: 'Bab 5',
    start: '03:10',
    end: '03:50',
    transitionIn: 'light-wipe',
    implemented: false,
  },
  {
    id: 'benefits',
    number: 7,
    compositionId: 'Scene7-Benefits',
    title: 'Manfaat & Tantangan',
    kicker: 'Bab 6',
    start: '03:50',
    end: '04:30',
    transitionIn: 'dip-to-black',
    implemented: false,
  },
  {
    id: 'future',
    number: 8,
    compositionId: 'Scene8-Future',
    title: 'Masa Depan Pertanian Cerdas',
    kicker: 'Penutup',
    start: '04:30',
    end: '05:00',
    transitionIn: 'fade',
    implemented: false,
  },
];

export interface SceneTiming extends SceneConfig {
  startFrame: number;
  endFrame: number;
  durationInFrames: number;
}

export const SCENE_TIMINGS: readonly SceneTiming[] = SCENES.map((s) => {
  const startFrame = tc(s.start);
  const endFrame = tc(s.end);
  return { ...s, startFrame, endFrame, durationInFrames: endFrame - startFrame };
});

export const getScene = (id: SceneId): SceneTiming => {
  const found = SCENE_TIMINGS.find((s) => s.id === id);
  if (!found) throw new Error(`Scene tidak dikenal: ${id}`);
  return found;
};
