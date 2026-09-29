"""Build a detached document snapshot for one translation round."""

from __future__ import annotations

from typing import Any


def build_context(
    sentences: list[dict[str, Any]],
    *,
    sentence_ids: list[int] | None,
    attempt: int,
    fitting: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Selected neighbours are fixed; unsettled sentences use the initial draft."""
    ordered = sorted(sentences, key=lambda s: (s["start_ms"], s["id"]))
    all_ids = [s["id"] for s in ordered]
    if len(all_ids) != len(set(all_ids)) or any(type(sid) is not int for sid in all_ids):
        raise ValueError("sentence ids must be unique integers")
    requested = all_ids if sentence_ids is None else sentence_ids
    editable = set(requested)
    if (
        not editable
        or any(type(sid) is not int for sid in requested)
        or len(editable) != len(requested)
        or not editable.issubset(all_ids)
    ):
        raise ValueError("invalid editable sentence ids")

    document = []
    for sent in ordered:
        previous = [t for t in sent.get("tgt", []) if t["attempt"] < attempt]
        baseline = next((t for t in previous if t["attempt"] == 1), None)
        if attempt > 1 and not baseline:
            raise ValueError(f"initial translation missing for sentence {sent['id']}")
        selected = sent.get("selected_attempt")
        current = baseline
        if selected is not None:
            if sent["id"] in editable:
                raise ValueError(f"cannot rewrite selected sentence {sent['id']}")
            current = next((t for t in previous if t["attempt"] == selected), None)
            if current is None:
                raise ValueError(f"selected translation missing for sentence {sent['id']}")
        document.append(
            {
                "id": sent["id"],
                "speaker_id": sent["speaker_id"],
                "start_ms": sent["start_ms"],
                "end_ms": sent["end_ms"],
                "source": sent["src"]["text"],
                "baseline_text": baseline["text"] if baseline else None,
                "current_text": current["text"] if current else None,
                "current_attempt": current["attempt"] if current else None,
                "retained_variants": [
                    {"attempt": t["attempt"], "text": t["text"]}
                    for t in (previous if selected is None else [current])
                ],
                "draft_status": "selected" if selected is not None else "provisional",
                "editable": sent["id"] in editable,
            }
        )

    payload = []
    lo, hi = float(fitting["lower_ratio"]), float(fitting["upper_ratio"])
    for index, sent in enumerate(ordered):
        if sent["id"] not in editable:
            continue
        duration = sent["src"]["audio_duration"]
        history = [
            {
                "attempt": t["attempt"],
                "text": t["text"],
                "tts_duration_ms": t["audio_duration"],
                "fitting_ratio": t.get("fitting_ratio"),
            }
            for t in sorted(sent.get("tgt", []), key=lambda t: t["attempt"])
            if t["attempt"] < attempt and t.get("audio_duration") is not None
        ]
        payload.append(
            {
                "id": sent["id"],
                "src_text": sent["src"]["text"],
                "baseline_text": document[index]["baseline_text"],
                "target_duration_ms": duration,
                "allowed_duration_ms": [duration * lo, duration * hi],
                "attempt": attempt,
                "history": history,
                "neighbour_ids": [
                    d["id"]
                    for d in document[max(0, index - 2) : index + 3]
                    if d["id"] != sent["id"]
                ],
            }
        )
    return document, payload


def validate_translations(items: Any, expected_ids: set[int]) -> dict[int, str]:
    """Validate the complete response before any sentence is changed."""
    if not isinstance(items, list):
        raise ValueError("translations must be a list")
    result: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            raise ValueError("translation id must be an integer")
        sid, text = item["id"], item.get("text")
        if sid not in expected_ids or sid in result:
            raise ValueError(f"unexpected or duplicate translation id: {sid}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"empty or invalid translation for sentence {sid}")
        result[sid] = text.strip()
    if set(result) != expected_ids:
        raise ValueError(f"missing translation ids: {sorted(expected_ids - set(result))}")
    return result
