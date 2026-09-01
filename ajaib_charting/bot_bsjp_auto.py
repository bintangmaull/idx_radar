import pandas as pd
import yfinance as yf
import datetime
import os
import json
import time
import requests
import pytz
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")
ARJUM_API_KEY = os.getenv("ARJUM_API_KEY", "YOUR_ARJUM_API_KEY_HERE")

def send_telegram_message(message):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("[TELEGRAM SIMULASI]\n", message)
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error send telegram: {e}")
        return False

def check_bandarmology(stock_code):
    url = f"https://stock.arjum.com/api/broker-summary/{stock_code}?net=false&broker_limit=20&all_data=false&flow=all"
    headers = {
        "X-API-Key": ARJUM_API_KEY,
        "Accept": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            brokers = data.get("brokers", [])
            if not brokers: return False, 0, "", ""
            
            buyers = [b for b in brokers if b.get('nval', 0) > 0]
            sellers = [b for b in brokers if b.get('nval', 0) < 0]
            
            buyers.sort(key=lambda x: x.get('nval', 0), reverse=True)
            sellers.sort(key=lambda x: x.get('nval', 0))
            
            top_buyers = [b.get('broker_code', '') for b in buyers[:3]]
            top_sellers = [b.get('broker_code', '') for b in sellers[:3]]
            
            total_buy_val = sum([b.get('nval', 0) for b in buyers[:3]])
            total_sell_val = abs(sum([b.get('nval', 0) for b in sellers[:3]]))
            
            is_accum = total_buy_val > total_sell_val
            net_val = total_buy_val - total_sell_val
            
            return is_accum, net_val, ','.join(top_buyers), ','.join(top_sellers)
    except:
        pass
    return False, 0, "", ""

def load_all_tickers():
    if os.path.exists('all_idx.json'):
        with open('all_idx.json', 'r') as f:
            return json.load(f)
    return ["BBCA", "BMRI", "WIFI", "GOTO"] # Fallback

def run_mass_scan():
    tickers = load_all_tickers()
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai mass scan BSJP untuk {len(tickers)} saham...")
    
    # Download massal
    yf_tickers = [t + ".JK" for t in tickers]
    try:
        # Progress=False agar tidak print baris panjang di console
        data = yf.download(yf_tickers, period="50d", group_by="ticker", progress=False)
    except Exception as e:
        print(f"Gagal download yfinance: {e}")
        return
        
    candidates = []
    
    print("Memproses data teknikal...")
    for stock in tickers:
        try:
            df = data[stock + ".JK"]
            if df.empty or len(df) < 25:
                continue
                
            df = df.dropna()
            if len(df) < 2:
                continue
                
            df['AvgVol20'] = df['Volume'].rolling(window=20).mean()
            
            last_bar = df.iloc[-1]
            prev_bar = df.iloc[-2]
            
            close_p = last_bar['Close']
            open_p = last_bar['Open']
            high_p = last_bar['High']
            low_p = last_bar['Low']
            vol = last_bar['Volume']
            avgvol = last_bar['AvgVol20']
            prev_close = prev_bar['Close']
            
            # --- FILTER TEKNIKAL KETAT ---
            if prev_close <= 50: continue # Bukan gocap
            
            price_return = (close_p - prev_close) / prev_close
            if price_return < 0.04: continue # Naik > 4%
                
            if pd.isna(avgvol) or vol <= (1.5 * avgvol): continue # Volume Breakout
                
            # Volume dari Yahoo Finance untuk IDX adalah lembar saham
            transaction_value = vol * close_p
            if transaction_value < 1000000000: continue # Transaksi > 1 Miliar
            
            candidates.append({
                "stock": stock,
                "close": close_p,
                "low": low_p,
                "high": high_p,
                "return": price_return
            })
            
        except Exception as e:
            # Jika saham tidak ada datanya (misal delisted), abaikan saja
            pass
            
    print(f"Lolos filter teknikal: {len(candidates)} saham.")
    if not candidates:
        send_telegram_message("🤖 *BSJP Auto Scan*\nTidak ada saham yang memenuhi kriteria ketat teknikal hari ini.")
        return
        
    # --- CEK BANDARMOLOGI ---
    print("Mengecek bandarmologi kandidat...")
    final_picks = []
    
    for cand in candidates:
        stock = cand["stock"]
        print(f"Mengecek broker summary {stock}...")
        is_accum, net_val, accum_str, dist_str = check_bandarmology(stock)
        
        if is_accum:
            cand["accum_str"] = accum_str
            final_picks.append(cand)
        time.sleep(1) # Jeda sedikit untuk API Arjum
        
    if not final_picks:
        send_telegram_message(f"🤖 *BSJP Auto Scan*\nAda {len(candidates)} saham lolos teknikal, tapi **TIDAK ADA** yang diakumulasi bandar. Skip beli hari ini.")
        return
        
    # Format Pesan Telegram
    msg = f"🌅 *BSJP AUTO RADAR (15:30 WIB)* 🌅\n"
    msg += f"_Ditemukan {len(final_picks)} saham super momentum!_\n\n"
    
    for p in final_picks:
        stock = p["stock"]
        close_p = int(p["close"])
        low_p = int(p["low"])
        ret = p["return"] * 100
        
        tp1 = int(close_p * 1.015)
        tp2 = int(close_p * 1.03)
        sl = int(min(close_p * 0.98, low_p * 0.99))
        
        msg += f"🔥 *{stock}* (Naik {ret:.1f}%)\n"
        msg += f"• Harga Beli: *Rp {close_p}*\n"
        msg += f"• Target Jual Pagi: *Rp {tp1} - Rp {tp2}*\n"
        msg += f"• Stop Loss: *Rp {sl}*\n"
        msg += f"• Bandar (Top 3): {p['accum_str']}\n\n"
        
    msg += "⚠️ _Gunakan dana terukur & disiplin Stop Loss!_"
    
    print("Mengirim ke Telegram...")
    send_telegram_message(msg)
    print("Selesai.")

def main_loop():
    print("=======================================")
    print("🤖 BOT AUTO BSJP 15:30 WIB AKTIF")
    print("=======================================")
    send_telegram_message("🤖 *Bot Auto BSJP* berhasil terhubung!\nAkan melakukan scan massal setiap jam 15:30 WIB.")
    
    while True:
        try:
            tz = pytz.timezone('Asia/Jakarta')
            now = datetime.datetime.now(tz)
            
            # Hanya Senin - Jumat
            if now.weekday() < 5:
                # Cek apakah jam 15:30
                if now.hour == 15 and now.minute == 30:
                    run_mass_scan()
                    # Sleep 60 detik agar tidak trigger berkali-kali di menit yang sama
                    time.sleep(61)
                    
            # Cek setiap 30 detik
            time.sleep(30)
            
        except KeyboardInterrupt:
            print("\nBerhenti...")
            break
        except Exception as e:
            print(f"Error di loop utama: {e}")
            time.sleep(60)

if __name__ == "__main__":
    # Jika dipanggil manual dengan argument "test", langsung run 1x
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        run_mass_scan()
    else:
        main_loop()
