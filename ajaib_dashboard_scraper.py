import time
from playwright.sync_api import sync_playwright

def scrape_dashboard():
    with sync_playwright() as p:
        print("Mencoba menyambung ke browser Chrome Anda...")
        try:
            # Menyambung ke browser Chrome Anda (harus dijalankan dengan port 9222)
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
        except Exception as e:
            print("\n[!] GAGAL TERHUBUNG KE BROWSER CHROME ANDA.")
            print("Syarat Wajib: Anda harus menutup semua Chrome Anda terlebih dahulu,")
            print("lalu membukanya kembali menggunakan perintah khusus dari terminal (Lihat instruksi di chat).")
            return
            
        print("="*70)
        print("KONEKSI BERHASIL!")
        print("1. Pastikan tab Ajaib 'Multi Orderbook' sedang terbuka di browser Anda.")
        print("2. Kembali ke terminal ini dan tekan ENTER.")
        print("="*70)
        
        input("\n>>> Tekan ENTER di sini jika tampilan Ajaib sudah siap... <<<") 
        
        print("\n[+] Memulai Pemantauan Data (Scraping Real-time)...")
        print("Tekan Ctrl+C kapan saja untuk menghentikan bot.\n")
        
        try:
            while True:
                # Mencari otomatis tab mana yang sedang membuka Ajaib
                halaman_aktif = None
                for halaman in context.pages:
                    if "ajaib.co.id" in halaman.url:
                        halaman_aktif = halaman
                        break
                        
                if not halaman_aktif:
                    print("[!] Error: Tidak ada tab Ajaib yang terbuka di browser Anda.")
                    time.sleep(5)
                    continue

                waktu_sekarang = time.strftime('%H:%M:%S')
                print(f"--- Snapshot Data Waktu: {waktu_sekarang} ---")
                
                # Bot mendeteksi tabel di tab Ajaib Anda
                semua_tabel = halaman_aktif.locator("table").all()
                
                if not semua_tabel:
                    print("[!] Tidak ada tabel yang terdeteksi di layar. Pastikan Anda berada di halaman Multi Orderbook.")
                else:
                    for idx, tabel in enumerate(semua_tabel):
                        # Ambil semua baris di dalam tabel ini
                        baris_antrean = tabel.locator("tbody tr").all() 
                        
                        data_orderbook = []
                        for baris in baris_antrean:
                            # Ekstrak teks dari setiap sel (kolom td)
                            kolom = baris.locator("td").all_text_contents()
                            
                            # Berdasarkan screenshot, format tabel Ajaib memiliki 6 kolom:
                            # Freq | Lot | Bid | Ask | Lot | Freq
                            if len(kolom) == 6: 
                                try:
                                    # Fungsi kecil pembantu untuk menghapus titik (13.002 -> 13002)
                                    def bersihkan_angka(teks):
                                        return int(teks.replace('.', '').replace(',', '').strip()) if teks.strip() else 0
                                    
                                    # Memasukkan ke dalam variabel yang rapi (Tipe data: Integer)
                                    baris_bersih = {
                                        "bid_freq": bersihkan_angka(kolom[0]),
                                        "bid_lot": bersihkan_angka(kolom[1]),
                                        "bid_price": bersihkan_angka(kolom[2]),
                                        "ask_price": bersihkan_angka(kolom[3]),
                                        "ask_lot": bersihkan_angka(kolom[4]),
                                        "ask_freq": bersihkan_angka(kolom[5])
                                    }
                                    # Pastikan bukan baris kosong (harga 0)
                                    if baris_bersih["bid_price"] > 0 or baris_bersih["ask_price"] > 0:
                                        data_orderbook.append(baris_bersih)
                                except Exception as e:
                                    pass # Abaikan baris header atau teks yang gagal dikonversi
                        
                        if data_orderbook:
                            print(f"\n[+] Data Saham Kotak ke-{idx+1} (Diproses menjadi Angka):")
                            
                            # Tampilkan 2 level harga teratas sebagai bukti
                            for i, level in enumerate(data_orderbook[:2]):
                                print(f"    Antrean {i+1}: BID {level['bid_lot']} lot di {level['bid_price']}  |  ASK {level['ask_lot']} lot di {level['ask_price']}")
                            
                            # =========================================================
                            # --- MASUKKAN ALGORITMA ANALISIS ENTRY ANDA DI SINI ---
                            # =========================================================
                            # Contoh Algoritma Sederhana: 
                            # Jika Lot Bid di harga terbaik lebih besar 3x lipat dari Lot Ask
                            
                            # bid_terbaik = data_orderbook[0]
                            # if bid_terbaik['bid_lot'] > (3 * bid_terbaik['ask_lot']):
                            #     print("    >>> 🚀 SINYAL ENTRY: Tembok Bid Terdeteksi Kuat!")
                            # =========================================================
                            
                print("\n" + "-" * 60)
                # Jeda 10 detik sebelum bot mengambil data lagi (menghindari beban server berlebih)
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("\n[!] Dihentikan oleh pengguna (Ctrl+C). Terima kasih!")
            
        finally:
            browser.close()

if __name__ == "__main__":
    scrape_dashboard()
