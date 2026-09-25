from magicdub_cli.adapters.registry import known_adapter_ids


def test_registry_has_v010_adapters() -> None:
    ids = known_adapter_ids()
    assert "fal/demucs" in ids
    assert "mvsep/dnr-v3" in ids
    assert "fal/whisper" in ids
    assert "deepseek/deepseek-flash" in ids
    assert "fal/index-tts-2" in ids
