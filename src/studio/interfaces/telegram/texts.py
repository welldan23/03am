"""Semua teks statis yang dilihat owner di Telegram (Bahasa Indonesia)."""

from __future__ import annotations

from studio.modules.episodes import Category, DocumentaryFormat, EpisodeStatus
from studio.modules.scripting import SegmentRole
from studio.shared.gates import Gate

WELCOME = (
    "🌙 <b>03:AM — AI Documentary Studio</b>\n"
    "Halo! Saya asisten studio. Pilih menu di bawah atau ketik saja, misalnya:\n"
    "• <i>Cari topik sejarah yang menarik</i>\n"
    "• <i>Buat dokumenter tentang Krakatau, format 90 detik</i>\n"
    "• <i>Tampilkan episode yang belum saya approve</i>\n\n"
    "⚠️ Fase 3: semua AI & biaya masih <b>simulasi (mock)</b>. Tidak ada API berbayar."
)

HELP = (
    "<b>Bantuan</b>\n"
    "/menu — menu utama\n"
    "/status — status produksi\n"
    "/episodes — episode aktif\n"
    "/budget — anggaran bulan ini\n"
    "/help — bantuan ini\n\n"
    "<b>Contoh perintah bebas</b>\n"
    "• Cari topik sejarah yang menarik\n"
    "• Buat dokumenter tentang Krakatau\n"
    "• Pilih format 90 detik\n"
    "• Tunjukkan hasil risetnya\n"
    "• Ringkas bagian pembuka\n"
    "• Naskahnya terlalu kaku, buat lebih natural\n"
    "• Apa sumber untuk klaim C-krak-sound?\n"
    "• Berapa estimasi biaya episode ini?\n"
    "• Tampilkan episode yang belum saya approve\n\n"
    "🔒 Keputusan approval (setuju/tolak/revisi) hanya lewat <b>tombol kartu</b>, tidak lewat "
    "teks, supaya tidak ada salah tebak."
)

NOT_PRIVATE = "Bot 03:AM hanya melayani chat pribadi dengan owner."
NOT_OWNER = "Maaf, bot ini privat."
UNKNOWN = "Saya belum paham maksudnya. Coba pilih menu, atau ketik /help untuk contoh perintah."
DECISION_BY_TEXT = (
    "🔒 Untuk keamanan, approval hanya bisa diputuskan lewat tombol di kartu approval. "
    "Ini daftar yang sedang menunggu:"
)
INTERNAL_ERROR = "Terjadi kesalahan di studio. Sudah dicatat; coba lagi sebentar lagi."
DB_BUSY = "Database studio sedang sibuk. Coba lagi beberapa detik lagi."
STEP_CANCELLED = "Oke, langkah dibatalkan."
ASK_FORMAT = "Pilih format dokumenter:"
ASK_CATEGORY = "Pilih kategori:"
ASK_EPISODE = "Episode yang mana? Pilih salah satu:"
ASK_CLAIM = "Klaim yang mana? Pilih untuk melihat sumbernya:"
ASK_REVISION_NOTES = (
    "✏️ Tulis catatan revisi naskah (apa yang perlu diubah). Ketik <i>batal</i> untuk berhenti."
)
NO_EPISODES = "Belum ada episode. Pilih 🎬 Buat Dokumenter untuk mulai."
NO_PENDING = "Tidak ada approval yang menunggu. 👍"
SIMULATION_NOTE = "⚠️ SIMULASI Fase 3 — tahap ini masih placeholder; tidak ada biaya/aset nyata."

MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("🎬 Buat Dokumenter", "new"),
    ("📂 Episode Aktif", "eps"),
    ("💡 Ide Topik", "ideas"),
    ("🔎 Review Riset", "research"),
    ("📝 Review Naskah", "script"),
    ("✅ Approval", "appr"),
    ("⚙️ Status Produksi", "status"),
    ("💰 Budget", "budget"),
    ("🛠 Pengaturan", "settings"),
)

