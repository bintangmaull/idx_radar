from tvDatafeed import TvDatafeed, Interval
import datetime

try:
    tv = TvDatafeed()
    data = tv.get_hist("WIFI", "IDX", interval=Interval.in_1_minute, n_bars=10)
    print("TV Data:")
    print(data)
except Exception as e:
    print("Error:", e)
