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

def run_backtest(initial_capital=5000000, fee_pct=0.0025):
    tv = TvDatafeed()
    wl = load_watchlist()
    all_trades = []
    
    try:
        ihsg = tv.get_hist(symbol='COMPOSITE', exchange='IDX', interval=Interval.in_daily, n_bars=300)
        ihsg['EMA34'] = ihsg['close'].ewm(span=34, adjust=False).mean()
        ihsg_map = {}
        for idx, row in ihsg.iterrows():
            ihsg_map[idx.date()] = row['close'] > row['EMA34']
    except:
        ihsg_map = {}
        
    test_stocks = wl[:11]
    
    for stock in test_stocks:
        try:
            hist = tv.get_hist(symbol=stock, exchange='IDX', interval=Interval.in_1_hour, n_bars=2000)
            if hist is None or hist.empty:
                continue
            hist.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            hist = hist.dropna()
            
            hist['EMA34'] = hist['Close'].ewm(span=34, adjust=False).mean()
            hist['EMA90'] = hist['Close'].ewm(span=90, adjust=False).mean()
            
            hist['TR'] = hist['High'] - hist['Low']
            hist['ATR14'] = hist['TR'].rolling(window=14).mean()
            hist['AvgVol20'] = hist['Volume'].rolling(window=20).mean()
            
            hist = hist.dropna()
            
            in_trade = False
            pending_order = None
            entry_price = tp1_price = tp2_price = sl_price = 0
            tp1_hit = False
            
            for i in range(1, len(hist)):
                current_bar = hist.iloc[i]
                prev_bar = hist.iloc[i-1]
                
                curr_open = current_bar['Open']
                curr_high = current_bar['High']
                curr_low = current_bar['Low']
                curr_close = current_bar['Close']
                
                if in_trade:
                    if curr_low <= sl_price:
                        exit_price = min(curr_open, sl_price)
                        if not tp1_hit:
                            all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'LOSS', 'type': 'FULL_SL'})
                        else:
                            all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'WIN', 'type': 'BEP_SL'})
                        in_trade = False
                        continue
                        
                    if not tp1_hit and curr_high >= tp1_price:
                        tp1_hit = True
                        exit_price = max(curr_open, tp1_price)
                        all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'WIN', 'type': 'TP1'})
                        sl_price = entry_price
                        
                    if tp1_hit and curr_high >= tp2_price:
                        exit_price = max(curr_open, tp2_price)
                        all_trades.append({'stock': stock, 'entry_price': entry_price, 'exit_price': exit_price, 'status': 'WIN', 'type': 'TP2'})
                        in_trade = False
                    continue
                
                if pending_order is not None:
                    pending_order['bars_waited'] += 1
                    
                    if pending_order['bars_waited'] > 5:
                        pending_order = None
                    else:
                        triggered = False
                        if pending_order['type'] == 'LIMIT':
                            if curr_low <= pending_order['price']:
                                triggered = True
                                entry_price = pending_order['price']
                        elif pending_order['type'] == 'STOP':
                            if curr_low <= pending_order['invalidation_price']:
                                pending_order = None 
                            elif curr_high >= pending_order['price']:
                                triggered = True
                                entry_price = max(curr_open, pending_order['price'])
                                
                        if triggered:
                            in_trade = True
                            tp1_hit = False
                            atr_at_entry = pending_order['atr']
                            sl_price = entry_price - (1.5 * atr_at_entry)
                            tp1_price = entry_price + (1.0 * atr_at_entry)
                            tp2_price = entry_price + (3.0 * atr_at_entry)
                            pending_order = None
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
                
                bar_date = prev_bar.name.date()
                ihsg_uptrend = ihsg_map.get(bar_date, True)
                
                if not ihsg_uptrend: continue
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
                if vol < (avgvol * 1.2) or vol < 5000: continue
                
                if is_pinbar:
                    limit_price = (close_p + low_p) / 2
                    pending_order = {
                        'type': 'LIMIT',
                        'price': limit_price,
                        'atr': atr,
                        'bars_waited': 0
                    }
                else: 
                    stop_price = high_p * 1.01
                    pending_order = {
                        'type': 'STOP',
                        'price': stop_price,
                        'invalidation_price': low_p,
                        'atr': atr,
                        'bars_waited': 0
                    }
                
        except Exception as e:
            pass
            
    if not all_trades:
        print("0 trades")
        return
        
    capital = initial_capital
    position_size = 1500000 
    stock_stats = {}
    
    for t in all_trades:
        stock = t['stock']
        if stock not in stock_stats:
            stock_stats[stock] = {'win': 0, 'loss': 0, 'tp1': 0, 'tp2': 0, 'bep': 0}
            
        lot = (position_size // (t['entry_price'] * 100))
        if lot == 0: continue
        
        if t['type'] in ['TP1', 'TP2', 'BEP_SL']:
            lot = lot // 2
            
        if lot == 0: continue
            
        invested = lot * 100 * t['entry_price']
        profit = ((lot * 100 * t['exit_price']) - (lot * 100 * t['exit_price'] * fee_pct)) - (invested + (invested * fee_pct))
        capital += profit
        
        if t['status'] == 'WIN':
            if t['type'] == 'TP1':
                stock_stats[stock]['win'] += 1
                stock_stats[stock]['tp1'] += 1
            elif t['type'] == 'TP2':
                stock_stats[stock]['tp2'] += 1
            elif t['type'] == 'BEP_SL':
                stock_stats[stock]['bep'] += 1
        else:
            stock_stats[stock]['loss'] += 1
            
    print("\n--- STATISTIK SMART ENTRY SWING (V4.1) ---")
    total_wins = total_losses = 0
    for s, stats in stock_stats.items():
        wins = stats['win']
        losses = stats['loss']
        total_wins += wins
        total_losses += losses
        total_trade = wins + losses
        win_rate = wins / total_trade * 100 if total_trade > 0 else 0
        print(f"[{s}] Trades: {total_trade} | Win: {wins} | Loss: {losses} | WR: {win_rate:.2f}% | (TP1: {stats['tp1']}, TP2: {stats['tp2']}, BEP: {stats['bep']})")
        
    total_t = total_wins + total_losses
    final_wr = total_wins / total_t * 100 if total_t > 0 else 0
    print(f"\nTotal Entry: {total_t}, Win: {total_wins}, Rate: {final_wr:.2f}%, Akhir: {capital:,.0f}")

if __name__ == "__main__":
    run_backtest()
