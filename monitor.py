"""Collect Bank of China telegraphic-transfer selling rates."""
import argparse
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from notify import destinations, send

TZ = timezone(timedelta(hours=8))
URL = "https://www.boc.cn/sourcedb/whpj/"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "docs" / "rates.json"
STATE = ROOT / "state.json"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PERIODS = (7, 30, 90)


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


class QuoteTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.tables_open = []
        self.cell_open = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables_open.append([])
        elif self.tables_open:
            rows = self.tables_open[-1]
            if tag == "tr":
                rows.append([])
            elif tag in ("th", "td") and rows:
                rows[-1].append("")
                self.cell_open = True

    def handle_endtag(self, tag):
        if tag == "table" and self.tables_open:
            self.tables.append(self.tables_open.pop())
        if tag in ("th", "td", "tr", "table"):
            self.cell_open = False

    def handle_data(self, data):
        if self.tables_open and self.cell_open:
            self.tables_open[-1][-1][-1] += data


def parse_quotes(html, currencies, collected_at):
    names = {name: code for code, name in currencies.items()}
    required = ("货币名称", "现汇卖出价", "发布日期", "发布时间")
    quotes = {}
    parser = QuoteTableParser()
    parser.feed(html)
    for table in parser.tables:
        columns = None
        for row in table:
            cells = [cell.strip() for cell in row]
            headers = ["".join(cell.split()) for cell in cells]
            if all(column in headers for column in required):
                columns = [headers.index(column) for column in required]
                continue
            if not columns or len(cells) <= max(columns):
                continue
            name, raw, day, clock = (cells[index] for index in columns)
            code = names.get(name)
            if not code:
                continue
            try:
                value = Decimal(raw.replace(",", "")) / 100
                # Some bank responses repeat the clock in the date cell.
                date_match = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", day)
                time_match = re.search(r"\d{1,2}:\d{2}:\d{2}", clock or day)
                if not date_match or not time_match:
                    continue
                stamp = datetime.strptime(date_match[0].replace("/", "-") + " " + time_match[0],
                                          "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
                if not value.is_finite() or value <= 0 or stamp > collected_at + timedelta(minutes=2):
                    continue
            except (ValueError, InvalidOperation):
                continue
            if code not in quotes or stamp.isoformat() > quotes[code]["t"]:
                quotes[code] = {"t": stamp.isoformat(), "v": float(value),
                                "collected_at": collected_at.isoformat()}
    return quotes


def fetch():
    urls = (URL, URL + "index.html", URL)
    for attempt, url in enumerate(urls):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0",
                                            "Cache-Control": "no-cache"})
            with urlopen(request, timeout=20) as response:
                html = response.read(2_000_000)
                encoding = response.headers.get_content_charset() or "utf-8"
            html = html.decode(encoding)
            now = datetime.now(TZ)
            quotes = parse_quotes(html, CONFIG["currencies"], now)
            if CONFIG["monitor_currency"] not in quotes:
                parser = QuoteTableParser()
                parser.feed(html)
                currency = CONFIG["currencies"][CONFIG["monitor_currency"]]
                candidates = [row for table in parser.tables for row in table
                              if row and row[0].strip() == currency]
                print(f"中行响应：{len(html)} 字符，{len(parser.tables)} 张表，"
                      f"目标币种行 {len(candidates)}，有效币种 {len(quotes)}")
                for candidate in candidates[:2]:
                    print(f"目标币种行的报价格数和时间：{len(candidate)} / "
                          + " ".join(cell.strip()[:20] for cell in candidate[-2:]))
                raise ValueError("缺少监控币种的有效牌价")
            return now, quotes
        except Exception as error:
            print(f"中行采集尝试 {attempt + 1}/3 失败（{type(error).__name__}）")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
    raise SystemExit("无法采集中行报价，保留已保存的数据")


def slot(stamp):
    # Slot boundaries match cron minutes 03, 08, 13, ... in Beijing time.
    return (int(stamp.timestamp()) - 180) // 300


def coverage(observed, now, days):
    end = slot(now)
    # The current slot can still be in progress.
    return sum(number in observed for number in range(end - days * 288, end))


def record(history, quotes, now):
    cutoff = (now - timedelta(days=91)).isoformat()
    series = history.setdefault("series", {})
    slots = history.setdefault("slots", {})
    for code in CONFIG["currencies"]:
        rows = {row["t"]: row for row in series.get(code, []) if row["t"] >= cutoff}
        observed = set(slots.get(code, []))
        if code in quotes:
            quote = quotes[code]
            rows.setdefault(quote["t"], quote)
            observed.add(slot(now))
        series[code] = sorted(rows.values(), key=lambda row: row["t"])
        slots[code] = sorted(value for value in observed if value >= slot(now - timedelta(days=31)))
    history.update(currencies=CONFIG["currencies"], checked_at=now.isoformat(),
                   monitor_currency=CONFIG["monitor_currency"],
                   target_price=CONFIG["target_price"],
                   coverage={code: {days: coverage(set(values), now, days)
                                    for days in (7, 30)}
                             for code, values in slots.items()})


