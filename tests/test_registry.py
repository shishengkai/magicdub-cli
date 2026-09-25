from magicdub_cli.adapters.registry import known_adapter_ids


def test_registry_has_v010_adapters() -> None:
    ids = known_adapter_ids()
    assert "fal/demucs" in ids
    assert "fal/sam-audio" in ids
    assert "mvsep/dnr-v3" in ids
    assert "fal/whisper" in ids
    assert "bailian/fun-asr" in ids
    assert "bailian/qwen-audio-3.1-asr-flash-filetrans" in ids
    assert "fishaudio/s2.1-pro-free" in ids
    assert "fishaudio/s2.1-pro" in ids
    assert "openrouter/fish-audio/s2.1-pro-free" in ids
    assert "openrouter/fish-audio/s2.1-pro" in ids
    assert "deepseek/deepseek-flash" in ids
    assert "fal/index-tts-2" in ids
