from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import datetime
import os
import yfinance as yf
import threading
import time
import json
from tvDatafeed import TvDatafeed, Interval

tv = TvDatafeed()

app = Flask(__name__)
# Cache untuk menyimpan data Support & Resistance (agar tidak kena limit API)
sr_cache = {}
# Izinkan ekstensi Chrome untuk mengirim data (Cross-Origin Resource Sharing)
CORS(app)  

DB_FILE = 'data/orderbook.db'

def init_db():
    if not os.path.exists('data'):
        os.makedirs('data')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orderbook_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            stock_code TEXT,
            total_bid_lot INTEGER,
            total_ask_lot INTEGER
        )
    ''')
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
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/record', methods=['POST'])
def record():
    data = request.json
    if not data or 'stock_code' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid data'}), 400
        
    stock_code = data['stock_code']
    total_bid_lot = data.get('total_bid_lot', 0)
    total_ask_lot = data.get('total_ask_lot', 0)
    
    # Hanya simpan jika ada data valid
    if total_bid_lot == 0 and total_ask_lot == 0:
        return jsonify({'status': 'ignored'})
        
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO orderbook_history (stock_code, total_bid_lot, total_ask_lot)
        VALUES (?, ?, ?)
    ''', (stock_code, total_bid_lot, total_ask_lot))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/api/history/<stock_code>')
def get_history(stock_code):
    # Ambil 300 data terakhir (sekitar 5 menit jika polling per detik)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, total_bid_lot, total_ask_lot 
        FROM orderbook_history 
        WHERE stock_code = ? 
        ORDER BY timestamp DESC 
        LIMIT 300
    ''', (stock_code,))
    
    # Dibalik agar urutannya berdasar waktu lama ke baru (kiri ke kanan di grafik)
    rows = reversed(c.fetchall())
    conn.close()
    
    history = []
    for row in rows:
        # Format waktu menjadi HH:MM:SS
        dt = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        # Konversi waktu UTC default sqlite ke WIB (opsional, untuk sederhana kita biarkan)
        # Tapi kita format ambil jam saja
        time_str = dt.strftime('%H:%M:%S')
        
        history.append({
            'timestamp': time_str,
            'bid': row[1] / 1000, # Jadikan dalam satuan 'Ribuan Lot' (k) agar grafik rapi
            'ask': row[2] / 1000
        })
        
    return jsonify(history)

@app.route('/api/sr/<stock_code>')
def get_support_resistance(stock_code):
    now = datetime.datetime.now()
    # Gunakan cache jika data kurang dari 1 jam
    if stock_code in sr_cache:
        cached_data, cached_time = sr_cache[stock_code]
        if now - cached_time < datetime.timedelta(hours=1):
            return jsonify(cached_data)

    try:
        # Ambil data 5 hari terakhir
        hist = tv.get_hist(symbol=stock_code, exchange='IDX', interval=Interval.in_daily, n_bars=5)
        
        if hist is None or len(hist) < 2:
            return jsonify({"status": "error", "message": "Data tidak cukup"}), 404
            
        hist.rename(columns={'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)

            
        # Ambil data H-1 (hari sebelumnya) untuk perhitungan Pivot yang akurat
        prev_day = hist.iloc[-2]
        
        high = prev_day['High']
        low = prev_day['Low']
        close = prev_day['Close']
        
        # Rumus Pivot Point Standard (TradingView)
        pivot = (high + low + close) / 3
        support1 = (pivot * 2) - high
        resistance1 = (pivot * 2) - low
        
        result = {
            "status": "success",
            "support": int(round(support1, 0)),
            "resistance": int(round(resistance1, 0)),
            "pivot": int(round(pivot, 0))
        }
        
        sr_cache[stock_code] = (result, now)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stocks')
def get_stocks():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT DISTINCT stock_code FROM orderbook_history ORDER BY stock_code')
    rows = c.fetchall()
    conn.close()
    return jsonify([row[0] for row in rows])

@app.route('/api/screener/latest/<stock_code>')
def get_latest_screener_result(stock_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT timestamp, signals, entry, tp, sl 
        FROM screener_results 
        WHERE stock_code = ?
    ''', (stock_code,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            "status": "success",
            "timestamp": row[0],
            "signals": row[1],
            "entry": row[2],
            "tp": row[3],
            "sl": row[4]
        })
    else:
        return jsonify({"status": "not_found", "message": "Belum ada hasil scan untuk saham ini"}), 200

# ========================================================
# FITUR SCREENER EOD (SAHAM GORENGAN)
# ========================================================

