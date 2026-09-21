"""Minimal fal.ai queue client: upload, submit, poll, download, cost estimate."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import fal_client
import httpx

from magicdub_cli.errors import (
    EXTERNAL_FATAL,
    EXTERNAL_RETRYABLE,
    USD_TO_CNY,
    AdapterError,
    classify_http,
)

QUEUE_BASE = "https://queue.fal.run"
API_BASE = "https://api.fal.ai"
POLL_INTERVAL_S = 5.0
POLL_DEADLINE_S = 1800.0


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
        "X-Fal-No-Retry": "1",
        "x-app-fal-disable-fallback": "true",
    }


def upload_file(path: Path, api_key: str) -> str:
    os.environ["FAL_KEY"] = api_key
    return fal_client.upload_file(str(path))


def run_model(
    *,
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    download_to: Path | None = None,
    result_key: str | None = None,
) -> tuple[dict[str, Any], float | None]:
    """Submit → poll → optional download. Returns (result_json, cost_cny_or_none)."""
    headers = _headers(api_key)
    with httpx.Client(timeout=httpx.Timeout(30.0, read=120.0)) as client:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                submit = client.post(
                    f"{QUEUE_BASE}/{endpoint}",
                    headers=headers,
                    json=payload,
                )
                if submit.status_code >= 400:
                    code = classify_http(submit.status_code)
                    raise AdapterError(
                        code,
                        f"fal submit HTTP {submit.status_code}: {submit.text[:500]}",
                    )
                body = submit.json()
                request_id = body.get("request_id")
                status_url = body.get("status_url")
                response_url = body.get("response_url")
                if not (request_id and status_url and response_url):
                    raise AdapterError(EXTERNAL_FATAL, f"fal submit missing urls: {body}")

                deadline = time.time() + POLL_DEADLINE_S
                billable_units: float | None = None
                while time.time() < deadline:
                    st = client.get(status_url, headers=headers)
                    if st.status_code in (429, 500, 502, 503, 504):
                        time.sleep(POLL_INTERVAL_S)
                        continue
                    if st.status_code >= 400:
                        raise AdapterError(
                            classify_http(st.status_code),
                            f"fal status HTTP {st.status_code}: {st.text[:500]}",
                        )
                    units_hdr = st.headers.get("x-fal-billable-units")
                    if units_hdr:
                        try:
                            billable_units = float(units_hdr)
                        except ValueError:
                            pass
                    status_body = st.json()
                    status = status_body.get("status")
                    if status == "COMPLETED":
                        break
                    if status in ("FAILED", "CANCELLED"):
                        raise AdapterError(
                            EXTERNAL_FATAL,
                            f"fal job {status}: {status_body}",
                        )
                    time.sleep(POLL_INTERVAL_S)
                else:
                    raise AdapterError(EXTERNAL_RETRYABLE, "fal poll timed out")

                resp = client.get(response_url, headers=headers)
                if resp.status_code >= 400:
                    raise AdapterError(
                        classify_http(resp.status_code),
                        f"fal result HTTP {resp.status_code}: {resp.text[:500]}",
                    )
                result = resp.json()
                if (
                    isinstance(result, dict)
                    and "data" in result
                    and isinstance(result["data"], dict)
                ):
                    result = result["data"]

                cost_cny = _estimate_cost_cny(
                    client, headers, endpoint, request_id, billable_units, result
                )

                if download_to is not None:
                    obj = result.get(result_key) if result_key else result
                    url = obj["url"] if isinstance(obj, dict) else None
                    if not url and isinstance(result, dict):
                        # try common keys
                        for key in ("audio", "vocals", "image"):
                            if isinstance(result.get(key), dict) and result[key].get("url"):
                                url = result[key]["url"]
                                break
                    if not url:
                        raise AdapterError(EXTERNAL_FATAL, f"no download url in result: {result}")
                    _download(client, url, download_to)

                return result, cost_cny
            except AdapterError as exc:
                last_err = exc
                if exc.code != EXTERNAL_RETRYABLE or attempt == 2:
                    raise
                time.sleep(2**attempt)
            except httpx.HTTPError as exc:
                last_err = AdapterError(EXTERNAL_RETRYABLE, str(exc))
                if attempt == 2:
                    raise last_err from exc
                time.sleep(2**attempt)
        assert last_err is not None
        raise last_err


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as r:
        if r.status_code != 200:
            raise AdapterError(EXTERNAL_RETRYABLE, f"download HTTP {r.status_code}")
        tmp = dest.with_suffix(dest.suffix + ".download")
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
        tmp.replace(dest)


def _estimate_cost_cny(
    client: httpx.Client,
    headers: dict[str, str],
    endpoint: str,
    request_id: str,
    billable_units: float | None,
    result: dict[str, Any],
) -> float | None:
    """Best-effort CNY; unknown stays None."""
    usd: float | None = None
    try:
        billing = client.get(
            f"{API_BASE}/v1/models/billing-events",
            headers=headers,
            params={"request_id": request_id},
        )
        if billing.status_code == 200:
            events = billing.json()
            if isinstance(events, list):
                items = events
            else:
                items = events.get("items") or events.get("data") or []
            total = 0.0
            found = False
            for item in items:
                if isinstance(item, dict) and item.get("cost_total") is not None:
                    total += float(item["cost_total"])
                    found = True
            if found:
                usd = total
    except httpx.HTTPError:
        pass

    if usd is None:
        try:
            pricing = client.get(
                f"{API_BASE}/v1/models/pricing",
                headers=headers,
                params={"endpoint_id": endpoint},
            )
            if pricing.status_code == 200 and billable_units is not None:
                data = pricing.json()
                unit_price = None
                if isinstance(data, dict):
                    unit_price = data.get("unit_price") or data.get("price")
                    prices = data.get("prices")
                    if unit_price is None and isinstance(prices, list) and prices:
                        unit_price = prices[0].get("unit_price")
                if unit_price is not None:
                    usd = float(unit_price) * float(billable_units)
        except httpx.HTTPError:
            pass

    if usd is None and billable_units is not None:
        # last resort: leave unknown
        return None
    if usd is None:
        return None
    return round(usd * USD_TO_CNY, 8)
