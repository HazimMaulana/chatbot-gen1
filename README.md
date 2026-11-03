# Chatbot gudang: Flask + PostgreSQL + Ollama

Panduan bot Telegram dan server: [DEPLOYMENT.md](DEPLOYMENT.md).

Proyek belajar chatbot stok dan harga. Seluruh data awal adalah fiktif.

## Alur aplikasi

```text
Terminal / aplikasi chat -> POST /chat -> Ollama mengekstrak kata pencarian
                                      -> PostgreSQL mencari barang
                                      -> jawaban stok/harga dari data aktual

Klien lain -> GET /api/items?q=keyboard -> data barang dalam JSON
```

Model tidak membuat SQL atau mengarang angka stok/harga. Python memformat jawaban
langsung dari hasil query PostgreSQL. `/chat` dan `/api/items` memakai fungsi
pencarian yang sama di `inventory.py`; Flask tidak memanggil dirinya lewat HTTP.
Jika Ollama gagal, pencarian kata sederhana digunakan sebagai fallback.

## File

| File | Fungsi |
|---|---|
| `app.py` | API HTTP, validasi input dan penanganan error |
| `chatbot.py` | Meminta Ollama mengekstrak nama barang/SKU |
| `inventory.py` | Pencarian barang dan format jawaban pelanggan |
| `database.py` | Koneksi PostgreSQL melalui psycopg |
| `init_db.py` | Membuat tabel dan mengisi 20 barang contoh |
| `config.py` | Konfigurasi dari environment atau .env |
| `compose.yaml` | PostgreSQL 17 lokal dengan Docker dan volume persisten |
| `.env.example` | Contoh pengaturan, tanpa kredensial asli |
| `tests/test_inventory.py` | Pengujian integrasi API dan database |

## Setup awal (PowerShell)

Prasyarat: Python 3.11+, Docker Desktop dengan Linux containers, dan Ollama.
Jalankan dari folder proyek:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Jika `.env` belum ada, salin `.env.example` ke `.env` dan isi password sendiri:

```powershell
Copy-Item .env.example .env
```

Jika `.env` sudah dibuat saat setup, pertahankan file itu. Password lokal telah
digenerate secara acak. Jangan commit `.env`. Python dan Docker Compose membaca
file tersebut; environment variable yang sudah ada mengambil prioritas.

Buka Docker Desktop lalu:

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe init_db.py
ollama pull qwen3:1.7b
.\.venv\Scripts\python.exe app.py
```

`init_db.py` aman diulang: SKU yang sudah ada tidak ditimpa. Stok contoh termasuk
barang habis. Harga adalah integer rupiah, stok bukan pemesanan/reservasi.

PostgreSQL dapat diakses di `127.0.0.1:5433`, database/user `warehouse`, password
sesuai `.env`. Bisa dilihat lewat pgAdmin atau DBeaver. Jangan bagikan password.
Data tetap ada di Docker volume ketika container dihentikan:

```powershell
docker compose stop
# Jalankan lagi kemudian:
docker compose up -d --wait
```

Mengubah password di `.env` tidak mengubah password database yang sudah dibuat.
Untuk server PostgreSQL existing/managed, isi `DATABASE_URL` sesuai penyedia;
Compose tidak diperlukan. DATABASE_URL mengambil prioritas atas POSTGRES_*.

## Uji API langsung

Buka terminal kedua. Browser juga bisa membuka endpoint GET berikut:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health/db
Invoke-RestMethod 'http://127.0.0.1:5000/api/items?q=keyboard' | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:5000/api/items/GDG-001 | ConvertTo-Json -Depth 5
```

| Endpoint | Fungsi |
|---|---|
| `GET /health` | Memeriksa Flask saja |
| `GET /health/db` | Memeriksa koneksi/tabel PostgreSQL |
| `GET /api/items?q=keyboard&limit=10&offset=0` | Cari nama, SKU, atau kategori |
| `GET /api/items` | Daftar barang dengan pagination |
| `GET /api/items/GDG-001` | Detail barang berdasarkan SKU |
| `POST /chat` | Pertanyaan bahasa Indonesia, jawaban dan data sumber |

`limit` antara 1-50. Semua kata pencarian harus cocok. Pencarian ini bukan fuzzy
search: salah eja/sinonim belum selalu dikenali. Stok 0 berarti barang tercatat
namun habis; hasil kosong berarti barang tidak ditemukan.

