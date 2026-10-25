# 03:AM — AI Documentary Studio

Studio produksi dokumenter AI semi-otonom berbasis Telegram. Membuat dokumenter pendek cinematic berbahasa Indonesia (30–180 detik) tentang sejarah, geopolitik, sains, geografi, dan misteri — dengan persetujuan manusia di setiap pengeluaran dan hasil akhir.

> Status: **Fase 3 selesai (bot Telegram)** — menunggu review owner. AI masih mock dan semua biaya simulasi; belum ada provider berbayar, render video, atau deploy.

## Mulai cepat

Butuh Python 3.12+ dan [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
uv run pytest                 # semua test (offline)
uv run studio budget plan     # lihat rencana anggaran
uv run studio --help
uv run studio bot check       # bot Telegram: lihat docs/TELEGRAM_SETUP.md
```

| Dokumen | Isi |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Kebutuhan produk, alur kerja, model biaya |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arsitektur modular monolith, struktur repo, domain |
| [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | Fase pengembangan + acceptance criteria |
| [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md) | Setup & pemakaian bot Telegram, contoh percakapan, troubleshooting |
| [docs/RISKS.md](docs/RISKS.md) | Risiko integrasi Hermes Agent & Higgsfield |
| [docs/adr/](docs/adr/README.md) | Keputusan arsitektur (ADR) |
| [CLAUDE.md](CLAUDE.md) | Panduan engineering |