WATCHLIST_FILE = 'watchlist.json'
DEFAULT_WATCHLIST = [
    "WIFI", "INET", "PACK", "FAST", "KIJA", "TEBE", "BRMS", "BUMI", "VKTR", 
    "GOTO", "ARTO", "BBYB", "BANK", "NCKL", "PGEO", "PTMP", "OMED", "RAJA", 
    "ENRG", "DEWA", "MEDC", "AKRA", "ESSA", "HRUM", "ADMR", "PANI", "SMRA", 
    "BSDE", "CTRA", "ASRI", "MLPL", "MPPA", "LPPF"
]

scan_state = {
    "status": "idle",
    "log": [],
    "results": [],
    "percent": 0
}

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_WATCHLIST

def save_watchlist(wl):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(wl, f)

@app.route('/api/watchlist', methods=['GET', 'POST'])
def manage_watchlist():
    if request.method == 'POST':
        data = request.json
        if data and 'watchlist' in data:
            new_wl = [s.strip().upper() for s in data['watchlist'] if s.strip()]
            save_watchlist(new_wl)
            return jsonify({"status": "success", "watchlist": new_wl})
    return jsonify({"watchlist": load_watchlist()})

@app.route('/api/scan/start', methods=['POST'])
def start_scan():
    global scan_state
    if scan_state["status"] == "scanning":
        return jsonify({"status": "error", "message": "Scan already running"})
        
    data = request.json or {}
    timeframe = data.get('timeframe', '5m')
    algorithm = data.get('algorithm', 'v1')
        
    scan_state = {
        "status": "scanning",
        "log": [f"Memulai scanning ({algorithm.upper()} - {timeframe})..."],
        "results": [],
        "percent": 0
    }
    
    if algorithm == 'v4':
        thread = threading.Thread(target=run_scanner_v4)
    else:
        thread = threading.Thread(target=run_scanner_v1, args=(timeframe,))
        
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "success"})

@app.route('/api/scan/progress')
def get_scan_progress():
    return jsonify(scan_state)

