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
# PENGATURAN SCANNER SWING
# ==========================================
SCAN_INTERVAL_SECONDS = 3600  # 1 Jam (Kondisi swing tidak butuh update menit)
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

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def is_market_open():
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5: 
        return False
    current_time = now.time()
    if datetime.time(9, 0) <= current_time <= datetime.time(12, 0): return True
    if datetime.time(13, 30) <= current_time <= datetime.time(16, 0): return True
    return False

def run_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan V3 (Swing Pullback)...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    for stock in wl:
        try:
            # Gunakan Timeframe 1-Hour (1 Jam)
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=500)
            if hist is None or hist.empty or len(hist) < 90:
                continue
                
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['EMA34'] = hist['Close'].ewm(span=34, adjust=False).mean()
            hist['EMA90'] = hist['Close'].ewm(span=90, adjust=False).mean()
            hist['RSI14'] = compute_rsi(hist['Close'])
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            
            last_bar = hist.iloc[-1]
            
            close_p = last_bar['Close']
            open_p = last_bar['Open']
            high_p = last_bar['High']
            low_p = last_bar['Low']
            vol = last_bar['Volume']
            avgvol = last_bar['AvgVol20']
            atr = last_bar['ATR14']
            ema34 = last_bar['EMA34']
            ema90 = last_bar['EMA90']
            rsi = last_bar['RSI14']
            
            # Filter Swing
            if ema34 < ema90 or close_p < ema90:
                continue
                
            if low_p > (ema34 * 1.03):
                continue
                
            if close_p <= open_p or close_p < ema34:
                continue
                
            if pd.isna(avgvol) or vol < (avgvol * 0.8) or vol < 5000:
                continue
                
            candle_time = hist.index[-1].strftime("%Y%m%d")
            alert_id = f"{stock}_{candle_time}_V3_SWING"
            
            if alert_id not in alert_cache:
                tp = int(close_p + (3.75 * atr))
                sl = int(close_p - (1.5 * atr))
                
                msg = (
                    f"⛺ *SINYAL SWING TRADING V3: {stock}* ⛺\n\n"
                    f"Harga Saat Ini: *Rp {int(close_p)}*\n"
                    f"Kondisi: *Pullback Rebound di EMA34 (RSI: {int(rsi)})* 📈\n\n"
                    f"🎯 *Rencana Swing (Multi-day Hold)*\n"
                    f"• Entry: *Sekarang/EOD (Rp {int(close_p)})*\n"
                    f"• Target Profit (TP): *Rp {tp} (Risk/Reward 1:2.5)*\n"
                    f"• Stop Loss (SL): *Rp {sl}*\n\n"
                    f"⏳ _Tanggal: {candle_time}_"
                )
                print(f"[ALERT] Swing Signal for {stock}!")
                success = send_telegram_message(msg)
                if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                    alert_cache[alert_id] = True

        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(1)
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM SWING BOT V3 AKTIF")
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
