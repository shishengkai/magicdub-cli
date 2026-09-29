"""Context, paid failures and fitting rounds, without external calls or user media."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from magicdub_cli.adapters.translation import deepseek_deepseek_flash as deepseek
from magicdub_cli.errors import AdapterError
from magicdub_cli.media.files import file_ref
from magicdub_cli.pipeline import runner
from magicdub_cli.state.io import load_state, new_state
from magicdub_cli.steps.fixed import alignment, duration_fitting, mixing
from magicdub_cli.steps.slots import translation, tts
from magicdub_cli.steps.slots.translation_context import build_context


@pytest.fixture
def state(tmp_path, monkeypatch):
    result = new_state(
        task_id="test",
        title="context",
        src_language="en",
        tgt_language="zh-Hans",
        fitting={"lower_ratio": 0.8, "upper_ratio": 1.2, "max_rewrites": 2},
        slots={
            "translation": {"order": ["deepseek/deepseek-flash"]},
            "tts": {"order": ["fal/index-tts-2"]},
        },
    )
    result["assets"]["src"]["transcript"] = "Full source with a distant reference."
    for sid in range(1, 5):
        path = tmp_path / f"reference_{sid}.wav"
        path.write_bytes(f"reference {sid}".encode())
        result["assets"]["sentences"].append(
            {
                "id": sid,
                "speaker_id": "A" if sid < 3 else "B",
                "start_ms": (sid - 1) * 1000,
                "end_ms": sid * 1000,
                "src": {
                    "text": f"source {sid}",
                    "audio_duration": 1000,
                    "audio": file_ref(path, relative_to=tmp_path),
                },
                "tgt": [],
                "selected_attempt": None,
            }
        )
    for slot in (translation, tts):
        monkeypatch.setattr(
            slot,
            "load_credentials",
            lambda: {
                "DEEPSEEK_API_KEY": "test-key",
                "FAL_KEY": "test-key",
            },
        )
    return result


def draft(text, attempt=1, ratio=1.6):
    return {
        "attempt": attempt,
        "text": text,
        "audio_duration": 1000 * ratio,
        "fitting_ratio": ratio,
        "selection": "rejected",
    }


def messages_for(state, attempt, ids=None):
    document, sentences = build_context(
        state["assets"]["sentences"],
        sentence_ids=ids,
        attempt=attempt,
        fitting=state["run"]["fitting"],
    )
    return deepseek.build_messages(
        transcript=state["assets"]["src"]["transcript"],
        src_language="en",
        tgt_language="zh-Hans",
        document=document,
        sentences=sentences,
        fitting=state["run"]["fitting"],
        max_attempt=3,
    )


def test_document_snapshot_round_three_and_initial_constraints(state):
    initial = messages_for(state, 1)
    assert "continuity" in initial[0]["content"]
    assert "EVERY pass" in initial[0]["content"]
    assert "LENGTH REVISION" not in initial[0]["content"]
    assert json.loads(initial[2]["content"])["pass"] == "initial"
    sentences = state["assets"]["sentences"]
    for sent in sentences:
        sent["tgt"] = [draft(f"baseline {sent['id']}"), draft(f"second {sent['id']}", 2)]
    sentences[0]["selected_attempt"] = 2
    state["assets"]["sentences"] = list(reversed(sentences))
    # Custom thresholds: 1.6 is inside this range, not automatically "too long".
    state["run"]["fitting"].update(lower_ratio=0.7, upper_ratio=1.7)
    messages = messages_for(state, 3, [2, 3, 4])
    context = json.loads(messages[1]["content"])
    task = json.loads(messages[2]["content"])
    document = context["ordered_document"]
    assert context["full_source_transcript"] == state["assets"]["src"]["transcript"]
    assert [s["id"] for s in document] == [1, 2, 3, 4]
    assert document[0]["current_text"] == "second 1"
    assert document[0]["baseline_text"] == "baseline 1"
    assert not document[0]["editable"]
    assert document[0]["retained_variants"] == [{"attempt": 2, "text": "second 1"}]
    assert document[1]["current_text"] == "baseline 2"
    assert document[1]["draft_status"] == "provisional"
    assert document[2]["speaker_id"] == "B"
    assert len(document[1]["retained_variants"]) == 2
    assert task["editable_ids"] == [2, 3, 4]
    assert task["sentences"][0]["allowed_duration_ms"] == [700, 1700]
    assert task["sentences"][0]["neighbors"][0]["current_attempt"] == 2
    assert task["sentences"][0]["history"][0]["timing_action"] == "within_range"
    assert "independent replacement" in messages[0]["content"]
    assert "not an exact ratio of 1" in messages[0]["content"]
    # Snapshot remains detached when later selections/translations change.
    sentences[0]["tgt"][1]["text"] = "changed later"
    assert document[0]["current_text"] == "second 1"
    with pytest.raises(ValueError, match="selected sentence"):
        messages_for(state, 3, [1])


@pytest.mark.parametrize(
    "items",
    [
        [{"id": 1, "text": "valid first result"}],
        [{"id": 1, "text": "a"}, {"id": 1, "text": "b"}],
        [{"id": 1, "text": "a"}, {"id": 9, "text": "extra"}],
        [{"id": 1, "text": "a"}, {"id": 2, "text": " "}],
        [{"id": 1, "text": "a"}, {"id": 2, "text": None}],
        [{"id": True, "text": "a"}, {"id": 2, "text": "b"}],
        [{"id": "1", "text": "a"}, {"id": 2, "text": "b"}],
    ],
)
def test_invalid_batch_never_partially_writes_and_retains_cost(state, tmp_path, monkeypatch, items):
    before = copy.deepcopy(state["assets"]["sentences"])
    monkeypatch.setattr(
        translation,
        "get_adapter",
        lambda _: SimpleNamespace(
            run=lambda *_: {"translations": items, "cost_cny": 0.123},
        ),
    )
    assert not translation.run(tmp_path, state, sentence_ids=[1, 2]).ok
    assert state["assets"]["sentences"] == before
    stored = load_state(tmp_path)
    assert stored["assets"]["sentences"] == before
    assert stored["assets"]["cost"]["cost_of_translation"] == 0.123
    assert not stored["ledger"][-1]["ok"]


def test_adapter_json_mode_trace_and_paid_malformed_answer(state, tmp_path, monkeypatch):
    document, sentences = build_context(
        state["assets"]["sentences"],
        sentence_ids=None,
        attempt=1,
        fitting=state["run"]["fitting"],
    )
    contents = ['{"translations":[{"id":1,"text":"hello"}]}', "{broken", None]
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": contents[len(requests) - 1],
                            "reasoning_content": "private reasoning",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        deepseek.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    inputs = {
        "api_key": "secret-test-key",
        "transcript": "source",
        "src_language": "en",
        "tgt_language": "zh-Hans",
        "sentences": sentences,
        "document": document,
        "fitting": state["run"]["fitting"],
        "max_attempt": 3,
    }
    out = deepseek.DeepSeekFlashAdapter().run(inputs, tmp_path / "valid")
    assert out["translations"] == [{"id": 1, "text": "hello"}]
    assert out["prompt_version"] == deepseek.PROMPT_VERSION
    payload = json.loads(requests[0].content)
    assert payload["model"] == "deepseek-flash"
    assert payload["response_format"] == {"type": "json_object"}
    for dirname in ("malformed", "empty"):
        with pytest.raises(AdapterError) as exc:
            deepseek.DeepSeekFlashAdapter().run(inputs, tmp_path / dirname)
        assert exc.value.cost_cny > 0
    assert len(requests) == 3  # no hidden re-request after paid malformed content
    for path in tmp_path.rglob("*.json"):
        trace = path.read_text()
        assert "secret-test-key" not in trace
        assert "private reasoning" not in trace
        assert "Authorization" not in trace


def test_slot_retains_cost_from_adapter_error(state, tmp_path, monkeypatch):
    def fail(*_):
        raise AdapterError("external_fatal", "bad response", cost_cny=0.25)

    monkeypatch.setattr(translation, "get_adapter", lambda _: SimpleNamespace(run=fail))
    assert not translation.run(tmp_path, state).ok
    assert state["assets"]["cost"]["cost_of_translation"] == 0.25
    assert all(not s["tgt"] for s in state["assets"]["sentences"])


@pytest.mark.parametrize("change", [None, "text", "reference", "source", "audio", "adapter"])
def test_tts_reuses_only_verified_exact_inputs(state, tmp_path, monkeypatch, change):
    sent = state["assets"]["sentences"][0]
    sent["tgt"] = [draft("baseline")]
    calls = []

    def generate(inputs, tmp):
        calls.append(inputs)
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / "out.wav"
        path.write_bytes(b"audio output")
        return {"audio_path": str(path), "cost_cny": 0.1}

    monkeypatch.setattr(tts, "get_adapter", lambda _: SimpleNamespace(run=generate))
    assert tts.run(tmp_path, state, sentence_id=1, attempt=1).ok
    sent["tgt"].append(draft("baseline", 2))
    if change == "text":
        sent["tgt"][1]["text"] = "baseline!"  # punctuation is meaningful
    elif change == "reference":
        path = tmp_path / sent["src"]["audio"]["path"]
        path.write_bytes(b"different reference")
        sent["src"]["audio"] = file_ref(path, relative_to=tmp_path)
    elif change == "source":
        sent["src"]["text"] += " changed"
    elif change == "audio":
        (tmp_path / sent["tgt"][0]["audio"]["path"]).write_bytes(b"corrupt")
    elif change == "adapter":
        state["run"]["slots"]["tts"]["order"] = ["fal/other-model"]
    assert tts.run(tmp_path, state, sentence_id=1, attempt=2).ok
    if change is None:
        assert len(calls) == 1
        assert state["assets"]["cost"]["cost_of_tts"] == 0.1
        assert len(state["ledger"]) == 1
        assert sent["tgt"][1]["reused_from_attempt"] == 1
        assert sent["tgt"][1]["audio"] == sent["tgt"][0]["audio"]
    else:
        assert len(calls) == 2
        assert "reused_from_attempt" not in sent["tgt"][1]
        assert state["assets"]["cost"]["cost_of_tts"] == 0.2


def test_rounds_mix_choices_with_unchanged_stop_and_matching_outputs(state, tmp_path, monkeypatch):
    events, snapshots = [], []
    texts = {
        1: ["long1", "better1", "longagain1"],
        2: ["same2", "same2"],
        3: ["long3", "fits3"],
        4: ["fits4"],
    }
    lengths = {
        "long1": 1600,
        "better1": 1300,
        "longagain1": 1500,
        "same2": 1600,
        "long3": 1600,
        "fits3": 900,
        "fits4": 1000,
    }

    def translate(inputs, tmp):
        snapshots.append(copy.deepcopy(inputs))
        attempt = inputs["sentences"][0]["attempt"]
        events.append(("translation", attempt))
        return {
            "translations": [
                {"id": s["id"], "text": texts[s["id"]][attempt - 1]}
                for s in reversed(inputs["sentences"])
            ],
            "cost_cny": 0.1,
        }

    def synthesize(inputs, tmp):
        events.append(("tts", inputs["text"]))
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / "out.wav"
        path.write_text(inputs["text"])
        return {"audio_path": str(path), "cost_cny": 0.2}

    def measure(path):
        text = path.read_text()
        events.append(("measure", text))
        return lengths[text]

    monkeypatch.setattr(translation, "get_adapter", lambda _: SimpleNamespace(run=translate))
    monkeypatch.setattr(tts, "get_adapter", lambda _: SimpleNamespace(run=synthesize))
    monkeypatch.setattr(duration_fitting, "audio_duration_ms", measure)
    assert translation.run(tmp_path, state).ok
    assert runner._run_fitting_rounds(tmp_path, state)
    sentences = state["assets"]["sentences"]
    assert [s["selected_attempt"] for s in sentences] == [2, 1, 2, 1]
    assert [s["fitting_stop_reason"] for s in sentences] == [
        "max_rewrites",
        "unchanged_text",
        "within_range",
        "within_range",
    ]
    assert [[s["id"] for s in snap["sentences"]] for snap in snapshots] == [
        [1, 2, 3, 4],
        [1, 2, 3],
        [1],
    ]
    assert snapshots[2]["document"][2]["current_text"] == "fits3"
    assert snapshots[2]["document"][0]["current_text"] == "long1"
    assert len(sentences[1]["tgt"]) == 2
    assert sentences[1]["tgt"][1]["reused_from_attempt"] == 1
    assert sum(e[0] == "tts" for e in events) == 7
    assert state["assets"]["cost"]["cost_of_tts"] == pytest.approx(1.4)
    # Each round generates every new TTS before any fitting measurement.
    assert [e[0] for e in events] == (
        ["translation"]
        + ["tts"] * 4
        + ["measure"] * 4
        + ["translation"]
        + ["tts"] * 2
        + ["measure"] * 3
        + ["translation", "tts", "measure"]
    )
    aligned_inputs = []

    def align(args):
        source = args[args.index("-i") + 1]
        aligned_inputs.append(Path(source).read_text())
        Path(args[-1]).write_bytes(b"aligned")

    monkeypatch.setattr(alignment, "run_ffmpeg", align)
    monkeypatch.setattr(alignment, "audio_duration_ms", lambda _: 1000)
    for sent in sentences:
        assert alignment.run(tmp_path, state, sentence_id=sent["id"]).ok
    assert aligned_inputs == ["better1", "same2", "fits3", "fits4"]
    srt = tmp_path / "output.srt"
    mixing._write_srt(state, srt)
    for text in aligned_inputs:
        assert text in srt.read_text()
    assert "longagain1" not in srt.read_text()
