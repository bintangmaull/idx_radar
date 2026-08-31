import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import datetime
import os
import json
import time
import requests
import pytz

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
SCAN_INTERVAL_SECONDS = 3600
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
        print("[TELEGRAM] Pesan:\n", message)
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except:
        return False

def is_market_open():
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5: return False
    current_time = now.time()
    if datetime.time(9, 0) <= current_time <= datetime.time(12, 0): return True
    if datetime.time(13, 30) <= current_time <= datetime.time(16, 0): return True
    return False

def get_ihsg_status(tv):
    backoff = 2
    for attempt in range(3):
        try:
            ihsg = tv.get_hist(symbol='COMPOSITE', exchange='IDX', interval=Interval.in_daily, n_bars=50)
            if ihsg is not None and not ihsg.empty:
                ema34 = ihsg['close'].ewm(span=34, adjust=False).mean()
                return ihsg['close'].iloc[-1] > ema34.iloc[-1]
            else:
                print(f"[IHSG RETRY {attempt+1}] Data kosong/None untuk IHSG, menunggu {backoff} detik...")
                time.sleep(backoff)
                backoff *= 2
        except Exception as e:
            print(f"[IHSG RETRY {attempt+1}] Gagal mengambil data IHSG: {e}, menunggu {backoff} detik...")
            time.sleep(backoff)
            backoff *= 2
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                try: tv = TvDatafeed()
                except: pass
    return True

def run_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan V4 (Ultimate Swing)...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    ihsg_uptrend = get_ihsg_status(tv)
    if not ihsg_uptrend:
        print("[IHSG] Market sedang Downtrend. Bot lebih konservatif.")
    else:
        print("[IHSG] Market sedang Uptrend. Bot beroperasi normal.")
        
    for stock in wl:
        hist = None
        backoff = 2
        for attempt in range(3):
            try:
                hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=150)
                if hist is not None and not hist.empty and len(hist) >= 90:
                    break
                else:
                    print(f"[RETRY {attempt+1}] Data kosong/None untuk {stock}, menunggu {backoff} detik...")
                    time.sleep(backoff)
                    backoff *= 2
            except Exception as e:
                print(f"[RETRY {attempt+1}] Gagal mengambil data {stock}: {e}, menunggu {backoff} detik...")
                time.sleep(backoff)
                backoff *= 2
                if "timeout" in str(e).lower() or "connection" in str(e).lower():
                    try:
                        tv = TvDatafeed() # Re-init
                    except:
                        pass
                    
        if hist is None or hist.empty or len(hist) < 90:
            print(f"[SKIP] Data tidak cukup atau gagal diambil untuk {stock}")
            continue
            
        try:
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['EMA34'] = hist['Close'].ewm(span=34, adjust=False).mean()
            hist['EMA90'] = hist['Close'].ewm(span=90, adjust=False).mean()
            
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
            
            if not ihsg_uptrend:
                continue
                
            if ema34 < ema90 or close_p < ema90: continue
            if low_p > (ema34 * 1.03): continue
            
            body = abs(close_p - open_p)
            tr = high_p - low_p
            lower_wick = min(open_p, close_p) - low_p
            if tr == 0: continue
            
            is_bullish = close_p > open_p
            is_pinbar = lower_wick > (1.5 * body) and close_p > ema34
            is_strong_bullish = is_bullish and body > (0.6 * tr) and close_p > ema34
            
            if not (is_pinbar or is_strong_bullish): continue
            if pd.isna(avgvol) or vol < (avgvol * 1.2) or vol < 5000: continue
                
            candle_time = hist.index[-1].strftime("%Y%m%d_%H")
            alert_id = f"{stock}_{candle_time}_V4_ULTIMATE"
            
            if alert_id not in alert_cache:
                tp1 = int(close_p + (1.0 * atr))
                tp2 = int(close_p + (3.0 * atr))
                sl = int(close_p - (1.5 * atr))
                
                cond_text = "Pinbar Rejection" if is_pinbar else "Bullish Engulfing/Strong Body"
                
                msg = (
                    f"👑 *ULTIMATE SWING V4: {stock}* 👑\n\n"
                    f"Harga Saat Ini: *Rp {int(close_p)}*\n"
                    f"Konfirmasi: *{cond_text} & Vol Spike* 📈\n"
                    f"IHSG Filter: *Uptrend (Aman)*\n\n"
                    f"🎯 *Rencana Partial TP (50%-50%)*\n"
                    f"• Entry: *Rp {int(close_p)}*\n"
                    f"• TP 1 (Jual 50%): *Rp {tp1}* (Pindah SL ke Entry/BEP)\n"
                    f"• TP 2 (Jual 50%): *Rp {tp2}*\n"
                    f"• Stop Loss Awal: *Rp {sl}*\n\n"
                    f"⏳ _Jam: {candle_time}_"
                )
                print(f"[ALERT] V4 Signal for {stock}!")
                success = send_telegram_message(msg)
                if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                    alert_cache[alert_id] = True

        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(1)
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM ULTIMATE SWING V4 AKTIF")
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
            time.sleep(10)

if __name__ == "__main__":
    main()
