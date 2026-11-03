# Telegram dan deployment

## 1. Buat bot Telegram

1. Buka akun resmi https://t.me/BotFather di Telegram.
2. Kirim `/newbot`, isi nama dan username unik berakhiran `bot`.
3. Simpan token dari BotFather di `.env` proyek (jangan kirim ke chat atau Git):

```dotenv
TELEGRAM_BOT_TOKEN=isi_token_dari_botfather
TELEGRAM_ALLOWED_USER_IDS=
CHAT_API_URL=http://127.0.0.1:5000
TELEGRAM_STATE_FILE=data/telegram_offset.txt
```

Konfigurasi yang sudah ada di .env tetap dipertahankan. Python membaca .env
saat mulai; restart proses setelah mengubahnya. Token bisa dicabut lewat BotFather.

## 2. Uji di laptop (PowerShell)

Pastikan Docker Desktop dan aplikasi Ollama berjalan.

Terminal pertama, dari folder proyek:

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe init_db.py
.\.venv\Scripts\python.exe app.py
```

Terminal kedua:

```powershell
.\.venv\Scripts\python.exe telegram_bot.py
```

Buka bot melalui `https://t.me/USERNAME_BOT_KAMU`, tekan Start, lalu kirim:

```text
Berapa stok keyboard?
Harga GDG-001?
Ada mouse gaming?
```

`/help` menampilkan bantuan percakapan. `/whoami` menampilkan Telegram user ID milikmu.
`/reset` mengosongkan nama perkenalan dan konteks barang.

Fitur percakapan:
- Percakapan berbasis teks tanpa tombol; keyboard menu lama otomatis dihapus.
- Ollama membaca delapan pesan terakhir untuk bertanya soal kebutuhan/preferensi,
  lalu mencari barang setelah konteks cukup. Stok dan harga langsung dijawab jika diminta.
- Coba `Aku cari keyboard`, kemudian `Buat kerja, budget 300 ribu`.
- Budget eksplisit dipakai sebagai batas harga di query database.
- Indikator mengetik saat menunggu Flask/model.
- Sapaan/perkenalan/ucapan terima kasih dibalas langsung tanpa model.
- Coba `Halo, namaku Budi`, `Ada keyboard?`, lalu `yang putih` atau `2`.
- Nomor dan ciri barang merujuk daftar hasil terakhir dalam sesi yang sama.
- Nama, SKU terakhir, dan delapan pesan terakhir disimpan terpisah per user
  di PostgreSQL. Teks riwayat dapat memuat harga lama, tetapi angka jawaban
  barang selalu diambil ulang dari database, bukan dari riwayat.
- Jalankan init_db.py setelah update ini untuk membuat tabel sesi; barang lama
  tidak ditimpa. Restart Flask dan bot setelah pembaruan kode.
- Bukan memori percakapan bebas: rujukan rumit, pemesanan, dan negosiasi belum didukung.
Untuk percobaan terbatas, isi ID itu di `TELEGRAM_ALLOWED_USER_IDS`, lalu restart
bot. Beberapa ID bisa dipisahkan koma. Jika kosong, semua pengguna dapat memakai
bot melalui private chat. Grup diabaikan. Bot hanya mendukung pesan teks.

Long polling membuat koneksi HTTPS keluar ke Telegram. Tidak perlu domain,
ngrok, webhook, atau port publik. Laptop harus tetap hidup dan terhubung internet.
Jangan jalankan dua instance bot dengan token sama, termasuk di laptop dan server.
Webhook yang pernah dipasang harus dihapus sebelum beralih ke long polling.

## 3. Pindah ke server Linux

Pilih VPS/VM yang menjalankan proses terus-menerus dan mendukung Docker Compose.
Konfigurasi ini menjalankan model di CPU server. Sebagai perkiraan awal untuk
demo kecil Qwen3 1.7B, pertimbangkan 4 vCPU, RAM 8 GB, dan disk 30 GB; ukur lagi
kecepatan serta penggunaan memori sebelum menerima banyak pengguna. Ini bukan
jaminan kapasitas. GPU laptop tidak dipakai oleh VPS. Hosting yang tidur saat
idle atau hanya mendukung request singkat tidak cocok untuk worker polling ini.

