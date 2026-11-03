"""Buat tabel dan isi data fiktif. Aman diulang: SKU lama tidak ditimpa."""

import random

from database import connect_db

PRODUCTS = [
    ("Keyboard Mechanical Hitam", "Aksesoris", "unit", 350000),
    ("Keyboard Wireless Putih", "Aksesoris", "unit", 220000),
    ("Mouse Wireless Hitam", "Aksesoris", "unit", 125000),
    ("Mouse Gaming RGB", "Aksesoris", "unit", 185000),
    ("Monitor LED 24 Inch", "Monitor", "unit", 1450000),
    ("Monitor IPS 27 Inch", "Monitor", "unit", 2350000),
    ("Kabel HDMI 2 Meter", "Kabel", "pcs", 65000),
    ("Kabel USB Type C 1 Meter", "Kabel", "pcs", 45000),
    ("Kabel LAN Cat6 5 Meter", "Kabel", "pcs", 55000),
    ("SSD SATA 512 GB", "Penyimpanan", "unit", 520000),
    ("SSD NVMe 1 TB", "Penyimpanan", "unit", 980000),
    ("Flashdisk USB 64 GB", "Penyimpanan", "pcs", 85000),
    ("RAM DDR4 8 GB 3200 MHz", "Komponen", "unit", 280000),
    ("RAM DDR4 16 GB 3200 MHz", "Komponen", "unit", 510000),
    ("Adaptor USB C 65W", "Aksesoris", "unit", 275000),
    ("Headset Gaming Hitam", "Audio", "unit", 320000),
    ("Speaker USB Stereo", "Audio", "set", 150000),
    ("Webcam Full HD", "Aksesoris", "unit", 390000),
    ("Router WiFi Dual Band", "Jaringan", "unit", 480000),
    ("Switch Gigabit 8 Port", "Jaringan", "unit", 350000),
]


def init_db():
    rng = random.Random(42)
    inserted = 0
    with connect_db() as conn:
        from conversation import init_sessions
        init_sessions(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                sku VARCHAR(32) UNIQUE NOT NULL,
                name VARCHAR(160) NOT NULL,
                category VARCHAR(80) NOT NULL,
                stock INTEGER NOT NULL CHECK (stock >= 0),
                unit VARCHAR(20) NOT NULL,
                price_idr BIGINT NOT NULL CHECK (price_idr >= 0),
                location VARCHAR(40) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for index, (name, category, unit, price) in enumerate(PRODUCTS, 1):
            stock = 0 if index in (4, 11) else rng.randint(1, 150)
            result = conn.execute("""
                INSERT INTO items (sku, name, category, stock, unit, price_idr, location)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sku) DO NOTHING
            """, (f"GDG-{index:03}", name, category, stock, unit, price,
                  f"Rak {chr(65 + (index - 1) // 5)}-{(index - 1) % 5 + 1}"))
            inserted += result.rowcount
        total = conn.execute("SELECT COUNT(*) AS total FROM items").fetchone()["total"]
    return inserted, total


if __name__ == "__main__":
    inserted, total = init_db()
    print(f"Database siap: {inserted} barang baru, total {total} barang fiktif.")
