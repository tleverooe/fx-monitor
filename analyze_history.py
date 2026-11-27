"""Summarize observed BOC intraday prices and estimate time below thresholds."""
import argparse
from datetime import datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from statistics import mean

from monitor import BACKFILL, CONFIG, DATA, TZ, load

THRESHOLDS = tuple(map(Decimal, ("4.425", "4.410", "4.400", "4.380", "4.350")))
MAX_GAP = timedelta(hours=1)


def observations(code, first, now):
    rows = {}
    for source in (load(DATA, {}).get("series", {}), load(BACKFILL, {})):
        for row in source.get(code, []):
            stamp = datetime.fromisoformat(row["t"]).astimezone(TZ)
            if first <= stamp <= now:
                rows.setdefault(stamp, Decimal(str(row["v"])))
    return sorted(rows.items())


def below_periods(rows, threshold):
    periods = []
    for (start, price), (end, _) in pairwise(rows):
        if price < threshold and end - start <= MAX_GAP:
            if periods and periods[-1][1] == start:
                periods[-1] = (periods[-1][0], end)
            else:
                periods.append((start, end))
    return periods


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=datetime.fromisoformat, default=datetime.now(TZ))
    args = parser.parse_args()
    now = args.as_of.astimezone(TZ)
    start = datetime.combine(now.date() - timedelta(days=6), time.min, TZ)
    code = CONFIG["monitor_currency"]
    rows = observations(code, start, now)
    total_daily = []
    for offset in range(7):
        day = start.date() + timedelta(days=offset)
        daily = [(stamp, price) for stamp, price in rows if stamp.date() == day]
        if not daily:
            print(day, "无报价")
            continue
        prices = [price for _, price in daily]
        low, high = min(prices), max(prices)
        total_daily.append(len(daily))
        print(day, f"{len(daily)} 笔 {daily[0][0]:%H:%M:%S}–{daily[-1][0]:%H:%M:%S}",
              f"低 {low:.4f} 高 {high:.4f} 振幅 {high-low:.4f}",
              f"均 {mean(prices):.4f} 最新 {prices[-1]:.4f}")
    print(f"合计 {sum(total_daily)} 笔；每笔低价按下一笔报价时间估算，超过一小时的间隔不计。")
    for threshold in THRESHOLDS:
        hits = [stamp for stamp, price in rows if price < threshold]
        periods = below_periods(rows, threshold)
        seconds = sum((end - begin).total_seconds() for begin, end in periods)
        print(f"< {threshold}: {len(hits)} 笔，约 {seconds/60:.1f} 分钟")
        for begin, end in periods:
            print(f"  {begin:%m-%d %H:%M:%S} – {end:%m-%d %H:%M:%S}")
        for stamp in hits:
            if not any(begin <= stamp < end for begin, end in periods):
                print(f"  {stamp:%m-%d %H:%M:%S}（单点，持续时间未知）")


if __name__ == "__main__":
    main()
