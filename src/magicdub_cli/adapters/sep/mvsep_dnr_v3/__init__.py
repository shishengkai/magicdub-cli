"""mvsep/dnr-v3 — DnR v3 Mel+SCNet via apex API + fal CDN URL upload."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from magicdub_cli import constants as C
from magicdub_cli.adapters.base import Adapter
from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    INPUT_INVALID,
    USD_TO_CNY,
    AdapterError,
    classify_http,
)
from magicdub_cli.fal_api import suffix_from_remote, upload_file
from magicdub_cli.ffmpeg_util import FFmpegError, run_ffmpeg

# Apex create endpoint (not de2). URL uploads are remote jobs → get-remote, then get.
CREATE_URL = "https://mvsep.com/api/separation/create"
GET_URL = "https://mvsep.com/api/separation/get"
GET_REMOTE_URL = "https://mvsep.com/api/separation/get-remote"

# DnR v3 · Mel+SCNet · direct extract · include independent-model results · PCM16 WAV
PARAMETERS = {
    "sep_type": "56",
    "add_opt1": "2",
    "add_opt2": "0",
    "add_opt3": "1",
    "output_format": "1",
    "is_demo": "0",
}

POLL_INTERVAL_S = 15.0
POLL_DEADLINE_S = 1800.0
STEM_TYPES = ("speech", "music", "sfx")


def _api_ok(value: object) -> bool:
    """MVSep may return JSON boolean true or the string \"true\"."""
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes"):
        return True
    if value == 1:
        return True
    return False


class MvsepDnrV3Adapter(Adapter):
    adapter_id = "mvsep/dnr-v3"
    slot = "sep"

    def run(self, inputs: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
        mvsep_key = inputs["api_key"]
        fal_key = inputs["fal_key"]
        audio_path = Path(inputs["audio_path"])
        if not audio_path.is_file():
            raise AdapterError(INPUT_INVALID, "sep input audio missing")

        tmp_dir.mkdir(parents=True, exist_ok=True)
        # Lossless FLAC shrinks demux WAV before fal CDN / MVSep size limits (free tier 100 MB).
        flac_path = _to_flac(audio_path, tmp_dir / "input.flac")
        # Upload via fal CDN; MVSep fetches with remote_type=direct.
        audio_url = upload_file(flac_path, fal_key)
        job_hash = _create_job(mvsep_key, audio_url)
        # URL create → remote hash; poll get-remote until done → local separation hash + files via get.
        files = _poll_remote_then_get(job_hash)
        stems = _download_stems(files, tmp_dir)
        non_speech = _mix_music_sfx(stems["music"], stems["sfx"], tmp_dir / "non_speech.wav")
        # Local estimate: 1 credit / job × published USD/credit × FX (no Platform history lookup).
        cost_cny = _cost_cny_from_credits(C.MVSEP_CREDITS_PER_JOB)
        return {
            "speech_path": stems["speech"],
            "non_speech_path": non_speech,
            "cost_cny": cost_cny,
        }


def _create_job(api_token: str, audio_url: str) -> str:
    data = {
        **PARAMETERS,
        "api_token": api_token,
        "url": audio_url,
        "remote_type": "direct",
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as client:
            resp = client.post(CREATE_URL, data=data)
    except httpx.HTTPError as exc:
        raise AdapterError(EXTERNAL_RETRYABLE, f"mvsep create network: {exc}") from exc
    if resp.status_code >= 400:
        raise AdapterError(
            classify_http(resp.status_code),
            f"mvsep create HTTP {resp.status_code}: {resp.text[:500]}",
        )
    try:
        body = resp.json()
    except ValueError as exc:
        raise AdapterError(EXTERNAL_FATAL, f"mvsep create non-json: {resp.text[:300]}") from exc
    if not isinstance(body, dict) or not _api_ok(body.get("success")):
        raise AdapterError(EXTERNAL_FATAL, f"mvsep create rejected: {body}")
    data_obj = body.get("data") if isinstance(body.get("data"), dict) else {}
    job_hash = data_obj.get("hash")
    if not isinstance(job_hash, str) or not job_hash.strip():
        raise AdapterError(EXTERNAL_FATAL, f"mvsep create missing hash: {body}")
    return job_hash.strip()


def _poll_remote_then_get(remote_hash: str) -> dict[str, dict[str, str]]:
    """URL jobs: poll get-remote → final separation hash → get files from get."""
    result_hash = _poll_status(
        GET_REMOTE_URL,
        remote_hash,
        label="get-remote",
        on_done=_remote_done_hash,
    )
    return _poll_status(
        GET_URL,
        result_hash,
        label="get",
        on_done=lambda body, h: _stem_files(body, h),
    )


def _remote_done_hash(body: dict[str, Any], remote_hash: str) -> str:
    """get-remote done returns the real separation hash (and a link to get), not stem files."""
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    result_hash = data.get("hash")
    if isinstance(result_hash, str) and result_hash.strip():
        return result_hash.strip()
    link = data.get("link")
    if isinstance(link, str):
        parsed = urlparse(link)
        if parsed.scheme == "https" and (parsed.netloc == "mvsep.com" or parsed.netloc.endswith(".mvsep.com")):
            qs = parse_qs(parsed.query)
            values = qs.get("hash") or []
            if values and isinstance(values[0], str) and values[0].strip():
                return values[0].strip()
    raise AdapterError(
        EXTERNAL_FATAL,
        f"mvsep get-remote done missing result hash (remote={remote_hash}): {body}",
    )


def _poll_status(
    url: str,
    job_hash: str,
    *,
    label: str,
    on_done: Any,
) -> Any:
    deadline = time.time() + POLL_DEADLINE_S
    last_status: str | None = None
    with httpx.Client(timeout=httpx.Timeout(30.0, read=60.0)) as client:
        while time.time() < deadline:
            try:
                resp = client.get(url, params={"hash": job_hash})
            except httpx.HTTPError as exc:
                raise AdapterError(EXTERNAL_RETRYABLE, f"mvsep {label} network: {exc}") from exc
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(POLL_INTERVAL_S)
                continue
            if resp.status_code >= 400:
                raise AdapterError(
                    classify_http(resp.status_code),
                    f"mvsep {label} HTTP {resp.status_code}: {resp.text[:500]}",
                )
            try:
                body = resp.json()
            except ValueError as exc:
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} non-json: {resp.text[:300]}") from exc
            if not isinstance(body, dict):
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} bad body: {body!r}")
            status = body.get("status")
            if status == "not_found":
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} not_found hash={job_hash}")
            if status == "failed":
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} failed: {body}")
            if not _api_ok(body.get("success")):
                raise AdapterError(EXTERNAL_RETRYABLE, f"mvsep {label} envelope: {body}")
            if not isinstance(status, str):
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} missing status: {body}")
            if status != last_status:
                last_status = status
            if status == "done":
                return on_done(body, job_hash)
            if status not in ("waiting", "processing", "distributing", "merging"):
                raise AdapterError(EXTERNAL_FATAL, f"mvsep {label} unknown status {status!r}")
            time.sleep(POLL_INTERVAL_S)
    raise AdapterError(EXTERNAL_RETRYABLE, f"mvsep {label} timed out hash={job_hash}")


