"""Unit tests for multi-channel ingestion payload adapters."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from raahat.adapters.channels.radio_console import RadioConsoleAdapter, RadioConsolePayload
from raahat.adapters.channels.sms import SMSAdapter, SMSPayload
from raahat.adapters.channels.web import WebSOSAdapter, WebSOSPayload
from raahat.domain.shared.enums import SourceType


class TestWebSOSAdapter:
    def test_valid_payload_conversion(self) -> None:
        disaster_id = uuid.uuid4()
        payload = WebSOSPayload(
            disaster_id=disaster_id,
            caller_name="Ramesh Kumar",
            phone_number="+919876543210",
            location_text="Near Old Post Office, Ward 4",
            latitude=15.4989,
            longitude=73.8278,
            people_count=4,
            situation_description="Water level up to ceiling, family on roof",
            needs=["boat", "medical"],
            language_code="hi",
            submission_token="tok-12345",
        )

        sub = WebSOSAdapter.to_submission(payload)

        assert sub.disaster_id == disaster_id
        assert sub.source_type == SourceType.WEB
        assert sub.source_identity == "+919876543210"
        assert sub.source_event_id == "tok-12345"
        assert sub.channel_reference == "web_sos"
        assert sub.idempotency_key == "web-tok-12345"
        assert sub.raw_payload["people_count"] == 4
        assert sub.raw_payload["needs"] == ["boat", "medical"]

    def test_dict_conversion(self) -> None:
        disaster_id = uuid.uuid4()
        data = {
            "disaster_id": disaster_id,
            "situation_description": "Flood water entering home",
        }
        sub = WebSOSAdapter.to_submission(data)
        assert sub.source_type == SourceType.WEB
        assert sub.raw_payload["situation_description"] == "Flood water entering home"
        assert sub.idempotency_key is None

    def test_invalid_payload_raises(self) -> None:
        with pytest.raises(ValidationError):
            WebSOSPayload(
                disaster_id=uuid.uuid4(),
                situation_description="",  # Empty string rejected
            )


class TestSMSAdapter:
    def test_valid_payload_conversion(self) -> None:
        disaster_id = uuid.uuid4()
        payload = SMSPayload(
            disaster_id=disaster_id,
            sender="+919876500000",
            message="Need urgent rescue 5 people at bus stand",
            message_id="SM1234567890",
            shortcode="56161",
        )

        sub = SMSAdapter.to_submission(payload)

        assert sub.disaster_id == disaster_id
        assert sub.source_type == SourceType.SMS
        assert sub.source_identity == "+919876500000"
        assert sub.source_event_id == "SM1234567890"
        assert sub.channel_reference == "56161"
        assert sub.idempotency_key == "sms-SM1234567890"
        assert sub.raw_payload["message"] == "Need urgent rescue 5 people at bus stand"

    def test_invalid_sender_raises(self) -> None:
        with pytest.raises(ValidationError):
            SMSPayload(
                disaster_id=uuid.uuid4(),
                sender="1",  # Too short
                message="SOS",
            )


class TestRadioConsoleAdapter:
    def test_valid_payload_conversion(self) -> None:
        disaster_id = uuid.uuid4()
        payload = RadioConsolePayload(
            disaster_id=disaster_id,
            operator_callsign="VU2NIX",
            frequency_channel="VHF-CH16",
            transmission_text="Station Beta reports 10 stranded at bridge",
            reporting_party="STATION-BETA",
            estimated_location="North Bridge Causeway",
            people_count=10,
            operator_entry_id="ENTRY-9988",
        )

        sub = RadioConsoleAdapter.to_submission(payload)

        assert sub.disaster_id == disaster_id
        assert sub.source_type == SourceType.RADIO
        assert sub.source_identity == "VU2NIX"
        assert sub.source_event_id == "ENTRY-9988"
        assert sub.channel_reference == "VHF-CH16"
        assert sub.idempotency_key == "radio-ENTRY-9988"
        assert sub.raw_payload["people_count"] == 10
        assert sub.raw_payload["operator_callsign"] == "VU2NIX"
