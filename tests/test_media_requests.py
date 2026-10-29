"""Bridge responses and temporary uploads never touch a live WhatsApp account."""

from unittest.mock import Mock

import pytest
import requests

from whatsapp_mcp import whatsapp


@pytest.mark.parametrize("payload", [[], None, {"success": "false"}, {"success": True, "message": 123}])
def test_malformed_send_response_is_a_failure(monkeypatch, payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    monkeypatch.setattr(whatsapp._session, "post", Mock(return_value=response))
    success, message = whatsapp.send_message("fixture", "hello")
    assert success is False
    assert isinstance(message, str)


def test_timeout_warns_against_blind_resend(monkeypatch):
    monkeypatch.setattr(whatsapp._session, "post", Mock(side_effect=requests.Timeout()))
    success, message = whatsapp.send_message("fixture", "hello")
    assert success is False
    assert "unknown" in message.lower()


def test_relative_file_is_resolved_before_bridge_handoff(monkeypatch, tmp_path):
    media = tmp_path / "fixture.jpg"
    media.write_bytes(b"fixture")
    monkeypatch.chdir(tmp_path)
    sent = Mock(return_value=(True, "sent"))
    monkeypatch.setattr(whatsapp, "_post_to_bridge", sent)
    whatsapp.send_file("fixture", "fixture.jpg")
    assert sent.call_args.args[0]["media_path"] == str(media)


@pytest.mark.parametrize("sent", [True, False])
def test_converted_audio_is_cleaned_after_upload(monkeypatch, tmp_path, sent):
    original, converted = tmp_path / "voice.wav", tmp_path / "converted.ogg"
    original.write_bytes(b"original")
    converted.write_bytes(b"converted")
    monkeypatch.setattr(whatsapp.audio, "convert_to_opus_ogg_temp", lambda _: str(converted))

    def upload(payload):
        assert converted.exists()
        assert payload["media_path"] == str(converted)
        return sent, "fixture"

    monkeypatch.setattr(whatsapp, "_post_to_bridge", upload)
    assert whatsapp.send_audio_message("fixture", str(original))[0] is sent
    assert original.exists()
    assert not converted.exists()


def test_existing_ogg_is_not_deleted(monkeypatch, tmp_path):
    original = tmp_path / "voice.ogg"
    original.write_bytes(b"fixture")
    monkeypatch.setattr(whatsapp, "_post_to_bridge", lambda _: (True, "sent"))
    whatsapp.send_audio_message("fixture", str(original))
    assert original.exists()


def test_download_has_a_timeout(monkeypatch):
    posted = Mock(return_value=Mock(status_code=200))
    posted.return_value.json.return_value = {"success": True, "path": "/fixture/image.jpg"}
    monkeypatch.setattr(whatsapp._session, "post", posted)
    assert whatsapp.download_media("fixture", "fixture") == "/fixture/image.jpg"
    assert posted.call_args.kwargs["timeout"] == whatsapp.HTTP_TIMEOUT_SECONDS
