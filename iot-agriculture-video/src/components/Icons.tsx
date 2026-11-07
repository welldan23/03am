import { colors } from '../styles/theme';

/** Ikon garis sederhana (viewBox 48×48). Sengaja polos agar serasi dengan tipografi. */
export type IconName = 'sensor' | 'gateway' | 'cloud' | 'phone' | 'valve' | 'drone' | 'sun' | 'drop' | 'leaf' | 'alert' | 'chart' | 'coin' | 'signal' | 'people';

const PATHS: Record<IconName, string> = {
  sensor: 'M24 6v22 M18 28h12v8l-6 6-6-6z M14 14a14 14 0 0 1 20 0 M10 9a20 20 0 0 1 28 0',
  gateway: 'M24 16v26 M14 42h20 M24 16l-8 26 M24 16l8 26 M17 9a10 10 0 0 0 0 14 M31 9a10 10 0 0 1 0 14 M24 12a4 4 0 1 1 0 8a4 4 0 1 1 0-8',
  cloud: 'M14 36h22a8 8 0 0 0 0-16a12 12 0 0 0-23 3a7 7 0 0 0 1 13z M18 30h12 M18 25h8',
  phone: 'M15 5h18a3 3 0 0 1 3 3v32a3 3 0 0 1-3 3H15a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z M21 38h6 M17 14h14v16H17z M20 26l4-5 3 3 2-3',
  valve: 'M4 30h12 M32 30h12 M16 22v16h16V22z M24 22V12 M16 10h16',
  drone: 'M18 22h12v6H18z M24 22v-4 M8 18h12 M28 18h12 M14 18v-3 M34 18v-3 M20 28l-4 6 M28 28l4 6 M24 28v12',
  sun: 'M24 16a8 8 0 1 1 0 16a8 8 0 1 1 0-16 M24 4v6 M24 38v6 M4 24h6 M38 24h6 M10 10l4 4 M34 34l4 4 M38 10l-4 4 M10 38l4-4',
  drop: 'M24 6c8 11 12 17 12 23a12 12 0 0 1-24 0c0-6 4-12 12-23z',
  leaf: 'M10 38c0-18 10-28 30-30c-1 20-11 30-30 30z M10 38l16-16',
  alert: 'M24 6l20 36H4z M24 18v12 M24 35v2',
  chart: 'M6 40h36 M10 34l9-10 7 6 12-14 M33 16h5v5',
  coin: 'M24 8a16 16 0 1 1 0 32a16 16 0 1 1 0-32 M24 15v18 M29 18c-1-2-3-3-5-3c-3 0-5 2-5 4c0 5 10 3 10 9c0 2-2 4-5 4c-2 0-4-1-5-3',
  signal: 'M8 40V34 M17 40V27 M26 40V20 M35 40V12 M6 8l36 32',
  people: 'M17 18a6 6 0 1 1 0-12a6 6 0 1 1 0 12 M5 40c0-8 5-14 12-14s12 6 12 14 M33 20a5 5 0 1 1 0-10a5 5 0 1 1 0 10 M31 26c7 0 12 5 12 12',
};

export const Icon: React.FC<{ name: IconName; size?: number; color?: string; strokeWidth?: number }> = ({
  name,
  size = 48,
  color = colors.paper,
  strokeWidth = 2.2,
}) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    <path d={PATHS[name]} stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
