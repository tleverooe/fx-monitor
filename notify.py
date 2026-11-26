"""Push adapters. Provider responses and request URLs never go to stdout."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def destinations():
    provider = os.getenv("PUSH_PROVIDER", "pushplus") or "pushplus"
    if provider == "pushplus":
        token = os.getenv("PUSHPLUS_TOKEN")
        topic = os.getenv("PUSHPLUS_TOPIC")
        if token:
            fields = {"token": token, "channel": "wechat", "template": "txt"}
            if topic:
                fields["topic"] = topic
            yield "pushplus", "https://www.pushplus.plus/send", fields
    elif provider == "wxpusher":
        token = os.getenv("WXPUSHER_APP_TOKEN")
        topic = os.getenv("WXPUSHER_TOPIC_ID")
        if token:
            if not topic or not topic.isascii() or not topic.isdecimal():
                raise ValueError("请设置有效的 WXPUSHER_TOPIC_ID")
            yield "wxpusher", "https://wxpusher.zjiecode.com/api/send/message", {
                "appToken": token, "topicIds": [int(topic)], "contentType": 1,
            }
    elif provider == "serverchan":
        keys = os.getenv("SERVERCHAN_SENDKEYS") or os.getenv("SERVERCHAN_SENDKEY", "")
        for index, key in enumerate(dict.fromkeys(keys.replace(",", " ").split())):
            yield f"serverchan-{index}", f"https://sctapi.ftqq.com/{key}.send", {}
    else:
        raise ValueError("PUSH_PROVIDER 必须是 pushplus、serverchan 或 wxpusher")


def send(destination, title, body):
    label, url, fields = destination
    try:
        if label.startswith("serverchan-"):
            payload = urlencode({"title": title, "desp": body}).encode()
            content_type = "application/x-www-form-urlencoded"
            expected = 0
        else:
            payload = json.dumps({**fields, "title": title, "summary": title,
                                  "content": body}).encode()
            content_type = "application/json"
            expected = 200 if label == "pushplus" else 1000
        request = Request(url, data=payload, headers={"Content-Type": content_type})
        with urlopen(request, timeout=15) as response:
            return json.load(response).get("code") == expected
    except Exception:
        # Exception text can contain a SendKey in a URL or credentials in a response.
        return False
