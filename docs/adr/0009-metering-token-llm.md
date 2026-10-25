# ADR-0009 — Semua Token LLM (Termasuk Hermes) Lewat Gateway Metering Studio

| | |
|---|---|
| Status | **Diterima** (2026-10-25) |
| Implementasi | Ledger & guard: Fase 1 · Gateway HTTP: Fase 5 · Adapter OpenAI asli: Fase 6 |

## Konteks

- Anggaran OpenAI **Rp60.000/bulan sudah termasuk Hermes**.
- Hermes memakai LLM untuk percakapan, pemanggilan tool (setiap putaran tool = 1 panggilan LLM baru), retry, serta fitur internal seperti ringkasan memori. Kalau Hermes memegang API key OpenAI sendiri, pemakaian ini tidak terlihat oleh studio dan tidak bisa dibatasi.
- Batas budget di dashboard OpenAI hanya jaring pengaman: datanya tertunda dan tidak per episode.

## Keputusan

1. **Hermes tidak pernah memegang API key OpenAI.** `base_url` Hermes diarahkan ke **gateway metering** lokal milik Studio (`http://127.0.0.1:<port>/v1`, kompatibel dengan OpenAI). Hanya gateway ini yang memegang key asli.
2. Untuk **setiap request** (percakapan, putaran tool call, retry, ringkasan internal):
   1. Gateway menghitung token input dan **memaksa** `max_tokens` (atau `max_completion_tokens`) sesuai batas config. Request tanpa batas output tetap diberi batas.
   2. Biaya terburuk dihitung (input + output maksimum) → `BudgetGuard.reserve(source="hermes", purpose=…)`.
   3. Reservasi ditolak → gateway membalas error terstruktur (`budget_exceeded`) tanpa meneruskan request ke OpenAI.
   4. Request diteruskan → biaya aktual dari field `usage` respons di-*commit*. Untuk streaming, `include_usage` diwajibkan.
   5. Hasil tidak jelas (timeout setelah request terkirim) → commit sebesar reservasi (konservatif), karena provider mungkin tetap menagih.
3. `purpose` dicatat per panggilan: `conversation`, `tool_call`, `retry`, `background` (memori, ringkasan, skill, cron — semua kerja di luar giliran percakapan). Retry selalu dihitung sebagai panggilan terpisah.
4. Panggilan LLM milik Studio sendiri (riset, naskah, …) memakai `BudgetGuard` yang sama dengan `source="studio"`.
5. Batas project di dashboard OpenAI tetap dipasang sebagai pengaman kedua, sedikit di atas alokasi.

## Yang Dibangun di Fase 1

- Ledger mencatat `source` (`studio`/`hermes`) dan `purpose`.
- Helper harga LLM per tier (`fast`/`smart`) per 1 juta token, dengan pembulatan ke atas.
- Test: keempat purpose Hermes (`conversation`, `tool_call`, `retry`, `background`) masing-masing tercatat dan memotong alokasi `openai` yang sama dengan Studio.
- Guard menolak belanja Hermes yang bukan kategori `openai`, yang memakai otorisasi selain operasional, atau yang purpose-nya tidak dikenal (ditambahkan saat audit Fase 1).

## Konsekuensi

- (+) Tidak ada token yang "lolos" dari hitungan anggaran.
- (+) Hermes langsung berhenti memakai LLM saat budget habis.
- (−) Gateway jadi komponen kritis. Kalau gateway mati, Director ikut mati (approval tetap jalan, sesuai ADR-0005).
- (−) Perlu menjaga kompatibilitas dengan format API OpenAI yang dipakai Hermes **[verifikasi di spike Fase 5]**.
