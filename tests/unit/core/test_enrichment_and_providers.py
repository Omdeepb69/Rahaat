from __future__ import annotations

import json

import httpx
import pytest

from raahat.application.ai import enrichment
from raahat.infrastructure.providers.base import ProviderError, ProviderNotConfigured
from raahat.infrastructure.providers.geo import NominatimClient, OsrmClient
from raahat.infrastructure.providers.gnani_prisma import GnaniPrismaClient
from raahat.infrastructure.providers.llm import GeminiClient, JsonCompletion, OpenAICompatibleClient


class FakeModel:
    name = "fake"
    model = "fake-1"
    configured = True

    def __init__(self, data):
        self.data = data

    def complete_json(self, *, system, user, max_tokens=1024):
        return JsonCompletion(self.data, "fake", "fake-1", 12.0)


def test_model_findings_without_supporting_quotes_are_rejected():
    model = FakeModel({
        "people_count": 6, "trapped": True, "water_depth_cm": 150, "needs": ["rescue_boat"],
        "location_phrases": ["near the old bridge", "Ernakulam district"],
        "summary": "Six people trapped near a bridge.",
        "quotes": {"people_count": "6 people", "trapped": "we cannot get out",
                   "water_depth_cm": "five feet", "needs": "send a boat"},
    })
    text = "We are 6 people near the old bridge, send a boat"
    result = enrichment.extract_with_model(model, text=text)
    accepted = {(f.attribute, f.value) for f in result.findings}
    assert ("people_count", 6) in accepted
    assert ("relief_need", "rescue_boat") in accepted
    assert ("trapped_status", True) not in accepted
    assert all(not a.startswith("water_depth") for a, _ in accepted)
    assert result.location_phrases == ["near the old bridge"]
    assert len(result.rejected) == 3


def test_out_of_schema_values_are_dropped():
    model = FakeModel({"category": "alien_invasion", "people_count": "many", "hazards": ["sharks"],
                       "quotes": {"hazards": "sharks"}})
    result = enrichment.extract_with_model(model, text="sharks")
    assert result.category is None and result.findings == []


def test_translation_requires_text():
    with pytest.raises(ProviderError):
        enrichment.translate_to_english(FakeModel({"translation": ""}), text="x", source_language="ml")


def _transport(handler):
    return httpx.MockTransport(handler)


def test_unconfigured_providers_raise_instead_of_returning_data():
    with pytest.raises(ProviderNotConfigured):
        GnaniPrismaClient(api_key=None, endpoint="https://example.test").transcribe(b"x")
    with pytest.raises(ProviderNotConfigured):
        OpenAICompatibleClient(api_base=None, api_key=None, model="m").complete_json(system="", user="")
    with pytest.raises(ProviderNotConfigured):
        GeminiClient(api_key=None, model="m").complete_json(system="", user="")
    with pytest.raises(ProviderNotConfigured):
        NominatimClient(enabled=False, base_url="https://x", user_agent="t").search("Kochi")
    with pytest.raises(ProviderNotConfigured):
        OsrmClient(base_url=None).route(origin=(10, 76), destination=(10.1, 76.1))


def test_prisma_parses_response_without_inventing_confidence():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key-ID"] == "key"
        return httpx.Response(200, json={"transcript": " വെള്ളം കയറി ", "detected_language_code": "ml-IN"})

    client = GnaniPrismaClient(api_key="key", endpoint="https://stt.test", transport=_transport(handler))
    result = client.transcribe(b"\x00\x01" * 100, language_hint="ml")
    assert result.text == "വെള്ളം കയറി"
    assert result.language == "ml-IN"
    assert result.confidence is None


def test_provider_http_errors_become_provider_errors():
    client = GnaniPrismaClient(
        api_key="key", endpoint="https://stt.test",
        transport=_transport(lambda r: httpx.Response(503, text="overloaded")),
    )
    with pytest.raises(ProviderError) as info:
        client.transcribe(b"\x00" * 10)
    assert info.value.retryable


def test_gemini_key_is_sent_in_header_not_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
        return httpx.Response(200, json=body)

    client = GeminiClient(api_key="secret-key", model="gemini-test", transport=_transport(handler))
    assert client.complete_json(system="s", user="u").data == {"ok": True}
    assert "secret-key" not in seen["url"] and seen["key"] == "secret-key"


def test_nominatim_candidates_and_osrm_route():
    def geocode(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"]
        return httpx.Response(200, json=[{"lat": "10.0", "lon": "76.3", "display_name": "Kakkanad",
                                          "importance": 0.4, "osm_type": "node", "osm_id": 1,
                                          "boundingbox": ["9.99", "10.01", "76.29", "76.31"]}])

    nominatim = NominatimClient(enabled=True, base_url="https://n.test", user_agent="t", transport=_transport(geocode))
    candidate = nominatim.search("Kakkanad").candidates[0]
    assert candidate.osm_ref == "node/1" and candidate.bounding_radius_m > 0

    def route(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1500.0, "duration": 240.0,
                              "geometry": {"coordinates": [[76.3, 10.0], [76.31, 10.01]]}}]})

    osrm = OsrmClient(base_url="https://o.test", transport=_transport(route))
    estimate = osrm.route(origin=(10.0, 76.3), destination=(10.01, 76.31))
    assert estimate.distance_m == 1500.0 and estimate.geometry[0] == (10.0, 76.3)