Di server, install Docker Engine dan Compose mengikuti dokumentasi Docker untuk
distribusi Linux yang dipakai. Salin source proyek melalui Git atau SCP, tanpa
.venv, cache, .env lokal, dan data pribadi. Masuk folder proyek, lalu:

```bash
cp .env.example .env
nano .env
```

Isi password database yang kuat, token Telegram, dan ID pengguna jika ingin
membatasi akses. Jangan timpa .env yang sudah ada. Untuk file deployment ini,
alamat DB/API/Ollama internal sudah diatur dalam Compose, bukan localhost host.

Jalankan tahap persiapan:

```bash
docker compose -f compose.deploy.yaml build
docker compose -f compose.deploy.yaml up -d --wait db ollama
docker compose -f compose.deploy.yaml run --rm --no-deps api python init_db.py
docker compose -f compose.deploy.yaml exec ollama ollama pull qwen3:1.7b
```

Hentikan bot di laptop dengan Ctrl+C, baru aktifkan layanan di server:

```bash
docker compose -f compose.deploy.yaml up -d --wait api bot
docker compose -f compose.deploy.yaml ps
docker compose -f compose.deploy.yaml logs --tail 50 bot api
```

Flask berjalan memakai Gunicorn di container Linux, bukan debug server.
Compose memuat ulang layanan setelah reboot jika Docker ikut dimulai.
Tidak ada port layanan yang dipublikasikan; Telegram hanya perlu koneksi keluar.
API hanya dapat diakses bot/container internal. Jika kelak perlu API publik,
tambahkan autentikasi, HTTPS, dan pembatasan request sebelum membuka akses.

Periksa database dan model:

```bash
docker compose -f compose.deploy.yaml exec api python -c "from app import app; print(app.test_client().get('/health/db').json)"
docker compose -f compose.deploy.yaml exec ollama ollama ps
```

Deployment membuat DB baru berisi contoh. Data database lokal tidak otomatis
pindah ke server. Untuk data nyata, gunakan backup/restore PostgreSQL terpisah.
Data DB, model, dan offset bot disimpan dalam named volume. Jangan menghapus
volume ketika memperbarui aplikasi; siapkan backup rutin sebelum menyimpan data nyata.

## Batas versi ini

- Satu worker bot memproses pesan berurutan; model lambat membuat pesan lain menunggu.
- Offset update disimpan setelah balasan berhasil, sehingga restart biasa tidak
  membaca ulang pesan yang selesai. Crash setelah balasan terkirim tetapi sebelum
  offset tersimpan masih dapat menyebabkan balasan ganda (bukan exactly-once).
- Pesan Telegram disimpan maksimal 24 jam sebelum diambil oleh bot.
- Kegagalan database/API menghasilkan balasan layanan belum tersedia.
- Belum ada pemesanan, perubahan stok, riwayat teks lengkap, atau antrean multiworker.
- Platform bot Telegram gratis untuk penggunaan normal; server dan listrik/internet
  tetap menjadi biaya operasional. Pesan pengguna dikirim melalui layanan Telegram.

## Troubleshooting

- Token kosong/invalid: periksa .env tanpa menampilkannya di log.
- Konflik getUpdates: hentikan bot lain yang memakai token sama.
- Bot diam: tekan Start, cek allowed user IDs, gunakan private chat, lihat log bot.
- Layanan gudang tidak tersedia: cek Flask dan `/health/db`.
- Database belum siap: jalankan init_db.py dan pastikan password cocok dengan DB.
- Jawaban sangat lambat: uji model lebih kecil atau server lebih kuat; jangan
  berasumsi VPS CPU sama cepatnya dengan RTX laptop.

Referensi:
- https://core.telegram.org/bots/tutorial
- https://core.telegram.org/bots/api#getupdates
- https://flask.palletsprojects.com/en/stable/deploying/gunicorn/
