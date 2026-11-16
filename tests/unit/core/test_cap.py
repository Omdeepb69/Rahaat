"""CAP feed parsing and import. XML below is a test fixture modelled on the CAP 1.2 schema."""
from __future__ import annotations

import httpx

from raahat.application.alerts.service import provider_for
from raahat.infrastructure.providers.cap import CapFeedClient, parse_cap, parse_feed

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>Test feed</title>
<item><title>Heavy rain warning (test fixture)</title><link>https://feed.test/cap/1</link>
<author>control@test (Test authority)</author><guid>1</guid><pubDate>Mon, 09 Nov 2026 16:48:53 GMT</pubDate></item>
<item><title>Second (test fixture)</title><link>https://feed.test/cap/2</link><guid>2</guid></item>
</channel></rss>"""

CAP = """<cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
<cap:identifier>TEST-1</cap:identifier><cap:sender>Test-SDMA</cap:sender><cap:sent>2026-11-10T16:15:40+05:30</cap:sent>
<cap:status>Actual</cap:status><cap:msgType>Alert</cap:msgType>
<cap:info><cap:language>ML</cap:language><cap:event>Heavy Rain</cap:event><cap:headline>കനത്ത മഴ</cap:headline></cap:info>
<cap:info><cap:language>en-IN</cap:language><cap:category>Met</cap:category><cap:event>Heavy Rain</cap:event>
<cap:urgency>Expected</cap:urgency><cap:severity>Severe</cap:severity><cap:certainty>Likely</cap:certainty>
<cap:expires>2026-11-10T19:04:00+05:30</cap:expires><cap:headline>Heavy rain likely (test fixture)</cap:headline>
<cap:area><cap:areaDesc>Test district</cap:areaDesc><cap:geocode><cap:valueName>LGD District Code</cap:valueName><cap:value>565</cap:value></cap:geocode></cap:area>
</cap:info></cap:alert>"""


def test_feed_and_message_parsing():
    items = parse_feed(FEED)
    assert [i.guid for i in items] == ["1", "2"]
    alert = parse_cap(CAP)
    assert alert.headline == "Heavy rain likely (test fixture)"  # English info preferred
    assert alert.headlines_by_language["ml"] == "കനത്ത മഴ"
    assert alert.severity == "Severe" and alert.sender == "Test-SDMA"
    assert alert.expires is not None and alert.expires.utcoffset() is not None
    assert alert.geocodes == [{"name": "LGD District Code", "value": "565"}]
    assert alert.instruction is None  # absent fields stay absent


def test_client_skips_known_items_and_reports_bad_messages():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/feed":
            return httpx.Response(200, text=FEED)
        if request.url.path.endswith("/1"):
            return httpx.Response(200, text=CAP)
        return httpx.Response(200, text="<not-cap/>")

    client = CapFeedClient(feed_url="https://feed.test/feed", user_agent="test", transport=httpx.MockTransport(handler))
    results, errors, _ = client.fetch(skip=set(), limit=10)
    assert [a.identifier for _, a in results] == ["TEST-1"]
    assert len(errors) == 1
    results, errors, _ = client.fetch(skip={"1", "2"}, limit=10)
    assert results == [] and errors == []


def test_only_ndma_sachet_is_labelled_official():
    assert provider_for("https://sachet.ndma.gov.in/cap_public_website/rss/rss_kerala.xml") == ("ndma_sachet", "official")
    assert provider_for("https://example.org/feed.xml") == ("cap_feed", "unverified")
