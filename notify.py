"""Push adapters. Provider responses and request URLs never go to stdout."""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def destinations():
    provider = os.getenv("PUSH_PROVIDER", "pushplus") or "pushplus"
    if provider == "email":
        sender = os.getenv("GMAIL_SENDER", "").strip()
        password = "".join(os.getenv("GMAIL_APP_PASSWORD", "").split())
        recipients = os.getenv("FX_EMAIL_TO", "").replace(",", " ").split()
        if not any((sender, password, recipients)):
            return
        if not all((sender, password, recipients)):
            raise ValueError("请设置 GMAIL_SENDER、GMAIL_APP_PASSWORD 和 FX_EMAIL_TO")
        for index, recipient in enumerate(dict.fromkeys(recipients)):
            yield f"email-{index}", "smtp.gmail.com", {
                "sender": sender, "password": password, "recipient": recipient,
            }
    elif provider == "pushplus":
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
        raise ValueError("PUSH_PROVIDER 必须是 pushplus、serverchan、wxpusher 或 email")


def send(destination, title, body):
    label, url, fields = destination
    try:
        if label.startswith("email-"):
            message = EmailMessage()
            message["Subject"] = title
            message["From"] = fields["sender"]
            message["To"] = fields["recipient"]
            message.set_content(body)
            with smtplib.SMTP_SSL(url, 465, timeout=15, context=ssl.create_default_context()) as client:
                client.login(fields["sender"], fields["password"])
                return not client.send_message(message)
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
