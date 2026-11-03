"""Pencarian read-only. Input pengguna menjadi parameter, bukan kode SQL."""

import re

from database import connect_db

STOP_WORDS = set(
    "apa apakah ada berapa stok stock harga barang produk isi gudang rincian detail "
    "tolong dong kak min admin saya aku mau ingin cari mencari cek lihat tampilkan "
    "masih tersedia yang di itu ini untuk dan dengan bisa boleh ya nya saja semua "
    "berapa jumlah sisa punya kamu sebutkan jelaskan tentang secara singkat".split()
)


def search_items(query="", limit=10, offset=0, max_price_idr=0):
    tokens = [word for word in re.findall(r"[\w-]+", query.lower())
              if word not in STOP_WORDS]
    # Input nonkosong tanpa kata pencarian tidak boleh menjadi daftar seluruh barang.
    if query.strip() and not tokens:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
    clauses, params = [], []
    for token in tokens[:20]:
        # Hindari wildcard dari input seperti underscore.
        escaped = token.replace("\\", "\\\\").replace("_", "\\_")
        clauses.append("(sku ILIKE %s OR name ILIKE %s OR category ILIKE %s)")
        params.extend([f"%{escaped}%"] * 3)
    if max_price_idr:
        clauses.append("price_idr <= %s")
        params.append(max_price_idr)
    where = " AND ".join(clauses) if clauses else "TRUE"
    with connect_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS total FROM items WHERE {where}", params
        ).fetchone()["total"]
        rows = conn.execute(
            f"SELECT * FROM items WHERE {where} ORDER BY sku LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    for row in rows:
        row["updated_at"] = row["updated_at"].isoformat()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


def get_item(sku):
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM items WHERE sku = %s", (sku.upper(),)).fetchone()
    if row:
        row["updated_at"] = row["updated_at"].isoformat()
    return row


def format_inventory_reply(result, query):
    if not result["items"]:
        return (f"Barang '{query}' tidak ditemukan di katalog. "
                "Coba nama barang atau SKU, misalnya keyboard atau GDG-001.")
    lines = []
    for item in result["items"]:
        price = f"Rp{item['price_idr']:,}".replace(",", ".")
        stock = f"{item['stock']} {item['unit']}" if item["stock"] else "habis (0)"
        lines.append(f"- {item['name']} ({item['sku']}): stok {stock}, "
                     f"harga {price}/{item['unit']}.")
    if result["total"] > len(result["items"]):
        lines.append(f"Menampilkan {len(result['items'])} dari {result['total']} barang. "
                     "Sebutkan nama atau SKU agar lebih spesifik.")
    return "Data barang saat ini:\n" + "\n".join(lines)