def _stem_files(body: dict[str, Any], expected_hash: str) -> dict[str, dict[str, str]]:
    data = body.get("data")
    if not isinstance(data, dict) or data.get("hash") != expected_hash:
        raise AdapterError(EXTERNAL_FATAL, "mvsep result hash mismatch")
    files = data.get("files")
    if not isinstance(files, list):
        raise AdapterError(EXTERNAL_FATAL, "mvsep result missing files list")
    out: dict[str, dict[str, str]] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").lower()
        if kind not in STEM_TYPES:
            continue  # ignore independent-model extras when add_opt3=1
        if kind in out:
            raise AdapterError(EXTERNAL_FATAL, f"mvsep duplicate stem type: {kind}")
        url = item.get("url")
        if not isinstance(url, str) or not _ok_download_url(url):
            raise AdapterError(EXTERNAL_FATAL, f"mvsep bad download url for {kind}")
        out[kind] = {"type": kind, "url": url}
    missing = [k for k in STEM_TYPES if k not in out]
    if missing:
        raise AdapterError(EXTERNAL_FATAL, f"mvsep missing stems: {missing}")
    return out


def _ok_download_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return False
    host = (parsed.netloc or "").lower()
    if host != "mvsep.com" and not host.endswith(".mvsep.com"):
        return False
    return parsed.path.startswith("/storage/")


def _download_stems(
    files: dict[str, dict[str, str]],
    tmp_dir: Path,
) -> dict[str, Path]:
    stems: dict[str, Path] = {}
    with httpx.Client(timeout=httpx.Timeout(30.0, read=300.0)) as client:
        for kind, meta in files.items():
            url = meta["url"]
            suf = suffix_from_remote(url=url, file_obj=meta)
            dest = tmp_dir / f"{kind}{suf}"
            _download(client, url, dest)
            stems[kind] = dest
    return stems


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as resp:
        if resp.status_code != 200:
            raise AdapterError(EXTERNAL_RETRYABLE, f"mvsep download HTTP {resp.status_code}")
        tmp = dest.with_suffix(dest.suffix + ".download")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
        tmp.replace(dest)


def _to_flac(src: Path, dest: Path) -> Path:
    """Encode slot audio to lossless FLAC for MVSep upload (size limit relief)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_ffmpeg(["-i", str(src), "-c:a", "flac", str(dest)])
    except FFmpegError as exc:
        raise AdapterError(INPUT_INVALID, f"mvsep flac encode failed: {exc}") from exc
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise AdapterError(INPUT_INVALID, "mvsep flac encode produced empty file")
    return dest


def _mix_music_sfx(music: Path, sfx: Path, dest: Path) -> Path:
    """Adapter-local non_speech = music + sfx (not a format conversion for the next slot)."""
    try:
        run_ffmpeg(
            [
                "-i",
                str(music),
                "-i",
                str(sfx),
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:normalize=0:duration=longest[out]",
                "-map",
                "[out]",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ]
        )
    except FFmpegError as exc:
        raise AdapterError(INPUT_INVALID, f"mvsep music+sfx mix failed: {exc}") from exc
    return dest


def _cost_cny_from_credits(credits: int | float) -> float:
    """credits × MVSEP_USD_PER_CREDIT × USD_TO_CNY."""
    return round(float(credits) * C.MVSEP_USD_PER_CREDIT * USD_TO_CNY, 8)