STATUS_LABEL: dict[EpisodeStatus, str] = {
    EpisodeStatus.DRAFT: "Draf",
    EpisodeStatus.DISCOVERING: "Mencari topik",
    EpisodeStatus.AWAITING_TOPIC: "Menunggu pilihan topik (G0)",
    EpisodeStatus.RESEARCHING: "Riset sumber",
    EpisodeStatus.FACT_CHECKING: "Cek fakta",
    EpisodeStatus.SCRIPTING: "Menulis naskah",
    EpisodeStatus.STORYBOARDING: "Menyusun storyboard (simulasi)",
    EpisodeStatus.AWAITING_EDITORIAL: "Menunggu approval editorial (G1)",
    EpisodeStatus.ESTIMATING_COST: "Estimasi biaya (simulasi)",
    EpisodeStatus.AWAITING_COST: "Menunggu approval biaya (G2, simulasi)",
    EpisodeStatus.GENERATING_ASSETS: "Membuat aset (simulasi)",
    EpisodeStatus.GENERATING_VOICE: "Sulih suara (simulasi)",
    EpisodeStatus.RENDERING: "Render (simulasi)",
    EpisodeStatus.AWAITING_FINAL: "Menunggu approval final (G3, simulasi)",
    EpisodeStatus.EXPORTING: "Ekspor (simulasi)",
    EpisodeStatus.EXPORTED: "Selesai",
    EpisodeStatus.REJECTED: "Ditolak",
    EpisodeStatus.CANCELLED: "Dibatalkan",
    EpisodeStatus.FAILED: "Gagal",
}

GATE_LABEL: dict[Gate, str] = {
    Gate.TOPIC: "G0 · Pilih topik",
    Gate.EDITORIAL: "G1 · Persetujuan editorial",
    Gate.COST: "G2 · Persetujuan biaya (simulasi)",
    Gate.FINAL: "G3 · Persetujuan final (simulasi)",
}

FORMAT_BUTTON: dict[DocumentaryFormat, str] = {
    DocumentaryFormat.QUICK_FILES: "⚡ Quick Files (30–45 dtk)",
    DocumentaryFormat.ARCHIVES: "🗂 The Archives (75–90 dtk)",
    DocumentaryFormat.DEEP_FILES: "🔬 Deep Files (120–180 dtk)",
}

CATEGORY_BUTTON: dict[Category, str] = {
    Category.SEJARAH: "🏛 Sejarah",
    Category.GEOPOLITIK: "🌐 Geopolitik",
    Category.SAINS: "🔭 Sains",
    Category.GEOGRAFI: "🗺 Geografi",
    Category.MISTERI: "🕯 Misteri",
}

SEGMENT_LABEL: dict[SegmentRole, str] = {
    SegmentRole.HOOK: "Hook",
    SegmentRole.CONTEXT: "Context",
    SegmentRole.CONFLICT: "Conflict",
    SegmentRole.EXPLANATION: "Explanation",
    SegmentRole.CLOSING: "Closing",
}

REVISION_TARGET_LABEL: dict[EpisodeStatus, str] = {
    EpisodeStatus.DISCOVERING: "Cari topik baru",
    EpisodeStatus.RESEARCHING: "Riset ulang",
    EpisodeStatus.FACT_CHECKING: "Cek fakta ulang",
    EpisodeStatus.SCRIPTING: "Tulis ulang naskah",
    EpisodeStatus.STORYBOARDING: "Susun ulang storyboard",
    EpisodeStatus.ESTIMATING_COST: "Hitung ulang biaya",
    EpisodeStatus.GENERATING_ASSETS: "Buat ulang aset",
    EpisodeStatus.GENERATING_VOICE: "Ulang sulih suara",
    EpisodeStatus.RENDERING: "Render ulang",
}

BUDGET_CATEGORY_LABEL: dict[str, str] = {
    "openai": "OpenAI + Hermes",
    "higgsfield": "Higgsfield",
    "tts": "TTS",
    "reserve": "Cadangan",
}
