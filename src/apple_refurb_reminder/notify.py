from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .config import Settings
from .models import Listing, Match


class DeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedBatch:
    subject: str
    body: str
    discord_parts: tuple[str, ...]


def render_batch(
    matches: list[Match],
    detected_at: datetime,
    timezone: str,
    *,
    test: bool = False,
) -> RenderedBatch:
    local = detected_at.astimezone(ZoneInfo(timezone))
    prefix = "【TEST】" if test else ""
    subject = f"{prefix}Apple整備済製品 在庫通知"
    if test and not matches:
        body = (
            "TEST\n"
            "本日の確認時点では、条件に一致する実在庫はありません。\n"
            "このメッセージは通知経路のテストです。\n"
            f"確認日時: {local:%Y-%m-%d %H:%M:%S %Z}"
        )
    else:
        lines = [subject, f"検出日時: {local:%Y-%m-%d %H:%M:%S %Z}", ""]
        grouped: dict[str, tuple[Listing, list[str]]] = {}
        for match in matches:
            if match.listing.id not in grouped:
                grouped[match.listing.id] = (match.listing, [])
            grouped[match.listing.id][1].append(match.subscription_id)
        for listing, subscription_ids in grouped.values():
            lines.extend(
                (
                    f"• {listing.title}",
                    f"  仕様: {listing.cpu_cores}コアCPU / {listing.gpu_cores}コアGPU"
                    f" · {listing.memory_gb}GB · {listing.storage}",
                    f"  価格: ¥{listing.price_jpy:,}",
                    f"  購読: {', '.join(sorted(subscription_ids))}",
                    f"  商品リンク: {listing.url}",
                    "",
                )
            )
        body = "\n".join(lines).rstrip()
    parts = split_discord(body)
    if len(parts) > 1:
        parts = tuple(
            f"{subject} {index}/{len(parts)}\n{part}"
            for index, part in enumerate(parts, 1)
        )
    return RenderedBatch(subject, body, parts)


def split_discord(text: str, limit: int = 1900) -> tuple[str, ...]:
    if len(text) <= limit:
        return (text,)
    parts: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}".strip()
        if current and len(candidate) > limit:
            parts.append(current)
            current = block
        else:
            current = candidate
    if current:
        parts.append(current)
    return tuple(parts)


def render_health_event(
    category: str,
    *,
    recovered: bool,
    region: str,
) -> RenderedBatch:
    language = {
        "JP": "ja",
        "US": "en",
        "CN": "zh-CN",
        "HK": "zh-HK",
    }.get(region, "en")
    messages = {
        ("en", False): (
            "Apple Refurb Reminder monitoring issue",
            f"• {category}: checks failed 3 consecutive times. "
            "Absence counters are paused for this category.",
        ),
        ("en", True): (
            "Apple Refurb Reminder monitoring recovered",
            f"• {category}: checks are working again.",
        ),
        ("ja", False): (
            "Apple整備済製品モニター 障害通知",
            f"• {category}: 3回連続で確認に失敗しました。このカテゴリの不在判定を停止しています。",
        ),
        ("ja", True): (
            "Apple整備済製品モニター 復旧通知",
            f"• {category}: 確認が正常に戻りました。",
        ),
        ("zh-CN", False): (
            "Apple 翻新产品监控异常",
            f"• {category}：已连续检查失败 3 次，该类别的缺席计数已暂停。",
        ),
        ("zh-CN", True): (
            "Apple 翻新产品监控已恢复",
            f"• {category}：检查已恢复正常。",
        ),
        ("zh-HK", False): (
            "Apple 翻新產品監控異常",
            f"• {category}：已連續檢查失敗 3 次，該類別的缺席計數已暫停。",
        ),
        ("zh-HK", True): (
            "Apple 翻新產品監控已恢復",
            f"• {category}：檢查已恢復正常。",
        ),
    }
    subject, body = messages[(language, recovered)]
    return RenderedBatch(subject, body, (f"{subject}\n{body}",))


class DiscordChannel:
    def __init__(self, webhook: str) -> None:
        self.webhook = webhook

    def send(self, batch: RenderedBatch) -> None:
        for part in batch.discord_parts:
            request = Request(
                self.webhook,
                data=json.dumps({"content": part}, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AppleRefurbReminder/0.1 (personal inventory monitor)",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=20) as response:
                    if response.status not in {200, 204}:
                        raise DeliveryError(f"Discord status={response.status}")
            except Exception as exc:
                raise DeliveryError(f"Discord 送信失敗: {exc}") from exc


class EmailChannel:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, batch: RenderedBatch) -> None:
        message = EmailMessage()
        message["Subject"] = batch.subject
        message["From"] = self.settings.email_from
        message["To"] = self.settings.email_to
        message.set_content(batch.body)
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
        except Exception as exc:
            raise DeliveryError(f"Email 送信失敗: {exc}") from exc
