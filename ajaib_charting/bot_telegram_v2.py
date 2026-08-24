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
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# ==========================================
# PENGATURAN SCANNER
# ==========================================
SCAN_INTERVAL_SECONDS = 300
WATCHLIST_FILE = 'watchlist.json'

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
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("[TELEGRAM] Token belum diset! Pesan:\n", message)
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

def is_market_open():
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5: 
        return False
    current_time = now.time()
    if datetime.time(9, 0) <= current_time <= datetime.time(12, 0): return True
    if datetime.time(13, 30) <= current_time <= datetime.time(16, 0): return True
    return False

def get_daily_ema(tv, stock):
    try:
        daily = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_daily, n_bars=50)
        if daily is not None and not daily.empty:
            ema34 = daily['close'].ewm(span=34, adjust=False).mean()
            return ema34.iloc[-1]
    except:
        pass
    return None

def run_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan V2 (VPA)...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    for stock in wl:
        try:
            # 1. Ambil EMA34 Daily
            daily_ema34 = get_daily_ema(tv, stock)
            
            # 2. Ambil data 5m
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=100)
            if hist is None or hist.empty or len(hist) < 21:
                continue
                
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            
            # Fokus ke candle yang baru saja closed (index -2)
            last_closed = hist.iloc[-2]
            
            close_p = last_closed['Close']
            open_p = last_closed['Open']
            high_p = last_closed['High']
            low_p = last_closed['Low']
            vol = last_closed['Volume']
            avgvol = last_closed['AvgVol20']
            atr = last_closed['ATR14']
            
            # Cek Makro Trend
            if daily_ema34 is not None and close_p < daily_ema34:
                continue
                
            # Cek Volume Spike (3x)
            if pd.isna(avgvol) or vol < (3.0 * avgvol) or vol < 5000:
                continue
                
            # Cek VPA Bullish Candle
            body = close_p - open_p
            tr = high_p - low_p
            
            if tr > 0 and body > 0:
                body_ratio = body / tr
                upper_wick = high_p - close_p
                
                if body_ratio > 0.6 and upper_wick <= (0.2 * tr):
                    candle_time = hist.index[-2].strftime("%Y%m%d_%H%M")
                    alert_id = f"{stock}_{candle_time}_V2"
                    
                    if alert_id not in alert_cache:
                        tp = int(close_p + (2.0 * atr))
                        sl = int(close_p - (1.5 * atr))
                        vol_multiplier = vol / avgvol
                        
                        msg = (
                            f"🚨 *SINYAL VPA SCALPING V2: {stock}* 🚨\n\n"
                            f"Harga: *Rp {int(close_p)}*\n"
                            f"Kondisi: *Bullish Marubozu & Volume Spike ({vol_multiplier:.1f}x)* 🚀\n\n"
                            f"🎯 *Rencana Cepat (Scalp)*\n"
                            f"• Entry: *Sekarang (Rp {int(close_p)})*\n"
                            f"• Take Profit (TP): *Rp {tp}*\n"
                            f"• Stop Loss (SL): *Rp {sl}*\n\n"
                            f"⏳ _Waktu Bar: {candle_time}_"
                        )
                        print(f"[ALERT] VPA Signal for {stock}!")
                        success = send_telegram_message(msg)
                        if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                            alert_cache[alert_id] = True

        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(1)
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM SCALPING BOT V2 AKTIF")
    print("=======================================")
    while True:
        try:
            if is_market_open():
                run_scanner()
            else:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bursa tutup. Istirahat...")
            time.sleep(SCAN_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nBerhenti...")
            break
        except Exception as e:
            print(f"Error, restart: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
