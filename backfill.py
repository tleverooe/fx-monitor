"""Merge official BOC public pages or manually saved history responses."""
import argparse
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from monitor import BACKFILL, CONFIG, TZ, URL, load, iter_quotes, save
SEARCH = "https://www.boc.cn/sourcedb/whpjSearch/index.html"


def request_page(url):
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(request, timeout=15) as response:
                return response.read(2_000_000).decode(
                    response.headers.get_content_charset() or "utf-8")
        except HTTPError as error:
            if error.code in (401, 403, 429):
                raise
            if error.code < 500 or attempt == 2:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(3 * (attempt + 1))


def public_quotes(now):
    html = request_page(URL)
    match = re.search(r'createPageHTML\(\s*(\d+)\s*,\s*0\s*,\s*"index"\s*,\s*"html"', html)
    if not match:
        raise ValueError("公开牌价列表的分页格式已变化")
    yield from page_quotes(html, now, URL)
    for page in range(1, int(match[1])):
        time.sleep(1.5)
        url = f"{URL}index_{page}.html"
        yield from page_quotes(request_page(url), now, url)


def page_quotes(html, now, url):
    quotes = list(iter_quotes(html, CONFIG["currencies"], now))
    if not quotes:
        raise ValueError(f"公开牌价页没有可解析的报价：{url}")
    for code, quote in quotes:
        yield code, dict(quote, source_url=url)


def imported_quotes(path, now):
    body = load(path, {}).get("respBody", {})
    if body.get("respStatus") != "00" or not isinstance(body.get("data"), list):
        raise ValueError(f"{path.name} 不是成功的中行历史牌价响应")
    if len(body["data"]) >= 1000:
        print(f"{path.name} 达到页面请求上限，须核实是否截断")
    names = {name: code for code, name in CONFIG["currencies"].items()}
    for row in body["data"]:
        code = names.get(str(row.get("cname_hbmc", "")).strip())
        if not code or row.get("mcj2") in (None, "", " "):
            continue
        try:
            value = Decimal(str(row["mcj2"]).replace(",", "")) / 100
            stamp = datetime.fromisoformat(row["pjtime"].strip().replace("/", "-"))
            stamp = stamp.replace(tzinfo=TZ) if stamp.tzinfo is None else stamp.astimezone(TZ)
            if not value.is_finite() or value <= 0 or stamp > now + timedelta(minutes=2):
                raise ValueError("报价或时间越界")
        except (KeyError, ValueError, InvalidOperation) as error:
            raise ValueError(f"{path.name} 含无法解析的现汇卖出价记录") from error
        yield code, {"t": stamp.isoformat(), "v": float(value),
                     "collected_at": now.isoformat(), "source_url": SEARCH}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, choices=range(1, 92),
                        metavar="1–91")
    parser.add_argument("--import-response", type=Path, nargs="+", default=[])
    parser.add_argument("--public", action="store_true", help="同时读取公开分页")
    args = parser.parse_args()
    now = datetime.now(TZ)
    start = (now.date() - timedelta(days=args.days - 1)).isoformat()
    existing = load(BACKFILL, {})
    merged = {code: {row["t"]: row for row in rows} for code, rows in existing.items()}
    sources = [imported_quotes(path, now) for path in args.import_response]
    if args.public or not sources:
        sources.append(public_quotes(now))
    for source in sources:
        for code, quote in source:
            if quote["t"][:10] >= start:
                merged.setdefault(code, {}).setdefault(quote["t"], quote)
    result = {code: sorted(rows.values(), key=lambda row: row["t"])
              for code, rows in merged.items()}
    save(BACKFILL, result)
    for code, rows in result.items():
        if rows:
            print(code, len(rows), rows[0]["t"], rows[-1]["t"])


if __name__ == "__main__":
    main()
