"""HTTP API chatbot. Jalankan dengan: python app.py."""

from flask import Flask, jsonify, request
import psycopg

from chatbot import interpret_inventory_request
from config import Config
from database import connect_db
from inventory import get_item, search_items

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/health")
def health():
    # Ini mengecek Flask saja, bukan koneksi ke Ollama.
    return jsonify({"status": "ok", "model": Config.MODEL})


@app.get("/health/db")
def database_health():
    with connect_db() as conn:
        total = conn.execute("SELECT COUNT(*) AS total FROM items").fetchone()["total"]
    return jsonify({"status": "ok", "database": "postgresql", "items": total})


@app.get("/api/items")
def items():
    query = request.args.get("q", "").strip()
    if len(query) > 200:
        return jsonify({"error": "q maksimal 200 karakter."}), 400
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return jsonify({"error": "limit dan offset harus bilangan bulat."}), 400
    if not 1 <= limit <= 50 or not 0 <= offset <= 100000:
        return jsonify({"error": "limit harus 1-50 dan offset harus 0-100000."}), 400
    return jsonify({"query": query, **search_items(query, limit, offset)})


@app.get("/api/items/<sku>")
def item_detail(sku):
    item = get_item(sku)
    if item is None:
        return jsonify({"error": "SKU tidak ditemukan."}), 404
    return jsonify({"item": item})


@app.post("/chat")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Body harus berupa JSON object."}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message harus berupa teks yang tidak kosong."}), 400
    if len(message) > Config.MAX_MESSAGE_CHARS:
        return jsonify({"error": f"message maksimal {Config.MAX_MESSAGE_CHARS} karakter."}), 400

    session_id = data.get("session_id")
    if session_id is not None and (not isinstance(session_id, str)
                                   or not 1 <= len(session_id) <= 120):
        return jsonify({"error": "session_id harus teks sepanjang 1-120 karakter."}), 400
    from conversation import respond
    return jsonify(respond(message.strip(), session_id, interpret_inventory_request))


@app.errorhandler(psycopg.Error)
def database_error(error):
    # Jangan mengirim detail koneksi/kredensial kepada pengguna.
    app.logger.error("Database operation failed (%s)", type(error).__name__)
    return jsonify({"error": "Database belum siap. Jalankan PostgreSQL dan init_db.py."}), 503


@app.errorhandler(413)
def request_too_large(error):
    return jsonify({"error": "Ukuran request terlalu besar."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
