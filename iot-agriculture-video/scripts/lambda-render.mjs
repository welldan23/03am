#!/usr/bin/env node
/**
 * Render OPSIONAL di AWS Lambda.
 *
 * ⚠  Skrip ini bisa membuat resource AWS (Lambda function, bucket S3) dan
 *    menimbulkan BIAYA. Secara default ia hanya mencetak rencana (dry-run).
 *    Eksekusi sungguhan butuh DUA hal sekaligus:
 *      1. flag  --i-approve-aws-costs
 *      2. env   REMOTION_LAMBDA_CONFIRM=yes
 *
 * Kredensial dibaca dari env (REMOTION_AWS_ACCESS_KEY_ID / REMOTION_AWS_SECRET_ACCESS_KEY)
 * dan TIDAK pernah dicetak.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const hit = args.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.split('=').slice(1).join('=') : fallback;
};

const plan = {
  region: flag('region', process.env.REMOTION_AWS_REGION ?? 'ap-southeast-1'),
  composition: flag('composition', 'IoTAgriculture'),
  memorySizeInMb: Number(flag('memory', '3008')),
  timeoutInSeconds: Number(flag('timeout', '300')),
  diskSizeInMb: 4096,
  framesPerLambda: Number(flag('frames-per-lambda', '240')),
  siteName: flag('site', 'iot-pertanian'),
  codec: 'h264',
  crf: 18,
};

const approved = args.includes('--i-approve-aws-costs') && process.env.REMOTION_LAMBDA_CONFIRM === 'yes';
const hasKeys = Boolean(process.env.REMOTION_AWS_ACCESS_KEY_ID && process.env.REMOTION_AWS_SECRET_ACCESS_KEY);

console.log('\nRencana render Lambda');
console.table(plan);
console.log(`Kredensial AWS terdeteksi : ${hasKeys ? 'ya' : 'TIDAK'}`);
console.log(`Persetujuan biaya         : ${approved ? 'YA' : 'tidak (dry-run)'}`);
console.log(`Perkiraan jumlah Lambda   : ${Math.ceil(7200 / plan.framesPerLambda)} worker untuk 7.200 frame\n`);

if (!approved) {
  console.log('Dry-run selesai. Tidak ada resource AWS yang dibuat dan tidak ada biaya.');
  console.log('Untuk eksekusi sungguhan (setelah owner menyetujui biaya):');
  console.log('  REMOTION_LAMBDA_CONFIRM=yes node scripts/lambda-render.mjs --i-approve-aws-costs\n');
  process.exit(0);
}
if (!hasKeys) {
  console.error('Set REMOTION_AWS_ACCESS_KEY_ID dan REMOTION_AWS_SECRET_ACCESS_KEY dulu (lihat README).');
  process.exit(1);
}

const { deployFunction, deploySite, getOrCreateBucket, renderMediaOnLambda, getRenderProgress } = await import(
  '@remotion/lambda'
);

console.log('1/4 Menyiapkan fungsi Lambda…');
const { functionName } = await deployFunction({
  region: plan.region,
  memorySizeInMb: plan.memorySizeInMb,
  timeoutInSeconds: plan.timeoutInSeconds,
  diskSizeInMb: plan.diskSizeInMb,
  createCloudWatchLogGroup: true,
});

console.log('2/4 Menyiapkan bucket S3…');
const { bucketName } = await getOrCreateBucket({ region: plan.region });

console.log('3/4 Mengunggah bundle situs…');
const { serveUrl } = await deploySite({
  entryPoint: path.join(root, 'src/index.ts'),
  bucketName,
  region: plan.region,
  siteName: plan.siteName,
});

console.log('4/4 Memulai render…');
const { renderId } = await renderMediaOnLambda({
  region: plan.region,
  functionName,
  serveUrl,
  composition: plan.composition,
  codec: plan.codec,
  crf: plan.crf,
  framesPerLambda: plan.framesPerLambda,
  privacy: 'private',
  downloadBehavior: { type: 'download', fileName: 'iot-pertanian.mp4' },
});

for (;;) {
  await new Promise((r) => setTimeout(r, 5000));
  const p = await getRenderProgress({ renderId, bucketName, functionName, region: plan.region });
  if (p.fatalErrorEncountered) {
    console.error('Render gagal:', p.errors?.[0]?.message);
    process.exit(1);
  }
  process.stdout.write(`\r   progres ${(p.overallProgress * 100).toFixed(1)}%   biaya sejauh ini ${p.costs?.displayCost ?? '?'}`);
  if (p.done) {
    console.log(`\nSelesai → ${p.outputFile}`);
    break;
  }
}
