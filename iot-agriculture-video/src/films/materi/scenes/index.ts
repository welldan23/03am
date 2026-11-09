import type { SceneProps } from '../../../scenes/types';
import { M01Opening } from './M01Opening';
import { M02WhatIsIoT } from './M02WhatIsIoT';
import { M03Architecture } from './M03Architecture';
import { M04Sensors } from './M04Sensors';
import { M05Rice } from './M05Rice';
import { M06Greenhouse } from './M06Greenhouse';
import { M07Livestock } from './M07Livestock';
import { M08Plantation } from './M08Plantation';
import { M09Dashboard } from './M09Dashboard';
import { M10Start } from './M10Start';
import { M11Closing } from './M11Closing';

export const MATERI_COMPONENTS: Readonly<Record<string, React.FC<SceneProps>>> = {
  'm-opening': M01Opening,
  'm-what': M02WhatIsIoT,
  'm-arch': M03Architecture,
  'm-sensors': M04Sensors,
  'm-rice': M05Rice,
  'm-greenhouse': M06Greenhouse,
  'm-livestock': M07Livestock,
  'm-plantation': M08Plantation,
  'm-dashboard': M09Dashboard,
  'm-start': M10Start,
  'm-closing': M11Closing,
};
