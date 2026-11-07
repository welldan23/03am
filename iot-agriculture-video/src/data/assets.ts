import { staticFile } from 'remotion';
import credits from './credits.generated.json';

/**
 * Semua foto berasal dari Wikimedia Commons dengan lisensi bebas (CC BY / CC BY-SA / CC0).
 * Metadata lisensi dibuat otomatis oleh `npm run fetch-assets` → credits.generated.json.
 */
export interface AssetCredit {
  id: string;
  file: string;
  title: string;
  author: string;
  license: string;
  licenseUrl: string | null;
  sourceUrl: string;
  width: number;
  height: number;
}

export const CREDITS: readonly AssetCredit[] = credits;

export type PhotoId =
  | 'dawnPaddy'
  | 'jatiluwihWide'
  | 'tegallalang'
  | 'farmerHarvest'
  | 'jatiluwihPanorama';

export const photo = (id: PhotoId): AssetCredit & { src: string } => {
  const c = CREDITS.find((x) => x.id === id);
  if (!c) throw new Error(`Aset tidak ada di credits.generated.json: ${id}. Jalankan npm run fetch-assets.`);
  return { ...c, src: staticFile(`assets/${c.file}`) };
};

export const GRAIN_TEXTURE = staticFile('assets/images/grain.png');
