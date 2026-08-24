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
    tv = TvDatafeed()
    wl = load_watchlist()
    all_trades = []
    test_stocks = wl[:11]
    
    for stock in test_stocks:
        try:
            # 1. Fetch Daily Data for Macro Trend (EMA34)
            daily_hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_daily, n_bars=100)
            if daily_hist is None or daily_hist.empty:
                continue
            daily_hist['Daily_EMA34'] = daily_hist['close'].ewm(span=34, adjust=False).mean()
            
            daily_ema_map = {}
            for idx, row in daily_hist.iterrows():
                daily_ema_map[idx.date()] = row['Daily_EMA34']

            # 2. Fetch 5m Data
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=2000)
            if hist is None or hist.empty:
                continue
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
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
                
                # Analisis VPA
                vol = prev_bar['Volume']
                close_p = prev_bar['Close']
                open_p = prev_bar['Open']
                high_p = prev_bar['High']
                low_p = prev_bar['Low']
                avgvol = prev_bar['AvgVol20']
                atr = prev_bar['ATR14']
                
                bar_date = prev_bar.name.date()
                daily_ema34 = daily_ema_map.get(bar_date, None)
                
                # Syarat 1: Makro Uptrend (Daily Close > Daily EMA34)
                if daily_ema34 is None or close_p < daily_ema34:
                    continue
                
                # Syarat 2: Volume Spike (Minimal 3x rata-rata)
                if vol < (3.0 * avgvol) or vol < 5000:
                    continue
                    
                # Syarat 3: VPA Bullish Candle (Body > 60% of TR, Close dekat High)
                body = close_p - open_p
                tr = high_p - low_p
                
                if tr == 0: 
                    continue
                    
                is_bullish = body > 0
                body_ratio = body / tr
                upper_wick = high_p - close_p
                
                if is_bullish and body_ratio > 0.6 and upper_wick <= (0.2 * tr):
                    in_trade = True
                    entry_price = current_bar['Open']
                    
                    # Parameter TP/SL untuk Scalping: TP = 2.0x ATR, SL = 1.5x ATR
                    tp_price = entry_price + (2.0 * atr)
                    sl_price = entry_price - (1.5 * atr)
                    
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
            
    print("\n--- STATISTIK PER SAHAM ---")
    for s, stats in stock_stats.items():
        total_trade = stats['win'] + stats['loss']
        win_rate = stats['win'] / total_trade * 100 if total_trade > 0 else 0
        print(f"[{s}] Trades: {total_trade} | Win: {stats['win']} | Loss: {stats['loss']} | Win Rate: {win_rate:.2f}%")
        
    print(f"\nTotal: {len(all_trades)}, Win: {len(wins)}, Rate: {(len(wins)/len(all_trades))*100:.2f}%, Akhir: {capital:,.0f}")

if __name__ == "__main__":
    run_backtest()
