# Poly Smart Money Bot

Telegram bot sederhana untuk menampilkan taruhan Smart Money di Polymarket.
Bot akan mengambil 120 menit aktivitas terakhir dari subgraph Polymarket,
memeriksa label alamat melalui Nansen Profiler, lalu menampilkan hanya alamat
berlabel Smart Money.

## Persiapan

1. Salin `.env.example` menjadi `.env` lalu isi dengan kredensial Anda:

   ```bash
   cp .env.example .env
   ```

   Ubah nilai berikut:

   - `TELEGRAM_BOT_TOKEN`: token bot dari BotFather.
   - `NANSEN_API_KEY`: API key Nansen Profiler.
   - `POLY_SUBGRAPH_URL`: opsional, gunakan endpoint berbeda jika perlu.

2. Buat virtual environment dan install dependensi:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Menjalankan Bot

Pastikan `.env` sudah diisi lalu jalankan:

```bash
python app.py
```

Bot menggunakan long polling dari `python-telegram-bot` versi 20 sehingga tidak
memerlukan webhook. Ketika bot menerima `/smartmoney`, data akan dimuat ulang dan
pesan berisi daftar market Smart Money akan dikirim lengkap dengan tombol inline
YES/NO/REFRESH.

Contoh output:

```
Smart Money Trades (last 120m)
• Pemilu Presiden AS 2024
  Outcome: YES
  Maker: 0xABCD…1234 (Smart Trader)
  Size @ Price: 250 @ 0.61
  Waktu: 2024-05-01 12:34:56 UTC
```

## Filter Smart Money

Smart Money didefinisikan sebagai alamat yang memiliki label salah satu dari:

- `Smart Trader`
- `30D Smart Trader`
- `90D Smart Trader`
- `180D Smart Trader`
- `Fund`

Nansen Profiler dipanggil untuk setiap alamat maker dan hasilnya dicache (LRU)
agar hemat kuota.

## Docker

Contoh Dockerfile sudah disediakan. Build dan jalankan dengan:

```bash
docker build -t poly-smartmoney-bot .
docker run --env-file .env poly-smartmoney-bot
```
