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
SCAN_INTERVAL_SECONDS = 900 # Scan every 15 minutes, but limit market hours to sore
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

# Custom market open check for ARB Hunter
def is_arb_hunting_time():
    tz = pytz.timezone('Asia/Jakarta')
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5: return False
    current_time = now.time()
    # Aktif sepanjang jam bursa untuk memantau saham yang tiba-tiba di-ARB (bisa dibatasi 15:00-16:00 jika perlu)
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

def calculate_rsi(data, window=14):
    delta = data.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def run_arb_scanner():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Memulai putaran scan ARB HUNTER (Daily)...")
    tv = TvDatafeed()
    wl = load_watchlist()
    
    for stock in wl:
        hist = None
        backoff = 2
        for attempt in range(3):
            try:
                time.sleep(1.5)
                # Ambil data harian untuk melihat pergerakan drop hari ini vs kemarin
                hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_daily, n_bars=50)
                if hist is not None and not hist.empty and len(hist) >= 20:
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
                        tv = TvDatafeed()
                    except:
                        pass
                    
        if hist is None or hist.empty or len(hist) < 20:
            print(f"[SKIP] Data tidak cukup atau gagal diambil untuk {stock}")
            continue
            
        try:
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            hist['RSI14'] = calculate_rsi(hist['Close'], window=14)
            
            # Ambil 2 bar terakhir (hari ini dan kemarin)
            if len(hist) < 2: continue
            
            last_bar = hist.iloc[-1]
            prev_bar = hist.iloc[-2]
            
            close_p = last_bar['Close']
            open_p = last_bar['Open']
            high_p = last_bar['High']
            low_p = last_bar['Low']
            vol = last_bar['Volume']
            avgvol = last_bar['AvgVol20']
            rsi = last_bar['RSI14']
            
            prev_close = prev_bar['Close']
            
            # 1. Filter Drop Harga (Minimal -9% dari close kemarin) ATAU dikunci ARB (Close == Low dan turun minimal -5%)
            drop_pct = ((close_p - prev_close) / prev_close) * 100
            
            is_heavy_drop = drop_pct <= -9.0
            is_locked_arb = (close_p == low_p) and (drop_pct <= -5.0)
            
            if not (is_heavy_drop or is_locked_arb):
                continue
                
            # 2. Filter Volume: Wajib ada lonjakan volume saat drop (menandakan ada transaksi/akumulasi)
            if pd.isna(avgvol) or vol < avgvol:
                continue
                
            # 3. Filter RSI: Opsional, tapi lebih bagus kalau oversold
            rsi_str = f"{rsi:.1f}" if not pd.isna(rsi) else "N/A"
            
            # 4. Filter Bandarmologi: Wajib Akumulasi
            is_accum, net_val, accum_str, dist_str = check_bandarmology(stock)
            if is_accum is False:
                continue # Kalo didistribusi saat ARB, terlalu bahaya
                
            candle_date = hist.index[-1].strftime("%Y%m%d")
            alert_id = f"{stock}_{candle_date}_ARB_HUNTER"
            
            if alert_id not in alert_cache:
                entry_text = f"Antri Beli di *Rp {int(close_p)}*"
                tp1 = int(close_p * 1.03) # Copet 3%
                tp2 = int(close_p * 1.05) # Copet 5%
                sl = int(close_p * 0.96)  # Cutloss -4% jika masih turun besoknya
                
                status_text = "Dikunci ARB" if is_locked_arb else "Heavy Drop"
                
                msg = (
                    f"🩸 *ARB HUNTER DETECTED: {stock}* 🩸\n\n"
                    f"Status: *{status_text}*\n"
                    f"Penurunan: *{drop_pct:.2f}%*\n"
                    f"Harga Saat Ini: *Rp {int(close_p)}*\n\n"
                    f"🧐 *Kenapa Menarik?*\n"
                    f"• 🐋 Bandar Terciduk AKUMULASI (Net Buy: {accum_str} | Sell: {dist_str})\n"
                    f"• 🔥 Volume Melampaui Rata-rata Harian\n"
                    f"• 📉 Indikator RSI: *{rsi_str}*\n\n"
                    f"🎯 *Rencana Trade (Copet Besok Pagi):*\n"
                    f"• Entry: {entry_text} (Bisa antri sekarang atau tunggu Open besok)\n"
                    f"• TP 1: *Rp {tp1}* (+3%)\n"
                    f"• TP 2: *Rp {tp2}* (+5%)\n"
                    f"• Cutloss Ketat: *Rp {sl}* (-4% dari Entry)\n\n"
                    f"⚠️ _Risiko Tinggi, Gunakan Money Management_"
                )
                print(f"[ALERT] ARB Hunter Signal for {stock}!")
                
                # Simpan ke DB Dashboard jika diperlukan
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
                    ''', (stock, f"{status_text} & Bandar Akumulasi", entry_text, tp2, sl))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"[ERROR] Failed to save {stock} to DB: {e}")
                    
                success = send_telegram_message(msg)
                if success or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
                    alert_cache[alert_id] = True

        except Exception as e:
            print(f"[ERROR] Memproses {stock}: {e}")
            
        time.sleep(2)
        
def main():
    print("=======================================")
    print("🤖 TELEGRAM ARB HUNTER AKTIF")
    print("=======================================")
    send_telegram_message("🤖 *Bot ARB Hunter* berhasil terhubung!\nMencari saham diskon dan akumulasi bandar...")
    while True:
        try:
            if is_arb_hunting_time():
                run_arb_scanner()
            else:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Bukan jam pantau. Istirahat...")
            time.sleep(SCAN_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("\nBerhenti...")
            break
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    main()