def run_scanner_v1(timeframe='5m'):
    global scan_state
    wl = load_watchlist()
    total = len(wl)
    
    for i, stock in enumerate(wl):
        scan_state["log"].append(f"Menganalisa {stock} ({i+1}/{total})...")
        try:
            # --- INTRADAY SCALPING SETUP ---
            if timeframe == '1m':
                # Mengambil data intraday dengan interval 1 menit (400 bars = ~1 hari)
                hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_minute, n_bars=400)
            else:
                # Mengambil data intraday dengan interval 5 menit (400 bars = ~5 hari)
                hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=400)
            
            if hist is None or hist.empty:
                scan_state["log"].append(f"-> Tidak ada data untuk {stock}")
                continue
                
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()

            
            if len(hist) >= 72: # Butuh minimal 1 hari data (72 bar)
                last_row = hist.iloc[-1]
                close_price = last_row['Close']
                open_price = last_row['Open']
                high_price = last_row['High']
                low_price = last_row['Low']
                volume = last_row['Volume']
                
                # Kalkulasi Delay
                import pytz
                from datetime import datetime
                jkt_tz = pytz.timezone('Asia/Jakarta')
                now_jkt = datetime.now(jkt_tz)
                last_time = hist.index[-1]
                
                if last_time.tzinfo is None:
                    last_time = jkt_tz.localize(last_time)
                else:
                    last_time = last_time.astimezone(jkt_tz)
                    
                delay_minutes = int((now_jkt - last_time).total_seconds() / 60)
                if delay_minutes < 0: delay_minutes = 0
                time_str = last_time.strftime("%H:%M")
                
                # EMA 9 dan 21 untuk Intraday Trend
                hist['EMA9'] = hist['Close'].ewm(span=9, adjust=False).mean()
                hist['EMA21'] = hist['Close'].ewm(span=21, adjust=False).mean()
                
                ema9 = hist['EMA9'].iloc[-1]
                ema21 = hist['EMA21'].iloc[-1]
                prev_ema9 = hist['EMA9'].iloc[-2]
                prev_ema21 = hist['EMA21'].iloc[-2]
                
                # Rata-rata Volume 20 bar (100 menit)
                avg_vol_20 = hist['Volume'].tail(20).mean()
                
                # Intraday ATR (14 bar) untuk volatilitas
                hist['TR'] = hist['High'] - hist['Low'] # Simple TR intraday
                atr_14 = hist['TR'].tail(14).mean()
                
                # Local Support & Resistance (72 bar terakhir = ~1 hari)
                local_support = hist['Low'].tail(72).min()
                local_resistance = hist['High'].tail(72).max()
                
                signals = []
                
                # 1. Volume Aktif (Volume saat ini > 1.5x rata-rata 20 bar)
                if volume > (1.5 * avg_vol_20) and volume > 5000:
                    signals.append("🔥 Volume Aktif")
                    
                # 2. Tren Naik (Strong Uptrend) - Harga berada di atas EMA9 dan EMA21
                if ema9 > ema21 and close_price > ema9:
                    signals.append("📈 Strong Uptrend")
                elif prev_ema9 < prev_ema21 and ema9 >= ema21:
                    signals.append("🚀 Golden Cross")
                    
                # 3. Buy on Dip (Sedang koreksi wajar ke area EMA21 atau Support)
                if ema9 > ema21 and low_price <= (ema21 + (0.5 * atr_14)) and close_price >= ema21:
                    signals.append("🎯 Dip at EMA21")
                elif low_price <= (local_support + atr_14) and close_price > local_support:
                    # Pastikan juga membentuk rejection (shadow bawah)
                    if (open_price - low_price) > (close_price - open_price):
                        signals.append("🎯 Support Rebound")
                        
                # 4. Filter Keketatan (Hanya tampilkan jika saham punya tren ATAU rebound ATAU volume spike)
                # Jika tidak ada sinyal sama sekali, kita tidak memasukannya ke hasil.
                if len(signals) > 0 and (close_price > ema21 or "🎯 Support Rebound" in signals):
                    score = len(signals)
                    if close_price > ema9:
                        score += 1
                        
                    # --- SCALPING TRADING PLAN ---
                    # 1. Entry: Area sedekat mungkin dengan harga saat ini, diskon maksimal 0.5 ATR
                    entry_bottom = int(close_price - (0.5 * atr_14))
                    entry_bottom = max(entry_bottom, int(local_support))
                    entry_bottom = min(entry_bottom, int(close_price))
                    entry_range = f"{entry_bottom} - {int(close_price)}"
                    
                    # 2. Target Profit (TP): 
                    # Jika local resistance masih jauh, pakai itu. Jika dekat, pakai R:R minimal 1:2.5 dari ATR
                    tp_rr = close_price + (2.5 * atr_14)
                    tp = int(max(local_resistance, tp_rr))
                        
                    # 3. Stop Loss (SL): Ketat di bawah Support Lokal atau 1.5 ATR
                    sl_atr = close_price - (1.5 * atr_14)
                    sl_support = local_support * 0.99
                    # Pakai stoploss yang paling aman (lebih tinggi / terdekat) untuk membatasi risiko
                    sl = int(max(sl_atr, sl_support))
                    
                    scan_state["results"].append({
                        "stock": stock,
                        "close": int(close_price),
                        "support": int(local_support),
                        "resistance": int(local_resistance),
                        "signals": signals,
                        "score": score,
                        "entry": entry_range,
                        "tp": tp,
                        "sl": sl,
                        "data_time": time_str,
                        "delay": delay_minutes
                    })
                    
                    # Simpan ke Database
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('''
                        INSERT OR REPLACE INTO screener_results 
                        (stock_code, timestamp, signals, entry, tp, sl)
                        VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                    ''', (stock, ', '.join(signals), entry_range, tp, sl))
                    conn.commit()
                    conn.close()
                    
                    scan_state["log"].append(f"-> {stock} masuk radar! {', '.join(signals)}")
                    
        except Exception as e:
            scan_state["log"].append(f"-> Error menganalisa {stock}: {str(e)}")
            
        scan_state["percent"] = int(((i + 1) / total) * 100)
        time.sleep(2) # Jeda agar tidak kena block
        
    # Urutkan berdasarkan skor tertinggi setelah selesai
    scan_state["results"].sort(key=lambda x: x["score"], reverse=True)
    scan_state["status"] = "finished"
    scan_state["log"].append("✅ Scanning selesai.")