def collect():
    now, quotes = fetch()
    history = load(DATA, {})
    record(history, quotes, now)
    save(DATA, history)
    code = CONFIG["monitor_currency"]
    q = quotes[code]
    print(f"采集成功：{len(quotes)} 个币种；{code} {q['v']:.6f} CNY；银行 {q['t']}；采集 {now.isoformat()}")


def low_windows(rows, quote, now):
    result = []
    for days in (7, 30):
        start = (now - timedelta(days=days)).isoformat()
        past = [row["v"] for row in rows if start <= row["t"] < quote["t"]]
        if past and quote["v"] < min(past):
            result.append(days)
    return result


def coverage_text(history, code, days):
    count = history["coverage"][code][str(days)]
    total = days * 288
    status = "采集时段完整" if count == total else "采集历史不完整"
    return f"近{days}天：{status}（{count}/{total} 个五分钟采集时段）"


def notify(test=False):
    targets = list(destinations())
    if not targets:
        print("未配置微信推送密钥，跳过通知")
        if test:
            raise SystemExit(1)
        return
    history = load(DATA, {})
    now = datetime.now(TZ)
    code = CONFIG["monitor_currency"]
    currency = CONFIG["currencies"][code]
    rows = history.get("series", {}).get(code, [])
    today = now.date().isoformat()
    state = load(STATE, {})
    receivers = state.setdefault("receivers", {})
    if not rows:
        print("无已保存的报价")
        raise SystemExit(1)
    quote = rows[-1]
    value = Decimal(str(quote["v"]))
    target = Decimal(str(CONFIG["target_price"]))
    quote_age = now - datetime.fromisoformat(quote["t"])
    checked_age = now - datetime.fromisoformat(history["checked_at"])
    fresh = (-timedelta(minutes=2) <= quote_age <= timedelta(hours=2)
             and timedelta(0) <= checked_age <= timedelta(minutes=20))
    below = fresh and value <= target
    windows = low_windows(rows, quote, now) if fresh else []
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    prior_day = [row["v"] for row in rows if row["t"].startswith(yesterday)]
    prior_summary = (f"{max(prior_day):.6f} / {min(prior_day):.6f}"
                     if prior_day else "暂无数据")
    digits = 6 if value < Decimal("0.1") else 4
    rate_text = f"{value:.{digits}f}"
    failed = False
    for destination in targets:
        label = destination[0]
        status = receivers.setdefault(label, {})
        if status.get("day") != today:
            status.update(day=today, attempts=0)
        threshold_key = f"{code}:{target.normalize()}"
        if fresh and not below:
            status.pop("below", None)
        daily = now.hour >= CONFIG["daily_hour_beijing"] and status.get("daily") != today
        last = status.get("last_attempt")
        cooled = not last or now - datetime.fromisoformat(last) >= timedelta(
            minutes=CONFIG["cooldown_minutes"])
        parts = []
        reached = below and status.get("below") != threshold_key
        lows = [days for days in windows if status.get(f"{code}-{days}") != today]
        if cooled or daily:
            if reached:
                parts.append(f"达到目标价（目标 ¥{target:f}）")
            parts.extend(f"创近{days}天已采集报价新低" for days in lows)
        if daily:
            parts.append(f"日报｜昨日采集最高 / 最低：{prior_summary}")
        if test:
            parts = ["手动发送测试，看到这条消息即表示微信收件成功。"]
        limit = min(CONFIG["daily_limit_per_destination"], 5) if label.startswith(
            "serverchan-") else CONFIG["daily_limit_per_destination"]
        # Leave one attempt available for the daily report.
        available = limit - ((test or not daily) and status.get("daily") != today)
        if not parts or status["attempts"] >= available or (
                not cooled and not test and not (daily and status.get("last_daily_attempt") != today)):
            if test:
                print(f"{label}：已达到今日推送预算")
                failed = True
            continue
        title = f"{currency} ¥{rate_text}｜" + ("微信测试" if test else
                 "购汇日报" if daily else "达到目标价" if reached else "近期新低")
        body = "\n\n".join([
            *parts, f"{code} 现汇卖出价：¥{rate_text} / 1 {code}",
            f"银行报价：{quote['t']}" + ("" if fresh else "（报价或采集已延迟）"),
            f"该报价首次采集：{quote.get('collected_at', '未记录')}",
            *(coverage_text(history, code, days) for days in (7, 30)),
            "实际成交以银行为准。", URL,
        ])
        status.update(attempts=status["attempts"] + 1, last_attempt=now.isoformat())
        if daily and not test:
            status["last_daily_attempt"] = today
        save(STATE, state)
        if send(destination, title, body):
            print(f"{label}：推送接口已接受")
            if not test:
                if daily:
                    status["daily"] = today
                if reached:
                    status["below"] = threshold_key
                for days in lows:
                    status[f"{code}-{days}"] = today
        else:
            print(f"{label}：推送失败，请在服务商后台检查配置、额度和接收频道")
            failed = True
        save(STATE, state)
    save(STATE, state)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["collect", "notify", "test-push"],
                        nargs="?", default="collect")
    operation = parser.parse_args().operation
    if operation == "collect":
        collect()
    else:
        notify(test=operation == "test-push")
