import { staticFile } from 'remotion';
import credits from './credits.generated.json';

/**
 * Semua foto berlisensi bebas (CC0 / Public domain / CC BY / CC BY-SA) dari Wikimedia
 * Commons atau Openverse. Cari dengan `npm run search-photos`, unduh dengan
 * `npm run fetch-assets` → credits.generated.json (dimensi dibaca dari file asli).
 */
export interface AssetCredit {
  id: string;
  file: string;
  provider: string;
  title: string;
  author: string;
  license: string;
  licenseUrl: string | null;
  sourceUrl: string;
  width: number;
  height: number;
}

export const CREDITS: readonly AssetCredit[] = credits;

/** id = kolom `id` di scripts/asset-sources.json. `npm run verify` mengecek semua pemakaian. */
export const photo = (id: string): AssetCredit & { src: string } => {
  const c = CREDITS.find((x) => x.id === id);
  if (!c) throw new Error(`Aset tidak ada di credits.generated.json: ${id}. Jalankan npm run fetch-assets.`);
  return { ...c, src: staticFile(`assets/${c.file}`) };
};

export const GRAIN_TEXTURE = staticFile('assets/images/grain.png');
