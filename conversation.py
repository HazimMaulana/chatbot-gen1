"""Alur percakapan dan konteks per sesi; stok selalu dibaca ulang dari DB."""

import re

from psycopg.types.json import Jsonb

from database import connect_db
from inventory import format_inventory_reply, get_item, search_items
from discovery import plan_conversation


def init_sessions(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id VARCHAR(120) PRIMARY KEY,
            state JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def load_state(session_id):
    if not session_id:
        return {}
    with connect_db() as conn:
        row = conn.execute("""SELECT state FROM chat_sessions WHERE session_id = %s
            AND updated_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'""", (session_id,)).fetchone()
    return row["state"] if row else {}


def save_state(session_id, state):
    if session_id:
        with connect_db() as conn:
            conn.execute("""INSERT INTO chat_sessions (session_id, state) VALUES (%s, %s)
                ON CONFLICT (session_id) DO UPDATE
                SET state = EXCLUDED.state, updated_at = CURRENT_TIMESTAMP""",
                (session_id, Jsonb(state)))


def catalog_overview():
    """Ringkasan dari seluruh kategori, bukan daftar produk tebakan model."""
    with connect_db() as conn:
        rows = conn.execute("""
            SELECT category, name FROM (
                SELECT category, name,
                    ROW_NUMBER() OVER (PARTITION BY category ORDER BY sku) AS position
                FROM items
            ) AS examples WHERE position <= 2 ORDER BY category, position
        """).fetchall()
    if not rows:
        return "Katalog barangnya belum terisi, jadi aku belum punya produk yang bisa diperkenalkan."
    groups = {}
    for row in rows:
        groups.setdefault(row["category"], []).append(row["name"])
    examples = "\n".join(f"- {category}: {', '.join(names)}."
                         for category, names in groups.items())
    return ("Di sini kami menjual perlengkapan komputer dan aksesoris. "
            "Ini beberapa contoh yang tercatat di katalog kami:\n\n" + examples +
            "\n\nAda yang ingin kamu tahu lebih lanjut? Aku bisa bantu cek detail, harga, dan stoknya.")


def respond(message, session_id, interpret):
    text = re.sub(r"[^\w\s-]", "", message.lower()).strip()
    state = load_state(session_id)

    def answer(reply, source="conversation", **extra):
        history = state.get("history", [])
        history.extend([{"role": "user", "content": message[:1000]},
                        {"role": "assistant", "content": reply[:2000]}])
        state["history"] = history[-8:]
        save_state(session_id, state)
        return {"reply": reply, "items": [], "total": 0, "source": source,
                "action": "help", "query": "", "interpreter": "local", **extra}

    def overview():
        # Ringkasan tidak dianggap sebagai pilihan SKU bernomor untuk giliran berikutnya.
        state.pop("skus", None)
        state["discovery_turns"] = 0
        return answer(catalog_overview(), "catalog", action="overview")

    if text in ("reset", "reset percakapan", "mulai ulang"):
        state.clear()
        return answer("Percakapan sudah direset. Mau mencari barang apa sekarang?")
    introduction = re.fullmatch(
        r"(?:(?:halo|hai|hi)[,!.]?\s+)?(?:namaku|nama saya|aku adalah|saya adalah)\s+"
        r"([\w'-]+(?:\s+[\w'-]+){0,3})[.!]?", message.strip(), re.IGNORECASE)
    if introduction:
        state["name"] = introduction.group(1)[:60]
        return answer(f"Salam kenal, {state['name']}! Aku Gudi, asisten virtual gudang. "
                      "Lagi butuh perlengkapan untuk apa nih?")
    name = f", {state['name']}" if state.get("name") else ""
    if text in {"halo", "hai", "hi", "hello", "hallo", "halo bot", "hai bot",
                "selamat pagi", "selamat siang", "selamat sore", "selamat malam"}:
        return answer(f"Halo{name}! Aku Gudi, asisten virtual gudang. "
                      "Ada yang lagi kamu cari, atau ada kebutuhan yang bisa kubantu?", "greeting")
    if text in {"terima kasih", "makasih", "thanks", "thank you", "oke", "ok", "sip"}:
        return answer(f"Sama-sama{name}! Kalau ada barang lain yang dicari, langsung sebutkan saja.")
    if text in {"siapa namaku", "namaku siapa", "siapa nama saya"}:
        return answer(f"Kamu memperkenalkan diri sebagai {state['name']}." if state.get("name")
                      else "Kita belum berkenalan. Kamu bisa bilang 'Namaku Budi'.")
    if text in {"siapa kamu", "kamu siapa"}:
        return answer("Aku Gudi, asisten virtual yang membantu mengecek barang di gudang.")
    if text in {"cari barang", "cek stok", "cek harga"}:
        return answer("Lagi cari barang apa? Cerita sedikit kebutuhanmu, nanti aku bantu cek pilihannya.")
    if text in {"hubungi admin", "admin"}:
        return answer("Kontak admin belum dikonfigurasi. Aku belum bisa meneruskan pesan. "
                      "Untuk sementara aku bisa membantu mengecek stok dan harga.")
    # Bentuk pertanyaan katalog yang umum dijawab langsung, termasuk saat model mati.
    general_catalog = (
        re.search(r"\b(barang|produk|perlengkapan)\s+"
                  r"(?:(?:yang|kamu|kalian|anda|dijual|jual|itu|ini|seperti|jenis|saja|aja)\s+){0,10}"
                  r"(?:apa|apaan)\b", text)
        or re.search(r"\b(jual|menjual|jualan)\s+(apa|apaan|apa aja|apa saja)\b", text)
        or re.search(r"\b(apa saja|apa aja)\b.{0,60}\b(dijual|kamu jual|kalian jual)\b", text)
    )
    if general_catalog:
        return overview()
    if text in {"lihat kategori", "kategori"}:
        with connect_db() as conn:
            categories = conn.execute("SELECT DISTINCT category FROM items ORDER BY category").fetchall()
        return answer("Pilih atau ketik kategori yang ingin dilihat:\n" +
                      "\n".join(f"- {row['category']}" for row in categories))

    previous = state.get("skus", [])
    result = None
    intent = None
    selection = re.fullmatch(r"(?:nomor\s+|pilihan\s+)?(\d+)", text)
    reference = (text.startswith(("yang ", "kalau yang ")) or
                 text in {"harganya", "stoknya", "berapa harganya", "berapa stoknya", "detailnya"})
    if selection:
        index = int(selection.group(1)) - 1
        if not 0 <= index < len(previous):
            return answer("Nomor pilihan belum tersedia. Cari barang dulu, lalu pilih nomor dari hasilnya.")
        item = get_item(previous[index])
        result = {"items": [item] if item else [], "total": int(bool(item)), "limit": 10, "offset": 0}
    elif reference:
        if not previous:
            return answer("Barang yang mana? Sebutkan nama atau SKU dulu supaya aku bisa mengeceknya.")
        qualifiers = [word for word in text.split() if word not in
                      {"yang", "kalau", "harganya", "stoknya", "berapa", "detailnya", "warna"}]
        live_items = [get_item(sku) for sku in previous]
        matches = [item for item in live_items if item and
                   all(word in item["name"].lower() for word in qualifiers)]
        result = {"items": matches, "total": len(matches), "limit": 10, "offset": 0}

    if result is None:
        # Pertanyaan fakta langsung tetap cepat; discovery dipakai untuk konsultasi
        # dan jawaban lanjutan atas pertanyaan kebutuhan bot.
        direct = bool(re.search(r"\b(stok|stock|harga|ada|tersedia|gdg-\d+|kategori|daftar)\b", text))
        explicit_list = text in {"lihat semua barang", "tampilkan daftar barang", "daftar barang"}
        if not direct and not explicit_list:
            catalog = search_items("", limit=50)
            plan = plan_conversation(message, state.get("history", []), catalog["items"])
            if plan and plan["action"] == "overview":
                return overview()
            if plan and plan["action"] == "ask":
                state["discovery_turns"] = state.get("discovery_turns", 0) + 1
                # Setelah dua pertanyaan, gunakan kata pencarian bila tersedia.
                if state["discovery_turns"] <= 2 or not plan["query"].strip():
                    return answer(plan["question"], "discovery")
            if plan and plan["query"].strip():
                intent = {"action": "search", "query": plan["query"], "interpreter": "discovery"}
                result = search_items(plan["query"], max_price_idr=plan["max_price_idr"])
                state["discovery_turns"] = 0
                query = plan["query"]

    if result is None:
        if text in {"lihat semua barang", "tampilkan daftar barang", "daftar barang"}:
            intent = {"action": "list", "query": "", "interpreter": "local"}
        else:
            intent = interpret(message)
        if intent["action"] == "help":
            return answer(f"Aku siap bantu{name}. Coba sebutkan barang yang dicari, "
                          "atau ceritakan kendalanya dulu. Lagi butuh untuk apa?")
        query = "" if intent["action"] == "list" else intent["query"]
        result = search_items(query)
    elif intent is None:
        query = message
        intent = {"action": "search", "query": message, "interpreter": "context"}

    if result["items"]:
        state["skus"] = [item["sku"] for item in result["items"]]
    reply = format_inventory_reply(result, query)
    if len(result["items"]) > 1:
        reply += "\n\nDari pilihan ini, kamu lebih suka yang seperti apa?"
    elif result["items"]:
        reply += "\n\nPilihan ini sudah sesuai kebutuhanmu, atau ada yang ingin kamu pastikan dulu?"
    elif reference:
        reply = "Pilihan itu belum cocok dengan barang yang tadi ditampilkan. Sebutkan ciri lain atau SKU-nya."
    return answer(reply, "database", **result, **intent)
