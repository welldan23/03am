/**
 * Angka faktual yang tampil di layar. Setiap angka WAJIB punya sumber.
 * Verifikasi ulang ke sumber resmi sebelum video dipublikasikan.
 */
export interface Fact {
  value: string;
  unit: string;
  label: string;
  source: string;
}

export const FACTS = {
  riceFieldArea: {
    value: '7,46',
    unit: 'juta ha',
    label: 'lahan baku sawah nasional',
    source: 'Kementerian ATR/BPN, 2019',
  },
  farmHouseholds: {
    value: '28,4',
    unit: 'juta',
    label: 'rumah tangga usaha pertanian',
    source: 'BPS, Sensus Pertanian 2023',
  },
} as const satisfies Record<string, Fact>;
