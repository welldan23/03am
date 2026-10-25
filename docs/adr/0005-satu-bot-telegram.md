# ADR-0005 — Satu Bot Telegram Milik Studio, Hermes Tanpa Gateway Telegram

| | |
|---|---|
| Status | **Diterima** (2026-10-25) — menggantikan rekomendasi "dua bot" di draft v0.1 |
| Konteks fase | Berlaku mulai Fase 3 (Telegram) dan Fase 5 (Hermes) |
| Ditinjau ulang bila | Spike Hermes (awal Fase 5) membuktikan mode headless tidak bisa dipakai |

## Konteks

- Satu token bot Telegram hanya boleh di-poll oleh **satu proses**. Proses kedua yang memanggil `getUpdates` dengan token yang sama akan kena error `409 Conflict`.
- Hermes Agent punya gateway Telegram sendiri yang ikut melakukan polling kalau diberi token bot.
- Approval (G0–G3) **wajib** lewat jalur deterministik. Approval tidak boleh pernah melewati LLM.
- Owner cuma satu orang. Antarmuka harus sesederhana mungkin.
- Semua token LLM yang dipakai Hermes wajib dihitung ke anggaran (lihat ADR-0009).

## Opsi yang Dievaluasi

| Kriteria | A. Satu bot milik Studio | B. Dua bot (Studio + Hermes) | C. Satu bot milik Hermes |
|---|---|---|---|
| Konflik polling | **Tidak mungkin terjadi** (hanya Studio yang polling; Hermes tidak diberi token bot) | Aman selama tokennya beda, tapi gampang salah konfigurasi | Tidak ada konflik |
| Keamanan approval | Tombol approval ditangani handler Studio, tidak pernah sampai ke LLM | Sama amannya | ❌ Approval lewat LLM |
| Kesederhanaan bagi owner | **1 chat** | 2 chat (atau 1 grup) | 1 chat |
| Kesederhanaan operasional | 1 token, 1 allowlist, 1 proses Telegram | 2 token, 2 allowlist, 2 proses Telegram | 1 token |
| Kontrol biaya Hermes | Studio memanggil Hermes untuk tiap giliran Director, jadi bisa dibatasi dan dimeter | Hermes jalan sendiri 24/7; giliran percakapan tidak lewat Studio | Sulit |
| Ketergantungan ke fitur Hermes | Butuh mode **headless** Hermes (single-query/CLI atau API lokal) — **[verifikasi di spike]** | Memakai gateway Hermes apa adanya | Memakai gateway |
| Kerusakan berantai | Kalau Hermes mati, bot & approval tetap jalan (Director membalas "sedang tidak tersedia") | Sama | Kalau Hermes mati, semuanya mati |

## Keputusan

**Opsi A: satu bot Telegram ("Studio Bot") yang dimiliki dan di-poll hanya oleh proses Studio.**

1. Gateway Telegram Hermes **tidak diaktifkan**. Hermes tidak pernah menerima token bot. Akibatnya konflik polling mustahil terjadi, bukan sekadar "dihindari".
2. Studio Bot membagi update yang masuk secara deterministik:
   - **Callback tombol** (approve/revisi/tolak) → handler `approvals` di Studio. Tidak pernah diteruskan ke Director.
   - **Perintah** (`/status`, `/budget`, …) → handler Studio.
   - **Teks bebas** dari owner → `DirectorPort.handle_message()` → adapter Hermes (headless) → balasan dikirim balik oleh Studio Bot.
3. Hermes memanggil kemampuan Studio lewat MCP server stdio (ADR-0004). Di MCP itu tidak ada tool untuk approval, budget, atau ekspor.
4. Semua panggilan LLM Hermes lewat gateway metering Studio (ADR-0009).
5. Saat Hermes tidak tersedia, Studio Bot tetap melayani perintah dan approval.

## Rencana Cadangan

Kalau spike awal Fase 5 menunjukkan Hermes tidak bisa dipanggil headless dengan andal, kita pindah ke **Opsi B** (dua bot, token berbeda) dengan syarat tetap sama: approval hanya di Studio Bot, LLM Hermes tetap lewat gateway metering, dan startup Studio menolak jalan kalau token Studio Bot sama dengan token Hermes.

## Konsekuensi

- (+) Owner cukup pakai satu chat; satu allowlist; satu titik audit.
- (+) Setiap giliran Director lewat Studio, jadi bisa dibatasi (rate limit, budget) dan dicatat.
- (−) Fitur khusus gateway Hermes (misalnya pengiriman cron ke Telegram) tidak dipakai. Notifikasi terjadwal dikirim oleh Studio.
- (−) Integrasi bergantung pada mode headless Hermes, sehingga perlu contract test dan versi Hermes di-pin.
