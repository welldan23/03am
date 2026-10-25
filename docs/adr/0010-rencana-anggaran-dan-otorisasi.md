# ADR-0010 — Rencana Anggaran Bulanan, Kurs, dan Otorisasi Belanja

| | |
|---|---|
| Status | **Diterima** (2026-10-25) |
| Implementasi | Fase 1 (`studio.modules.budget`, `config/budget.yaml`) |

## Konteks

- Batas total Rp500.000/bulan **sudah termasuk** VPS, LLM, TTS, dan video.
- Harga provider dalam USD, sedangkan anggaran dalam Rupiah. Kurs bisa berubah.
- Biaya VPS belum pasti (VPS belum dibeli).
- "Semua pengeluaran wajib lewat persetujuan manusia", tapi panggilan LLM untuk riset/naskah terjadi **sebelum** G2 (approval biaya produksi).

## Keputusan

### 1. Rencana anggaran ada di config, bukan di kode

`config/budget.yaml` berisi kurs (`fx.usd_idr` + tanggal + sumber), biaya VPS (`vps.planned_usd`, `vps.actual_usd`), dan alokasi per kategori dalam **integer Rupiah**. Rencana awal (kurs asumsi Rp17.850/USD):

| Pos | Rupiah |
|---|---|
| VPS (USD 9,50) | 169.575 |
| Higgsfield | 190.000 |
| OpenAI (termasuk Hermes) | 60.000 |
| TTS | 25.000 |
| Cadangan | 55.425 |
| **Total** | **500.000** |

Validasi otomatis:
- `ceil(vps_usd × kurs) + Σ alokasi ≤ monthly_budget_idr`. Kalau lewat → rencana **tidak valid** dan semua belanja baru ditolak.
- Kalau `vps.actual_usd` sudah diisi dan berbeda dari `planned_usd` → rencana ditandai **perlu dihitung ulang**. Provider berbayar tidak bisa diaktifkan sampai owner menyetujui alokasi baru. Perintah `studio budget recalc --vps-usd X` membuat usulan: selisih diambil dari cadangan dulu, kalau kurang baru dari alokasi variabel secara proporsional. Usulan ini **tidak** ditulis otomatis.
- Aktivasi provider berbayar juga butuh `vps.actual_usd` terisi dan sama dengan `planned_usd`. Selama VPS belum ada, API berbayar memang tidak bisa diaktifkan.

### 2. Periode bulanan diaktifkan manusia

- Belanja apa pun (termasuk simulasi dari mock) butuh **periode aktif** (`YYYY-MM`, zona Asia/Jakarta) yang diaktifkan owner (`studio budget activate`).
- Saat aktivasi, rencana (alokasi + kurs) disimpan sebagai **snapshot**. Mengubah config tidak mengubah periode berjalan sampai owner mengaktifkan ulang (tercatat di audit log).
- **Cadangan tidak bisa dibelanjakan.** Yang bisa dibelanjakan hanya alokasi `higgsfield`, `openai`, dan `tts`.

### 3. Otorisasi belanja (spend authorization)

Setiap reservasi wajib menunjuk satu otorisasi aktif. Semua otorisasi lahir dari tindakan manusia:

| Jenis | Dibuat saat | Batas | Dipakai untuk |
|---|---|---|---|
| `operational` | Owner mengaktifkan periode | `limits.operational_cap_idr` per bulan | Percakapan Hermes, discovery topik |
| `preproduction` | Owner menyetujui G0 (pilih topik) | `limits.preproduction_cap_idr` per episode (tampil di kartu G0) | LLM untuk riset, cek fakta, naskah, storyboard |
| `production` | Owner menyetujui G2 | `ceil(estimasi × (1 + margin))` (tampil di kartu G2) | Gambar, video, TTS |

Otorisasi dicabut kalau approval asalnya digantikan (revisi) atau episode dibatalkan.

### 4. Aturan reservasi (`BudgetGuard.reserve`)

Ditolak kalau salah satu terjadi: mode `real` tapi kill switch mati atau syarat aktivasi berbayar belum terpenuhi; rencana tidak valid; periode tidak aktif; otorisasi tidak aktif atau sisanya kurang; sisa alokasi kategori kurang; sisa total yang bisa dibelanjakan kurang. Setiap penolakan dicatat di audit log.

Ledger mode `simulated` (mock) dan `real` dihitung **terpisah** dengan aturan yang sama, supaya alur uang teruji tanpa uang sungguhan.

### 5. Pencatatan uang

- Rupiah = `int`. USD = `int` mikro-dolar (1 USD = 1.000.000). Kurs = `Decimal`. Tidak ada `float`.
- Konversi USD → IDR selalu **dibulatkan ke atas**.
- Setiap estimasi dan setiap entri ledger menyimpan **kurs yang dipakai** dan versi tabel harga.

## Konsekuensi

- (+) Tidak ada belanja tanpa jejak keputusan manusia.
- (+) Perubahan kurs atau biaya VPS tidak bisa diam-diam menembus batas Rp500.000.
- (−) Owner perlu mengaktifkan periode tiap bulan (satu perintah).
- (−) Biaya pra-produksi dibatasi per episode. Kalau habis, episode gagal dengan alasan jelas dan owner harus memutuskan.
