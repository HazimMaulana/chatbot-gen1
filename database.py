"""Koneksi PostgreSQL. Kredensial tidak ditulis di source code."""

import psycopg
from psycopg.rows import dict_row

from config import Config


def connect_db():
    if Config.DATABASE_URL:
        return psycopg.connect(
            Config.DATABASE_URL, connect_timeout=5, row_factory=dict_row,
            options="-c statement_timeout=5000",
        )
    if not Config.DB_PASSWORD:
        raise psycopg.OperationalError("Konfigurasi password database belum diisi.")
    return psycopg.connect(
        host=Config.DB_HOST, port=Config.DB_PORT, dbname=Config.DB_NAME,
        user=Config.DB_USER, password=Config.DB_PASSWORD,
        connect_timeout=5, row_factory=dict_row,
        options="-c statement_timeout=5000",
    )
