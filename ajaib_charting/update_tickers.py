import requests
import json
import os
import re

def fetch_idx_tickers():
    print("Mengambil daftar saham IDX...")
    
    tickers = []
    
    try:
        # Sumber 1: Daftar saham dari public github dataset
        url = "https://raw.githubusercontent.com/yudiwbs/dataset-saham-idx/master/daftar_saham.csv"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            lines = res.text.split('\n')
            for line in lines[1:]: # Skip header
                if line.strip():
                    parts = line.split(',')
                    if len(parts) > 0 and len(parts[0]) == 4:
                        tickers.append(parts[0].strip().upper())
    except Exception as e:
        print("Gagal fetch dari sumber 1:", e)
        
    # Sumber cadangan jika gagal
    if len(tickers) < 100:
        print("Menggunakan metode fallback...")
        try:
            # Mencoba fetch dari sumber lain atau API IDX
            # Untuk simplifikasi, kita bisa pakai daftar hardcoded jika gagal total
            pass
        except:
            pass

    # Membersihkan dan memastikan unik
    tickers = list(set([t for t in tickers if re.match(r'^[A-Z]{4}$', t)]))
    tickers.sort()
    
    if len(tickers) > 100:
        print(f"Berhasil mendapatkan {len(tickers)} kode saham.")
        with open('all_idx.json', 'w') as f:
            json.dump(tickers, f)
        print("Tersimpan di all_idx.json")
    else:
        print("Gagal mendapatkan daftar saham yang valid. Silakan buat all_idx.json secara manual dengan isi array string kode saham, misal: [\"BBCA\", \"WIFI\", ...]")

if __name__ == '__main__':
    fetch_idx_tickers()
