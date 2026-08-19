import pandas as pd
from tvDatafeed import TvDatafeed, Interval
import datetime
import os
import json

def load_watchlist():
    watchlist_file = 'watchlist.json'
    if os.path.exists(watchlist_file):
        try:
            with open(watchlist_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return ["WIFI", "INET", "PACK", "FAST", "KIJA", "TEBE", "BRMS", "BUMI", "VKTR", "GOTO", "ARTO"]

def run_backtest(initial_capital=10000000, fee_pct=0.0025):
    print("="*50)
    print("MEMULAI BACKTEST INTRADAY SCALPING")
    print("="*50)
    
    tv = TvDatafeed()
    wl = load_watchlist()
    
    all_trades = []
    
    # Untuk backtest kita pakai sebagian saham saja agar tidak terlalu lama
    # Jika ingin full, hilangkan slicing [:10]
    test_stocks = wl[:15]
    
    for stock in test_stocks:
        print(f"Mengunduh & memproses data {stock}...")
        try:
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=2000)
            if hist is None or hist.empty:
                continue
                
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            # --- Kalkulasi Indikator Dasar (Sama dengan server.py) ---
            hist['EMA9'] = hist['Close'].ewm(span=9, adjust=False).mean()
            hist['EMA21'] = hist['Close'].ewm(span=21, adjust=False).mean()
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            hist['LocalSupport'] = hist['Low'].rolling(window=72).min()
            hist['LocalResistance'] = hist['High'].rolling(window=72).max()
            
            # Shift data to get previous values easily
            hist['PrevEMA9'] = hist['EMA9'].shift(1)
            hist['PrevEMA21'] = hist['EMA21'].shift(1)
            
            # Drop NaN rows caused by rolling windows
            hist = hist.dropna()
            
            in_trade = False
            entry_price = 0
            tp_price = 0
            sl_price = 0
            entry_time = None
            entry_signals = ""
            
            for i in range(1, len(hist)):
                current_bar = hist.iloc[i]
                prev_bar = hist.iloc[i-1]
                
                # --- EXIT LOGIC ---
                if in_trade:
                    # Cek apakah TP atau SL tersentuh di bar ini
                    if current_bar['Low'] <= sl_price:
                        # Terkena SL (bisa slip karena gap down, tapi kita anggap SL terpenuhi)
                        exit_price = min(current_bar['Open'], sl_price) 
                        all_trades.append({
                            'stock': stock,
                            'entry_time': entry_time,
                            'exit_time': hist.index[i],
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'status': 'LOSS',
                            'signals': entry_signals
                        })
                        in_trade = False
                    elif current_bar['High'] >= tp_price:
                        # Terkena TP
                        exit_price = max(current_bar['Open'], tp_price)
                        all_trades.append({
                            'stock': stock,
                            'entry_time': entry_time,
                            'exit_time': hist.index[i],
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'status': 'WIN',
                            'signals': entry_signals
                        })
                        in_trade = False
                    continue # Jika masih in trade, jangan cari sinyal entry baru
                
                # --- ENTRY LOGIC ---
                vol = prev_bar['Volume']
                ema9 = prev_bar['EMA9']
                ema21 = prev_bar['EMA21']
                prevema9 = prev_bar['PrevEMA9']
                prevema21 = prev_bar['PrevEMA21']
                close_p = prev_bar['Close']
                open_p = prev_bar['Open']
                high_p = prev_bar['High']
                low_p = prev_bar['Low']
                avgvol = prev_bar['AvgVol20']
                atr = prev_bar['ATR14']
                loc_supp = prev_bar['LocalSupport']
                loc_res = prev_bar['LocalResistance']
                
                signals = []
                if vol > (1.5 * avgvol) and vol > 5000:
                    signals.append("Volume Aktif")
                
                if ema9 > ema21 and close_p > ema9:
                    signals.append("Strong Uptrend")
                elif prevema9 < prevema21 and ema9 >= ema21:
                    signals.append("Golden Cross")
                    
                if ema9 > ema21 and low_p <= (ema21 + (0.5 * atr)) and close_p >= ema21:
                    signals.append("Dip at EMA21")
                elif low_p <= (loc_supp + atr) and close_p > loc_supp:
                    if (open_p - low_p) > (close_p - open_p):
                        signals.append("Support Rebound")
                        
                has_rebound = "Support Rebound" in signals
                if len(signals) > 0 and (close_p > ema21 or has_rebound):
                    # Kita anggap Entry di harga Open bar berikutnya (yaitu current_bar['Open'])
                    # Karena realitanya kita bereaksi setelah bar sebelumnya selesai
                    in_trade = True
                    entry_price = current_bar['Open']
                    entry_time = hist.index[i]
                    entry_signals = ", ".join(signals)
                    
                    # TP & SL dihitung dari saat sinyal muncul (prev_bar)
                    tp_rr = close_p + (2.5 * atr)
                    tp_price = max(loc_res, tp_rr)
                    
                    sl_atr = close_p - (1.5 * atr)
                    sl_support = loc_supp * 0.99
                    sl_price = max(sl_atr, sl_support)
                    
        except Exception as e:
            print(f"Error {stock}: {e}")
            
    print("\n" + "="*50)
    print("LAPORAN HASIL BACKTEST")
    print("="*50)
    
    if not all_trades:
        print("Tidak ada transaksi yang memenuhi kriteria.")
        return
        
    wins = [t for t in all_trades if t['status'] == 'WIN']
    losses = [t for t in all_trades if t['status'] == 'LOSS']
    
    total_trades = len(all_trades)
    win_rate = (len(wins) / total_trades) * 100
    
    capital = initial_capital
    portfolio_history = [capital]
    
    position_size = 1000000 # Kita asumsikan beli Rp 1 Juta per transaksi
    
    for t in all_trades:
        # Hitung lot yang didapat (pembulatan ke bawah)
        lot = (position_size // (t['entry_price'] * 100))
        if lot == 0: continue
        
        invested = lot * 100 * t['entry_price']
        buy_fee = invested * fee_pct
        
        gross_value = lot * 100 * t['exit_price']
        sell_fee = gross_value * fee_pct
        
        net_profit = (gross_value - sell_fee) - (invested + buy_fee)
        capital += net_profit
        portfolio_history.append(capital)
        
    print(f"Total Saham Diuji   : {len(test_stocks)}")
    print(f"Total Transaksi     : {total_trades}")
    print(f"Transaksi Win       : {len(wins)}")
    print(f"Transaksi Loss      : {len(losses)}")
    print(f"Win Rate            : {win_rate:.2f}%")
    print(f"Modal Awal          : Rp {initial_capital:,.0f}")
    print(f"Modal Akhir         : Rp {capital:,.0f}")
    
    profit_pct = ((capital - initial_capital) / initial_capital) * 100
    print(f"Pertumbuhan Portofolio: {profit_pct:.2f}%")
    
    # 5 Sinyal paling untung
    print("\nSampel 5 Transaksi Terakhir:")
    for t in all_trades[-5:]:
        profit_loss_pct = ((t['exit_price'] - t['entry_price']) / t['entry_price']) * 100
        print(f"[{t['stock']}] {t['entry_time']} -> {t['status']} ({profit_loss_pct:.2f}%) | {t['signals']}")

if __name__ == "__main__":
    run_backtest()
