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
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_5_minute, n_bars=2000)
            if hist is None or hist.empty:
                continue
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['EMA9'] = hist['Close'].ewm(span=9, adjust=False).mean()
            hist['EMA21'] = hist['Close'].ewm(span=21, adjust=False).mean()
            hist['EMA200'] = hist['Close'].ewm(span=200, adjust=False).mean() # Tren besar
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            hist['LocalSupport'] = hist['Low'].rolling(window=72).min()
            hist['LocalResistance'] = hist['High'].rolling(window=72).max()
            
            hist['PrevEMA9'] = hist['EMA9'].shift(1)
            hist['PrevEMA21'] = hist['EMA21'].shift(1)
            hist = hist.dropna()
            
            in_trade = False
            entry_price = tp_price = sl_price = 0
            
            for i in range(1, len(hist)):
                current_bar = hist.iloc[i]
                prev_bar = hist.iloc[i-1]
                
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
                ema9 = prev_bar['EMA9']
                ema21 = prev_bar['EMA21']
                ema200 = prev_bar['EMA200']
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
                
                # Sinyal difilter lebih ketat
                # Hanya beli jika harga > EMA 200 (Uptrend harian)
                if close_p < ema200:
                    continue
                    
                signals = []
                if ema9 > ema21 and close_p > ema9:
                    signals.append("Strong Uptrend")
                elif prevema9 < prevema21 and ema9 >= ema21:
                    signals.append("Golden Cross")
                    
                if ema9 > ema21 and low_p <= (ema21 + (0.5 * atr)) and close_p >= ema21:
                    signals.append("Dip at EMA21")
                
                # Syarat Rebound lebih ketat: tren harus naik
                elif low_p <= (loc_supp + atr) and close_p > loc_supp and ema9 > ema21:
                    if (open_p - low_p) > (close_p - open_p):
                        signals.append("Support Rebound")
                        
                if len(signals) > 0 and vol > (1.5 * avgvol): # Wajib ada lonjakan volume
                    in_trade = True
                    entry_price = current_bar['Open']
                    
                    # Parameter SL dilebarkan (2.5 ATR), TP dilebarkan (5 ATR)
                    tp_rr = close_p + (5.0 * atr)
                    tp_price = max(loc_res, tp_rr)
                    
                    sl_atr = close_p - (2.5 * atr)
                    sl_support = loc_supp * 0.98
                    sl_price = min(sl_atr, sl_support) # Pakai SL terjauh agar tidak gampang kena stop hunt
                    
        except Exception as e:
            pass
            
    if not all_trades:
        print("0 trades")
        return
        
    wins = [t for t in all_trades if t['status'] == 'WIN']
    capital = initial_capital
    position_size = 1000000 
    
    for t in all_trades:
        lot = (position_size // (t['entry_price'] * 100))
        if lot == 0: continue
        invested = lot * 100 * t['entry_price']
        profit = ((lot * 100 * t['exit_price']) - (lot * 100 * t['exit_price'] * fee_pct)) - (invested + (invested * fee_pct))
        capital += profit
        profit_pct = (t['exit_price'] - t['entry_price']) / t['entry_price'] * 100
        print(f"[{t['stock']}] {t['status']} | Entry: {t['entry_price']} | Exit: {t['exit_price']} | PnL: {profit_pct:.2f}% | Rp {profit:,.0f}")
        
    print(f"\nTotal: {len(all_trades)}, Win: {len(wins)}, Rate: {(len(wins)/len(all_trades))*100:.2f}%, Akhir: {capital:,.0f}")

if __name__ == "__main__":
    run_backtest()
