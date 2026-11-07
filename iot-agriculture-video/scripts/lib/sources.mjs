// Sumber foto berlisensi bebas tanpa API key: Wikimedia Commons + Openverse.
// Dipakai bersama oleh search-photos.mjs (mencari) dan fetch-assets.mjs (mengunduh).

export const UA = 'IoTPertanianDocBuilder/0.1 (educational documentary; Remotion)';
const COMMONS_API = 'https://commons.wikimedia.org/w/api.php';
const OPENVERSE_API = 'https://api.openverse.org/v1/images/';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const stripHtml = (s) =>
  String(s ?? '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();

/** GET dengan retry + backoff eksponensial (Commons/Flickr sering membalas 429). */
export async function http(url, { json = true, tries = 5 } = {}) {
  let last = '';
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, { headers: { 'User-Agent': UA, Accept: json ? 'application/json' : '*/*' } });
      if (res.ok) {
        if (!json) return Buffer.from(await res.arrayBuffer());
        const text = await res.text();
        try {
          return JSON.parse(text);
        } catch {
          last = 'respons bukan JSON (kemungkinan rate limit)';
        }
      } else {
        last = `HTTP ${res.status}`;
        if (res.status === 404) break;
      }
    } catch (err) {
      last = err instanceof Error ? err.message : String(err);
    }
    if (i < tries - 1) await sleep(2000 * 2 ** i);
  }
  throw new Error(`Gagal mengambil ${url}: ${last}`);
}

/**
 * Kebijakan lisensi: hanya yang boleh dipakai komersial DAN dimodifikasi
 * (video meng-crop, men-grade, dan menimpa teks). NC/ND/tidak jelas = ditolak.
 * Mengembalikan label rapi, atau null kalau ditolak.
 */
export function acceptLicense(raw, version = '') {
  const s = String(raw ?? '').trim().toLowerCase();
  if (!s) return null;
  if (/\b(nc|nd)\b|noncommercial|noderiv/.test(s)) return null;
  if (s === 'cc0' || s.startsWith('cc0')) return 'CC0';
  if (s === 'pdm' || s.startsWith('public domain') || s === 'pd' || s.startsWith('pd-')) return 'Public domain';
  if (s === 'by-sa' || s.startsWith('cc by-sa')) return s.startsWith('cc') ? raw.trim() : `CC BY-SA ${version}`.trim();
  if (s === 'by' || s.startsWith('cc by')) return s.startsWith('cc') ? raw.trim() : `CC BY ${version}`.trim();
  return null;
}

// ── Wikimedia Commons ────────────────────────────────────────────────────

/** Info satu file Commons, termasuk URL thumbnail selebar `width`. */
export async function commonsInfo(title, width) {
  const params = new URLSearchParams({
    action: 'query',
    titles: title,
    prop: 'imageinfo',
    iiprop: 'url|size|mime|extmetadata',
    iiurlwidth: String(width),
    iiextmetadatafilter: 'LicenseShortName|LicenseUrl|Artist',
    format: 'json',
  });
  const data = await http(`${COMMONS_API}?${params}`);
  const page = Object.values(data.query?.pages ?? {})[0];
  const ii = page?.imageinfo?.[0];
  if (!ii) throw new Error(`File Commons tidak ditemukan: ${title}`);
  const m = ii.extmetadata ?? {};
  // Thumbnail Commons maksimal 3840px. Butuh lebih besar (mis. panorama) → ambil file asli,
  // nanti diperkecil sendiri oleh fetch-assets.
  // Untuk audio/video, "thumburl" hanyalah ikon PNG — selalu ambil file asli.
  const isImage = String(ii.mime ?? '').startsWith('image/');
  const useOriginal = !isImage || width > 3840 || !ii.thumburl;
  return {
    title: title.replace(/^File:/, ''),
    author: stripHtml(m.Artist?.value),
    licenseRaw: m.LicenseShortName?.value ?? '',
    license: acceptLicense(m.LicenseShortName?.value),
    licenseUrl: m.LicenseUrl?.value ?? null,
    pageUrl: ii.descriptionurl,
    width: ii.width,
    height: ii.height,
    duration: ii.duration ?? null,
    downloadUrl: useOriginal ? ii.url : ii.thumburl,
  };
}

export async function searchCommons(query, limit) {
  const params = new URLSearchParams({
    action: 'query',
    generator: 'search',
    gsrsearch: `${query} filetype:bitmap`,
    gsrnamespace: '6',
    gsrlimit: String(Math.min(50, limit * 3)),
    prop: 'imageinfo',
    iiprop: 'url|size|extmetadata',
    iiurlwidth: '480',
    iiextmetadatafilter: 'LicenseShortName|LicenseUrl|Artist',
    format: 'json',
  });
  const data = await http(`${COMMONS_API}?${params}`);
  return Object.values(data.query?.pages ?? {})
    .sort((a, b) => (a.index ?? 0) - (b.index ?? 0))
    .map((p) => {
      const ii = p.imageinfo?.[0] ?? {};
      const m = ii.extmetadata ?? {};
      return {
        provider: 'commons',
        ref: p.title,
        title: p.title.replace(/^File:/, ''),
        author: stripHtml(m.Artist?.value),
        licenseRaw: m.LicenseShortName?.value ?? '',
        license: acceptLicense(m.LicenseShortName?.value),
        pageUrl: ii.descriptionurl,
        width: ii.width ?? 0,
        height: ii.height ?? 0,
        thumb: ii.thumburl,
      };
    });
}

// ── Openverse (Flickr, museum, dll.) ─────────────────────────────────────

const OV_LICENSES = 'cc0,pdm,by,by-sa';

function fromOpenverse(r) {
  return {
    provider: 'openverse',
    ref: r.id,
    source: r.source,
    title: stripHtml(r.title) || '(tanpa judul)',
    author: stripHtml(r.creator) || '',
    licenseRaw: `${r.license} ${r.license_version ?? ''}`.trim(),
    license: acceptLicense(r.license, r.license_version),
    licenseUrl: r.license_url ?? null,
    pageUrl: r.foreign_landing_url ?? r.detail_url,
    width: r.width ?? 0,
    height: r.height ?? 0,
    thumb: r.thumbnail,
    downloadUrl: r.url,
  };
}

export async function searchOpenverse(query, limit) {
  const params = new URLSearchParams({
    q: query,
    license: OV_LICENSES,
    page_size: String(Math.min(20, limit * 2)),
    mature: 'false',
  });
  const data = await http(`${OPENVERSE_API}?${params}`);
  // Hasil yang asalnya Wikimedia dilewati: sudah tercakup pencarian Commons,
  // dan lewat Commons kita bisa minta ukuran thumbnail yang pas.
  return (data.results ?? []).filter((r) => r.source !== 'wikimedia').map(fromOpenverse);
}

export async function openverseInfo(id) {
  const r = await http(`${OPENVERSE_API}${encodeURIComponent(id)}/`);
  return fromOpenverse(r);
}
