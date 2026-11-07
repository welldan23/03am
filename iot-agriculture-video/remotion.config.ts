// Konfigurasi CLI Remotion (studio & render lokal). Render Lambda memakai
// opsi yang sama lewat scripts/lambda-render.mjs.
import { Config } from '@remotion/cli/config';

Config.setEntryPoint('src/index.ts');
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(92);
Config.setOverwriteOutput(true);
Config.setPixelFormat('yuv420p');

// Opsional: pakai Chrome/Chromium yang sudah terpasang (CI, container tanpa internet).
if (process.env.REMOTION_BROWSER_EXECUTABLE) {
  Config.setBrowserExecutable(process.env.REMOTION_BROWSER_EXECUTABLE);
}
