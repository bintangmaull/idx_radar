# 🚀 Panduan Lengkap Deployment Ajaib Charting dengan Dokploy

Panduan ini menjelaskan langkah demi langkah cara men-deploy **Web Dashboard** dan **Telegram Bot** Anda ke VPS menggunakan platform **Dokploy** (berbasis Docker Compose).

---

## Tahap 1: Persiapan di Repositori (Lokal)

Sebelum mulai deploy, pastikan kode terbaru sudah didorong (push) ke GitHub.

1. Buka Terminal di VS Code.
2. Pastikan Anda berada di root folder `ajaib_charting` (atau folder yang berisi file `.git`).
3. Jalankan perintah berikut untuk menyimpan perubahan dan push ke GitHub:
   ```bash
   git add .
   git commit -m "Siap untuk deploy dengan credential yang diamankan"
   git push origin main
   ```
   *(Catatan: Sesuaikan `main` dengan nama branch Anda jika menggunakan nama lain seperti `master`)*

---

## Tahap 2: Buat Network Traefik (Di VPS/Dokploy)

Karena di dalam `docker-compose.yml` kita menggunakan network eksternal bernama `dokploy-network`, pastikan network tersebut sudah ada di VPS Anda.

1. Login ke VPS Anda menggunakan SSH (misal: `ssh root@ip_vps_anda`).
2. Buat Docker network secara manual dengan perintah:
   ```bash
   docker network create dokploy-network
   ```
   *(Jika network sudah ada, akan muncul pesan error yang wajar. Abaikan saja).*

---

## Tahap 3: Konfigurasi Dokploy

1. **Login ke Dashboard Dokploy**
   Buka browser dan akses dashboard Dokploy Anda (biasanya `http://<IP-VPS>:3000`).

2. **Buat Project Baru**
   - Di sidebar kiri, klik **Projects**.
   - Klik **Create Project**.
   - Beri nama, misalnya: `IDX-Ajaib`.
   - Klik project yang baru dibuat.

3. **Buat Compose Application**
   - Di dalam project `IDX-Ajaib`, klik **Create Service** (atau tombol sejenis untuk menambah aplikasi).
   - Pilih tipe **Compose** (karena kita akan menggunakan `docker-compose.yml`).
   - Beri nama service, misalnya: `ajaib-bot-web`.

4. **Hubungkan dengan GitHub**
   - Di tab **General** / **Source**, pilih opsi **Git Repository** atau **GitHub**.
   - Pilih repository GitHub Anda (misal: `bintangmaull/idx_radar` atau repository tempat kode ini berada).
   - Tentukan **Branch** yang digunakan (misal: `main`).
   - Tentukan **Compose File Path**. Jika foldernya ada di dalam sub-folder `ajaib_charting`, tulis:
     `/ajaib_charting/docker-compose.yml`
     *(Jika `docker-compose.yml` ada di root folder, cukup tulis `/docker-compose.yml`)*

5. **Masukkan Environment Variables (Kredensial Rahasia)**
   Karena kita memisahkan kredensial ke dalam file `.env` yang tidak di-push ke GitHub, kita harus memasukkannya secara manual di Dokploy:
   - Masuk ke tab **Environment** di menu aplikasi Dokploy.
   - Klik **Add Variable** (atau paste langsung dalam format env file).
   - Masukkan variabel berikut (sesuaikan valuenya):
     ```env
     TELEGRAM_BOT_TOKEN=8610277986:AAFB1uLk63-T-jE_jqdtomtnY_rudcfrAKU
     TELEGRAM_CHAT_ID=8597147288
     ARJUM_API_KEY=sk_live_ml1n2K7otE_C486JoyoXxagO4P1b71MllKv79_xWeR4
     ```
   - Klik **Save**.

6. **Konfigurasi Domain (Traefik)**
   Pada file `docker-compose.yml`, kita sudah memasukkan label Traefik untuk mengarahkan rute `sinyal.bintangmaulana.my.id` ke port 5000:
   ```yaml
   - "traefik.http.routers.ajaib-web.rule=Host(`sinyal.bintangmaulana.my.id`)"
   ```
   Pastikan Anda sudah mengarahkan DNS record (A Record/CNAME) domain `sinyal.bintangmaulana.my.id` di Cloudflare / provider domain menuju ke **IP VPS Anda**.
   
   *(Traefik milik Dokploy secara otomatis akan mendeteksi label ini dan membuatkan SSL/HTTPS melalui Let's Encrypt).*

---

## Tahap 4: Mulai Deploy!

1. Klik tombol **Deploy** (atau Save & Deploy) di kanan atas dashboard Dokploy Anda.
2. Dokploy akan:
   - Mengambil (_clone_) kode dari GitHub.
   - Menjalankan `docker-compose build`.
   - Menjalankan `docker-compose up -d`.
3. Buka tab **Logs** (Deployment Logs) untuk memantau proses build. Pastikan tidak ada error.

---

## Tahap 5: Verifikasi Deployment

Setelah deploy selesai (status **Running** / **Active**):

1. **Cek Web Dashboard**
   Buka browser dan kunjungi domain: `https://sinyal.bintangmaulana.my.id`. Dashboard Ajaib Charting Anda seharusnya sudah bisa diakses.

2. **Cek Log Bot Telegram**
   - Di Dokploy, masuk ke menu **Containers** atau **Logs** khusus container `ajaib-bot`.
   - Anda seharusnya melihat pesan seperti:
     ```
     =======================================
     🤖 TELEGRAM SMART ENTRY V4.1 AKTIF
     =======================================
     ```

## 🛠️ Jika Terjadi Masalah (Troubleshooting)

- **Website tidak bisa diakses (Error 502 Bad Gateway)**: Pastikan container `ajaib-web` berjalan. Cek Logs-nya di Dokploy apakah ada error terkait Python (misalnya, modul belum terinstall).
- **Bot tidak mengirim sinyal**: Cek Logs di container `ajaib-bot`. Pastikan Token API di menu Environment Dokploy sudah benar.
- **Terkait `orderbook.db`**: Karena `docker-compose.yml` menggunakan *volume binding* lokal (`- ./orderbook.db:/app/orderbook.db`), database akan dibuat dan disimpan secara persisten di *host* Dokploy. Ini memastikan jika bot di-restart, data history orderbook tidak hilang.

Selamat! Sistem Anda kini akan berjalan otomatis 24/7 di VPS tanpa perlu komputer lokal Anda nyala terus-menerus. 🚀