## Uji percakapan

```powershell
$body = @{ message = "Berapa stok keyboard?" } | ConvertTo-Json
$result = Invoke-RestMethod `
    -Uri "http://127.0.0.1:5000/chat" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
$result.reply
```

Coba juga `Harga GDG-001?`, `Ada mouse gaming?`, `Tampilkan daftar barang`,
atau `Ada unicorn?`. Respons berisi `reply`, `items`, `total`, `query`, dan
`interpreter` (ollama atau keyword_fallback). Pesan bantuan tidak mencari DB.
Konteks percakapan tersedia melalui `session_id` opsional di request /chat.
Telegram otomatis memakai sesi terpisah per user. Nama perkenalan dan SKU hasil
terakhir disimpan di tabel `chat_sessions`; stok/harga selalu dibaca ulang.
Delapan pesan terakhir juga disimpan untuk menggali kebutuhan secara natural.
Contoh: `Aku cari keyboard` -> bot bertanya kegunaan -> `Buat kerja, budget
300 ribu` -> bot mencari barang dengan harga maksimal Rp300.000.
Tidak ada tombol menu; pertanyaan stok/harga langsung tetap bisa digunakan.
Konteks diabaikan setelah 24 jam tidak aktif, tetapi barisnya tidak otomatis dihapus.
`/reset` atau tombol Reset percakapan mengosongkan konteks sesi.
Tanpa session_id, request tetap berdiri sendiri. Endpoint ini belum memakai
autentikasi sesi: jangan membukanya ke internet tanpa kontrol akses.
Pertanyaan perbandingan, transaksi, dan filter stok/harga belum didukung.

## Pengujian

Dengan PostgreSQL dan tabel contoh siap:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tes memakai DB yang dikonfigurasi; init hanya menambah SKU contoh yang belum ada.
Ollama dimock dalam tes agar hasil tidak bergantung pada keluaran model.

## Menyambungkan ke aplikasi chat

Kontrak adapter sederhana: terima pesan -> POST /chat dengan JSON
`{"message": "pesan pengguna"}` -> kirim `reply` kembali ke percakapan asal.
Adapter long polling tersedia di `telegram_bot.py`. Token belum diisi dan bot
belum diaktifkan; ikuti `DEPLOYMENT.md` untuk mencoba dan memindahkan ke server.

### Telegram (opsi belajar gratis)

Platform bot Telegram gratis untuk pemakaian normal:
https://core.telegram.org/bots

1. Buat bot lewat @BotFather dan simpan token sebagai environment variable.
2. Adapter Python membaca update dengan long polling.
3. Pesan teks diteruskan ke Flask /chat, lalu reply dikirim lewat Bot API.
4. Long polling memungkinkan percobaan lokal tanpa membuka webhook publik.

### WhatsApp (opsi resmi)

Gunakan WhatsApp Business Platform / Cloud API. Akun WhatsApp biasa dan aplikasi
WhatsApp Business saja belum memberikan endpoint bot Python.

1. Siapkan akun developer Meta dan setup WhatsApp Cloud API/test number.
2. Simpan access token, phone number ID, dan webhook verify token di environment.
3. Sediakan webhook HTTPS publik, termasuk verifikasi challenge dan signature.
4. Webhook menerima pesan, mengantrikannya, lalu adapter memanggil /chat.
5. Kirim reply ke nomor pengirim melalui API pesan Meta.
6. Deduplicasi message ID agar webhook ulang tidak menghasilkan balasan ganda.

Jangan anggap seluruh pemakaian WhatsApp gratis. Halaman resmi harga saat dicek
menyebut balasan service dalam jendela 24 jam gratis; template/kategori lain dan
biaya penyedia perantara dapat berbeda. Pastikan rate card yang berlaku pada
akunmu sebelum aktivasi: https://business.whatsapp.com/products/platform-pricing

Aplikasi ini tetap lokal dan belum dipublikasikan. Sebelum akses publik,
gunakan server WSGI produksi (bukan debug Flask), HTTPS, autentikasi API,
pembatasan request, dan pengaturan akses data. Jangan membuka port PostgreSQL
atau Ollama ke internet. Laptop/server yang menjalankan model harus tetap hidup.
