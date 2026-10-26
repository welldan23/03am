# Architecture Decision Records

| No. | Judul | Status |
|---|---|---|
| 0001 | Modular monolith, bukan microservice | Diterima — ringkasan di ARCHITECTURE §13 |
| 0002 | SQLite (stdlib `sqlite3`) + migrasi SQL bernomor | Diterima — ringkasan di ARCHITECTURE §13 |
| 0003 | Approval di luar jalur LLM | Diterima — ringkasan di ARCHITECTURE §13 |
| 0004 | Hermes ↔ Studio lewat MCP stdio | Diterima — ringkasan di ARCHITECTURE §13 |
| [0005](0005-satu-bot-telegram.md) | Satu bot Telegram milik Studio, Hermes tanpa gateway Telegram | **Diterima** |
| 0006 | Mock provider sebagai default | Diterima — ringkasan di ARCHITECTURE §13 |
| 0007 | Uang sebagai integer + ledger reservasi | Diterima — detail di ADR-0010 |
| 0008 | Antrean job di SQLite, bukan Redis/Celery | Diterima — ringkasan di ARCHITECTURE §13 |
| [0009](0009-metering-token-llm.md) | Semua token LLM (termasuk Hermes) lewat gateway metering Studio | **Diterima** |
| [0010](0010-rencana-anggaran-dan-otorisasi.md) | Rencana anggaran bulanan, kurs, dan otorisasi belanja | **Diterima** |
| [0011](0011-eksekusi-job-dua-fase.md) | Eksekusi job dua fase & catatan panggilan provider (`provider_calls`) | **Diterima** |
| [0012](0012-antarmuka-telegram-dan-outbox.md) | Antarmuka Telegram: Studio Controller, kode tombol sekali pakai, outbox notifikasi | **Diterima** |
| [0013](0013-pemrosesan-update-tahan-crash.md) | Pemrosesan update Telegram tahan crash (inbox + reply outbox persisten) | **Diterima** |

ADR yang masih berupa ringkasan akan ditulis lengkap kalau keputusannya perlu dibahas ulang.
