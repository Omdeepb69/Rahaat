"""Common Alerting Protocol (CAP 1.2) feed adapter.

Built for the NDMA SACHET integrated alert system, which publishes an RSS
index per country and per state (e.g. .../rss/rss_kerala.xml); each item links
to a CAP message issued by an authority such as IMD or a State Disaster
Management Authority. Any RSS-of-CAP feed with the same shape works.

Only values present in the message are recorded. A missing field stays
missing.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx

from .base import ProviderError, ProviderNotConfigured, Stopwatch, translate_http_errors

CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}
PROVIDER = "cap_feed"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class FeedItem:
    guid: str
    title: str
    link: str
    author: Optional[str]
    published_at: Optional[datetime]


@dataclass(frozen=True)
class CapAlert:
    identifier: str
    sender: Optional[str]
    sent: Optional[datetime]
    status: Optional[str]
    msg_type: Optional[str]
    event: Optional[str]
    category: Optional[str]
    urgency: Optional[str]
    severity: Optional[str]
    certainty: Optional[str]
    effective: Optional[datetime]
    expires: Optional[datetime]
    headline: Optional[str]
    instruction: Optional[str]
    area_description: Optional[str]
    headlines_by_language: dict[str, str] = field(default_factory=dict)
    geocodes: list[dict[str, str]] = field(default_factory=list)
    references: Optional[str] = None


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        try:
            return parsedate_to_datetime(value.strip())
        except (TypeError, ValueError):
            return None


def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
    if node is None:
        return None
    found = node.find(path, CAP_NS)
    value = (found.text or "").strip() if found is not None else ""
    return value or None


def parse_feed(xml_text: str) -> list[FeedItem]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderError(PROVIDER, f"feed is not valid XML: {exc}") from exc
    items: list[FeedItem] = []
    for item in root.iter("item"):
        guid = (item.findtext("guid") or item.findtext("link") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not guid or not link:
            continue
        items.append(
            FeedItem(
                guid=guid,
                title=(item.findtext("title") or "").strip(),
                link=link,
                author=(item.findtext("author") or "").strip() or None,
                published_at=_parse_time(item.findtext("pubDate")),
            )
        )
    return items


def parse_cap(xml_text: str) -> CapAlert:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ProviderError(PROVIDER, f"CAP message is not valid XML: {exc}") from exc
    if not root.tag.endswith("alert"):
        raise ProviderError(PROVIDER, "document is not a CAP alert")
    infos = root.findall("cap:info", CAP_NS)
    english = next(
        (i for i in infos if (_text(i, "cap:language") or "").lower().startswith("en")),
        infos[0] if infos else None,
    )
    headlines: dict[str, str] = {}
    for info in infos:
        language = (_text(info, "cap:language") or "und").lower()
        headline = _text(info, "cap:headline")
        if headline:
            headlines[language] = headline
    area = english.find("cap:area", CAP_NS) if english is not None else None
    geocodes = [
        {"name": _text(g, "cap:valueName") or "", "value": _text(g, "cap:value") or ""}
        for g in (area.findall("cap:geocode", CAP_NS) if area is not None else [])
    ]
    identifier = _text(root, "cap:identifier")
    if not identifier:
        raise ProviderError(PROVIDER, "CAP message has no identifier")
    return CapAlert(
        identifier=identifier,
        sender=_text(root, "cap:sender"),
        sent=_parse_time(_text(root, "cap:sent")),
        status=_text(root, "cap:status"),
        msg_type=_text(root, "cap:msgType"),
        event=_text(english, "cap:event"),
        category=_text(english, "cap:category"),
        urgency=_text(english, "cap:urgency"),
        severity=_text(english, "cap:severity"),
        certainty=_text(english, "cap:certainty"),
        effective=_parse_time(_text(english, "cap:effective")),
        expires=_parse_time(_text(english, "cap:expires")),
        headline=_text(english, "cap:headline"),
        instruction=_text(english, "cap:instruction"),
        area_description=_text(area, "cap:areaDesc") if area is not None else None,
        headlines_by_language=headlines,
        geocodes=geocodes,
        references=_text(root, "cap:references"),
    )


class CapFeedClient:
    name = PROVIDER

    def __init__(
        self,
        *,
        feed_url: Optional[str],
        user_agent: str,
        timeout_seconds: float = 20.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._feed_url = feed_url
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._feed_url)

    @property
    def feed_url(self) -> Optional[str]:
        return self._feed_url

    def _get(self, client: httpx.Client, url: str) -> str:
        with translate_http_errors(PROVIDER):
            response = client.get(url)
            response.raise_for_status()
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ProviderError(PROVIDER, "response larger than allowed")
        return response.text

    def fetch(self, *, skip: set[str], limit: int) -> tuple[list[tuple[FeedItem, CapAlert]], list[str], float]:
        """Read the feed and fetch up to ``limit`` CAP messages whose guid is not in ``skip``.

        Returns (alerts, per-item errors, duration ms). A failure to read the
        feed itself raises; a failure on one message is reported and skipped.
        """
        if not self._feed_url:
            raise ProviderNotConfigured(PROVIDER, "CAP_ALERT_FEED_URL")
        watch = Stopwatch()
        results: list[tuple[FeedItem, CapAlert]] = []
        errors: list[str] = []
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers={"User-Agent": self._user_agent},
            follow_redirects=True,
        ) as client:
            items = parse_feed(self._get(client, self._feed_url))
            for item in [i for i in items if i.guid not in skip][:limit]:
                try:
                    results.append((item, parse_cap(self._get(client, item.link))))
                except ProviderError as exc:
                    errors.append(f"{item.guid}: {exc}")
        return results, errors, watch.elapsed_ms


def alert_payload(item: FeedItem, alert: CapAlert) -> dict[str, Any]:
    return {
        "sender": alert.sender,
        "feed_author": item.author,
        "status": alert.status,
        "msg_type": alert.msg_type,
        "event": alert.event,
        "category": alert.category,
        "urgency": alert.urgency,
        "certainty": alert.certainty,
        "effective": alert.effective.isoformat() if alert.effective else None,
        "instruction": alert.instruction,
        "headlines": alert.headlines_by_language,
        "geocodes": alert.geocodes,
        "references": alert.references,
        "cap_identifier": alert.identifier,
    }
