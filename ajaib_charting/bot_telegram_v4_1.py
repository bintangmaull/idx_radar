import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import datetime
import os
import json
import time
import requests
import pytz
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_FILE = 'data/orderbook.db'
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")
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

def check_bandarmology(stock_code):
    url = f"https://stock.arjum.com/api/broker-summary/{stock_code}?net=false&broker_limit=20&all_data=false&flow=all"
    headers = {
        "X-API-Key": os.getenv("ARJUM_API_KEY", "YOUR_ARJUM_API_KEY_HERE"),
        "Accept": "application/json"
    }
    try:
        import requests
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            brokers = data.get("brokers", [])
            if not brokers: return None, 0, "", ""
            
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
    return None, 0, "", ""

def get_ihsg_status(tv):
    try:
        ihsg = tv.get_hist(symbol='COMPOSITE', exchange='IDX', interval=Interval.in_daily, n_bars=50)
        if ihsg is not None and not ihsg.empty:
            ema34 = ihsg['close'].ewm(span=34, adjust=False).mean()
            return ihsg['close'].iloc[-1] > ema34.iloc[-1]
    except:
        pass
    return True

def run_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan V4.1 (Smart Entry)...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    ihsg_uptrend = get_ihsg_status(tv)
        
    for stock in wl:
        try:
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=150)
            if hist is None or hist.empty or len(hist) < 90:
                continue
                
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
            
            # if not ihsg_uptrend: continue # Dinonaktifkan sesuai permintaan
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
            # Syarat volume dikembalikan super ketat (Wajib lonjakan 20% & > 5000 lot)
            if pd.isna(avgvol) or vol < (avgvol * 1.2) or vol < 5000: continue
            
            # --- CEK BANDARMOLOGI ---
            is_accum, net_val, accum_str, dist_str = check_bandarmology(stock)
                
            candle_time = hist.index[-1].strftime("%Y%m%d_%H")
            alert_id = f"{stock}_{candle_time}_V50_ULTIMATE"
            
            if alert_id not in alert_cache:
                if is_pinbar:
                    entry = int((close_p + low_p) / 2)
                    entry_text = f"Antri Beli (Buy Limit) di *Rp {entry}*"
                    cond_text = "Pinbar Rejection"
                elif is_strong_bullish:
                    entry = int(high_p * 1.01)
                    entry_text = f"Beli Saat Tembus (Buy Stop) di *Rp {entry}*"
                    cond_text = "Bullish Momentum"
                    
                if vol > (avgvol * 1.2):
                    cond_text += " & Vol Spike 🔥"
                    
                if is_accum is True:
                    cond_text += f"\n🐋 *Bandar Akumulasi* (Beli: {accum_str} | Jual: {dist_str})"
                elif is_accum is False:
                    cond_text += f"\n⚠️ *Bandar Distribusi* (Jual: {dist_str} | Beli: {accum_str}) - RISIKO TINGGI!"
                
                tp1 = int(entry + (1.0 * atr))
                tp2 = int(entry + (3.0 * atr))
                sl = int(entry - (1.5 * atr))
                
                msg = (
                    f"🧠 *SMART ENTRY V4.1: {stock}* 🧠\n\n"
                    f"Harga Penutupan: *Rp {int(close_p)}*\n"
                    f"Pola: *{cond_text}*\n\n"
                    f"🎯 *Instruksi Trading*\n"
                    f"• Eksekusi: {entry_text}\n"
                    f"• TP 1 (Jual 50%): *Rp {tp1}* (Lalu SL -> BEP)\n"
                    f"• TP 2 (Jual 50%): *Rp {tp2}*\n"
                    f"• Stop Loss: *Rp {sl}*\n\n"
                    f"⏳ _Berlaku maks 5 jam ke depan_"
                )
                print(f"[ALERT] V4.1 Signal for {stock}!")
                
                # Simpan ke database dashboard web
                try:
                    if not os.path.exists('data'):
                        os.makedirs('data')
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        CREATE TABLE IF NOT EXISTS screener_results (
                            stock_code TEXT PRIMARY KEY,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            signals TEXT,
                            entry TEXT,
                            tp INTEGER,
                            sl INTEGER
                        )
                    ''')
                    c.execute('''
                        INSERT OR REPLACE INTO screener_results 
                        (stock_code, timestamp, signals, entry, tp, sl)
                        VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                    ''', (stock, cond_text.replace('\n', ', '), entry_text, tp1, sl))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"[ERROR] Failed to save {stock} to DB: {e}")
                    
                success = send_telegram_message(msg)
                if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                    alert_cache[alert_id] = True

        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(1)
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM SMART ENTRY V5.0 AKTIF")
    print("=======================================")
    send_telegram_message("🤖 *Bot IDX V5.0 Ultimate* berhasil terhubung!\nStatus: Sedang memantau pasar...")
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