def check_bandarmology(stock_code):
    url = f"https://stock.arjum.com/api/broker-summary/{stock_code}?net=false&broker_limit=20&all_data=false&flow=all"
    headers = {
        "X-API-Key": "sk_live_ml1n2K7otE_C486JoyoXxagO4P1b71MllKv79_xWeR4",
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

def run_scanner_v4():
    global scan_state
    wl = load_watchlist()
    total = len(wl)
    
    def get_ihsg_status_local():
        try:
            ihsg = tv.get_hist(symbol='COMPOSITE', exchange='IDX', interval=Interval.in_daily, n_bars=50)
            if ihsg is not None and not ihsg.empty:
                ema34 = ihsg['close'].ewm(span=34, adjust=False).mean()
                return ihsg['close'].iloc[-1] > ema34.iloc[-1]
        except:
            pass
        return True
        
    ihsg_uptrend = get_ihsg_status_local()
    if not ihsg_uptrend:
        scan_state["log"].append("[IHSG] Market sedang Downtrend. Bot V4.1 hanya mencari setup terkuat.")
    else:
        scan_state["log"].append("[IHSG] Market sedang Uptrend. Bot beroperasi normal.")
        
    for i, stock in enumerate(wl):
        scan_state["log"].append(f"Menganalisa {stock} ({i+1}/{total})...")
        try:
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=150)
            if hist is None or hist.empty or len(hist) < 90:
                scan_state["log"].append(f"-> Tidak ada data cukup untuk {stock}")
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
            
            import pytz
            from datetime import datetime
            import pandas as pd
            jkt_tz = pytz.timezone('Asia/Jakarta')
            now_jkt = datetime.now(jkt_tz)
            last_time = hist.index[-1]
            if last_time.tzinfo is None:
                last_time = jkt_tz.localize(last_time)
            else:
                last_time = last_time.astimezone(jkt_tz)
                
            delay_minutes = int((now_jkt - last_time).total_seconds() / 60)
            if delay_minutes < 0: delay_minutes = 0
            time_str = last_time.strftime("%H:%M")
            
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
            import pandas as pd
            # Syarat volume dikembalikan super ketat (Wajib lonjakan 20% & > 5000 lot)
            if pd.isna(avgvol) or vol < (avgvol * 1.2) or vol < 5000: continue
            
            # --- CEK BANDARMOLOGI ---
            is_accum, net_val, accum_str, dist_str = check_bandarmology(stock)
                
            signals = []
            if is_pinbar:
                signals.append("📌 Pinbar Rejection")
                entry = int((close_p + low_p) / 2)
                entry_range = f"Buy Limit @ {entry}"
            elif is_strong_bullish:
                signals.append("💪 Bullish Momentum")
                entry = int(high_p * 1.01)
                entry_range = f"Buy Stop @ {entry}"
                
            if vol > (avgvol * 1.2):
                signals.append("🔥 Vol Spike")
                
            # Hitung Skor Keyakinan (Base 70%)
            confidence = 70
            
            if is_pinbar and body > 0:
                wick_ratio = lower_wick / body
                if wick_ratio > 3: confidence += 10
                elif wick_ratio > 2: confidence += 5
                
            if not pd.isna(avgvol) and avgvol > 0:
                vol_ratio = vol / avgvol
                if vol_ratio > 2.0: confidence += 10
                elif vol_ratio > 1.5: confidence += 5
                
            distance = abs(low_p - ema34) / ema34
            if distance <= 0.01: confidence += 10
            elif distance <= 0.02: confidence += 5
            
            # Bonus Bandarmologi
            if is_accum is True:
                confidence += 15
                signals.append(f"🐋 Akum: {accum_str} | Dis: {dist_str}")
            elif is_accum is False:
                confidence -= 20
                signals.append(f"⚠️ Dis: {dist_str} | Akum: {accum_str}")
            
            confidence = min(confidence, 99) # Maksimal 99%
            
            tp1 = int(entry + (1.0 * atr))
            tp2 = int(entry + (3.0 * atr))
            sl = int(entry - (1.5 * atr))
            
            scan_state["results"].append({
                "stock": stock,
                "close": int(close_p),
                "support": int(ema34), 
                "resistance": int(tp2),
                "signals": signals,
                "score": confidence, 
                "confidence": confidence,
                "entry": entry_range,
                "tp": f"TP1: {tp1} | TP2: {tp2}",
                "sl": sl,
                "data_time": time_str,
                "delay": delay_minutes
            })
            
            # Simpan ke Database
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO screener_results 
                (stock_code, timestamp, signals, entry, tp, sl)
                VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            ''', (stock, ', '.join(signals), entry_range, tp1, sl))
            conn.commit()
            conn.close()
            
            scan_state["log"].append(f"-> {stock} masuk radar V4.1! {signals[0]}")
            
        except Exception as e:
            scan_state["log"].append(f"-> Error menganalisa {stock}: {str(e)}")
            
        scan_state["percent"] = int(((i + 1) / total) * 100)
        time.sleep(1) 
        
    scan_state["results"].sort(key=lambda x: x["score"], reverse=True)
    scan_state["status"] = "finished"
    scan_state["log"].append("✅ Scanning V4.1 selesai.")

if __name__ == '__main__':
    # Memastikan folder templates ada
    if not os.path.exists('templates'):
        os.makedirs('templates')
        
    init_db()
    print("="*60)
    print("SERVER DATABASE & CHARTING AJAIB MENYALA")
    print("Buka dashboard grafik di: http://localhost:5000")
    print("="*60)
    app.run(host='0.0.0.0', port=5000, debug=True)
