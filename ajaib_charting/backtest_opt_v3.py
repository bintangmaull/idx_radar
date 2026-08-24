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

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_backtest(initial_capital=10000000, fee_pct=0.0025):
    tv = TvDatafeed()
    wl = load_watchlist()
    all_trades = []
    test_stocks = wl[:11]
    
    for stock in test_stocks:
        try:
            # Menggunakan Data 1 Jam (1-Hour) untuk Swing agar data lebih padat
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=2000)
            if hist is None or hist.empty:
                continue
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            # Indikator Swing
            hist['EMA34'] = hist['Close'].ewm(span=34, adjust=False).mean()
            hist['EMA90'] = hist['Close'].ewm(span=90, adjust=False).mean()
            hist['RSI14'] = compute_rsi(hist['Close'])
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            
            hist = hist.dropna()
            
            in_trade = False
            entry_price = tp_price = sl_price = 0
            
            for i in range(1, len(hist)):
                current_bar = hist.iloc[i]
                prev_bar = hist.iloc[i-1]
                
                # Cek exit trade
                if in_trade:
                    if current_bar['Low'] <= sl_price:
                        exit_price = min(current_bar['Open'], sl_price) 
                        all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'LOSS'})
                        in_trade = False
                    elif current_bar['High'] >= tp_price:
                        exit_price = max(current_bar['Open'], tp_price)
                        all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'WIN'})
                        in_trade = False
                    continue
                
                vol = prev_bar['Volume']
                close_p = prev_bar['Close']
                open_p = prev_bar['Open']
                high_p = prev_bar['High']
                low_p = prev_bar['Low']
                avgvol = prev_bar['AvgVol20']
                atr = prev_bar['ATR14']
                ema34 = prev_bar['EMA34']
                ema90 = prev_bar['EMA90']
                rsi = prev_bar['RSI14']
                
                # Syarat 1: Makro Uptrend (EMA34 > EMA90)
                if ema34 < ema90 or close_p < ema90:
                    continue
                
                # Syarat 2: Pullback ke EMA34 (Low menyentuh area EMA34)
                if low_p > (ema34 * 1.03): 
                    continue # Harga masih terlalu tinggi, bukan pullback
                    
                # Syarat 3: Bullish Rebound (Mulai mantul)
                if close_p <= open_p or close_p < ema34:
                    continue # Masih turun / belum ada rejection dari support
                    
                # Syarat 4: Volume Normal/Tinggi
                if vol < (avgvol * 0.8) or vol < 5000:
                    continue
                    
                # Valid Swing Signal
                in_trade = True
                entry_price = current_bar['Open']
                
                # Coba RR 1:1.3 (TP lebih kecil untuk win rate lebih tinggi)
                sl_price = entry_price - (1.5 * atr)
                tp_price = entry_price + (2.0 * atr) 
                
        except Exception as e:
            pass
            
    if not all_trades:
        print("0 trades")
        return
        
    wins = [t for t in all_trades if t['status'] == 'WIN']
    capital = initial_capital
    position_size = 1000000 
    
    stock_stats = {}
    
    for t in all_trades:
        stock = t['stock']
        if stock not in stock_stats:
            stock_stats[stock] = {'win': 0, 'loss': 0}
            
        lot = (position_size // (t['entry_price'] * 100))
        if lot == 0: continue
        invested = lot * 100 * t['entry_price']
        profit = ((lot * 100 * t['exit_price']) - (lot * 100 * t['exit_price'] * fee_pct)) - (invested + (invested * fee_pct))
        capital += profit
        
        if t['status'] == 'WIN':
            stock_stats[stock]['win'] += 1
        else:
            stock_stats[stock]['loss'] += 1
            
    print("\n--- STATISTIK SWING TRADING PER SAHAM ---")
    for s, stats in stock_stats.items():
        total_trade = stats['win'] + stats['loss']
        win_rate = stats['win'] / total_trade * 100 if total_trade > 0 else 0
        print(f"[{s}] Trades: {total_trade} | Win: {stats['win']} | Loss: {stats['loss']} | Win Rate: {win_rate:.2f}%")
        
    print(f"\nTotal: {len(all_trades)}, Win: {len(wins)}, Rate: {(len(wins)/len(all_trades))*100:.2f}%, Akhir: {capital:,.0f}")

if __name__ == "__main__":
    run_backtest()
