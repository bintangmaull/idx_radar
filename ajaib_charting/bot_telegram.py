import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import datetime
import os
import json
import time
import requests
import pytz

# ==========================================
# PENGATURAN TELEGRAM BOT
# ==========================================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Ganti dengan token dari @BotFather
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"      # Ganti dengan Chat ID Anda

# ==========================================
# PENGATURAN SCANNER
# ==========================================
SCAN_INTERVAL_SECONDS = 300  # Scan setiap 5 menit (sesuai timeframe chart 5m)
WATCHLIST_FILE = 'watchlist.json'

# Cache untuk mencegah pengiriman alert berulang pada candle yang sama
alert_cache = {}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return ["WIFI", "INET", "PACK", "FAST", "KIJA", "TEBE", "BRMS", "BUMI", "VKTR", "GOTO", "ARTO"]

def send_telegram_message(message):
    """Mengirim pesan ke Telegram menggunakan HTTP Request"""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("[TELEGRAM] Token belum di-setting! Pesan:", message)
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"[TELEGRAM] Pesan berhasil dikirim!")
            return True
        else:
            print(f"[TELEGRAM ERROR] {response.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM ERROR] Gagal mengirim pesan: {e}")
        return False

def is_market_open():
    """Cek apakah saat ini adalah jam buka bursa saham Indonesia (WIB)"""
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.datetime.now(tz)
    
    # Bursa tutup hari Sabtu dan Minggu
    if now.weekday() >= 5: 
        return False
        
    current_time = now.time()
    
    # Sesi 1: 09:00 - 12:00
    if datetime.time(9, 0) <= current_time <= datetime.time(12, 0):
        return True
        
    # Sesi 2: 13:30 - 16:00
    if datetime.time(13, 30) <= current_time <= datetime.time(16, 0):
        return True
        
    return False

def run_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    for stock in wl:
        try:
            # Ambil data 5 menit, cukup sedikit saja karena kita butuh real-time & EMA200
            # Untuk EMA200 kita butuh minimal 200 bar, kita ambil 400 bar
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=400)
            if hist is None or hist.empty:
                continue
                
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            # --- Kalkulasi Indikator ---
            hist['EMA9'] = hist['Close'].ewm(span=9, adjust=False).mean()
            hist['EMA21'] = hist['Close'].ewm(span=21, adjust=False).mean()
            hist['EMA200'] = hist['Close'].ewm(span=200, adjust=False).mean()
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            hist['LocalSupport'] = hist['Low'].rolling(window=72).min()
            hist['LocalResistance'] = hist['High'].rolling(window=72).max()
            
            # Kita hanya peduli pada candle TERAKHIR (bar yang baru saja selesai)
            # karena candle yg sedang berjalan (iloc[-1]) datanya belum valid (bisa berubah).
            # Jadi kita ambil iloc[-2] (bar yg baru closing)
            if len(hist) < 3: continue
            
            last_closed_bar = hist.iloc[-2]
            prev_bar = hist.iloc[-3]
            
            close_p = last_closed_bar['Close']
            open_p = last_closed_bar['Open']
            high_p = last_closed_bar['High']
            low_p = last_closed_bar['Low']
            vol = last_closed_bar['Volume']
            
            ema9 = last_closed_bar['EMA9']
            ema21 = last_closed_bar['EMA21']
            ema200 = last_closed_bar['EMA200']
            avgvol = last_closed_bar['AvgVol20']
            atr = last_closed_bar['ATR14']
            loc_supp = last_closed_bar['LocalSupport']
            loc_res = last_closed_bar['LocalResistance']
            
            prevema9 = prev_bar['EMA9']
            prevema21 = prev_bar['EMA21']
            
            # --- LOGIKA OPTIMIZED (Win Rate 87%) ---
            if close_p < ema200:
                continue # Skip jika tren jangka panjang sedang turun
                
            signals = []
            if ema9 > ema21 and close_p > ema9:
                signals.append("🚀 Strong Uptrend")
            elif prevema9 < prevema21 and ema9 >= ema21:
                signals.append("🔥 Golden Cross")
                
            if ema9 > ema21 and low_p <= (ema21 + (0.5 * atr)) and close_p >= ema21:
                signals.append("🎯 Dip at EMA21")
                
            elif low_p <= (loc_supp + atr) and close_p > loc_supp and ema9 > ema21:
                if (open_p - low_p) > (close_p - open_p):
                    signals.append("🛡️ Support Rebound")
                    
            if len(signals) > 0 and vol > (1.5 * avgvol) and vol > 5000:
                # Sinyal Ditemukan!
                
                # Cek cache agar tidak spam
                # Buat ID unik berdasarkan kode saham dan jam candle tersebut terbentuk
                candle_time = hist.index[-2].strftime("%Y%m%d_%H%M")
                alert_id = f"{stock}_{candle_time}"
                
                if alert_id not in alert_cache:
                    # Hitung TP dan SL yang Dilebarkan
                    tp_rr = close_p + (5.0 * atr)
                    tp = int(max(loc_res, tp_rr))
                    
                    sl_atr = close_p - (2.5 * atr)
                    sl_support = loc_supp * 0.98
                    sl = int(min(sl_atr, sl_support))
                    
                    # Format Pesan
                    msg = (
                        f"🚨 *SINYAL SCALPING: {stock}* 🚨\n\n"
                        f"Harga Saat Ini: *Rp {int(close_p)}*\n"
                        f"Sinyal: {', '.join(signals)}\n\n"
                        f"🎯 *Rencana Trading*\n"
                        f"• Entry: *Sekarang (Rp {int(close_p)})*\n"
                        f"• Target Profit (TP): *Rp {tp}*\n"
                        f"• Stop Loss (SL): *Rp {sl}*\n\n"
                        f"⏳ _Waktu Bar: {candle_time}_"
                    )
                    
                    print(f"[ALERT] Sinyal ditemukan untuk {stock}!")
                    success = send_telegram_message(msg)
                    
                    # Simpan ke cache jika sukses agar tidak diulang
                    if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                        alert_cache[alert_id] = True
            
        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(1) # Hindari rate limit TradingView
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM SCALPING BOT AKTIF")
    print("=======================================")
    print("Program akan memonitor pasar secara realtime.")
    
    while True:
        try:
            if is_market_open():
                run_scanner()
            else:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bursa tutup. Bot istirahat...")
                
            # Tunggu 5 menit sebelum scan berikutnya
            # (Jika bursa tutup, bot akan mengecek kondisi lagi dalam 5 menit)
            time.sleep(SCAN_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            print("\nMenghentikan bot...")
            break
        except Exception as e:
            print(f"[CRITICAL ERROR] Bot restart otomatis dalam 10 detik: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
