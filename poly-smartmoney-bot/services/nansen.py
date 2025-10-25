"""Helpers for determining whether an address is labelled Smart Money by Nansen."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Tuple

import requests

SMART_LABELS = {
    "Smart Trader",
    "30D Smart Trader",
    "90D Smart Trader",
    "180D Smart Trader",
    "Fund",
}

NANSEN_API_URL = "https://api.nansen.ai/api/v1/profiler/address/labels"


class NansenError(RuntimeError):
    """Raised when the Nansen Profiler API responds with an error."""


def _get_headers() -> dict[str, str]:
    """Construct headers including the API key for the Nansen Profiler service."""
    api_key = os.getenv("NANSEN_API_KEY")
    if not api_key:
        raise RuntimeError("NANSEN_API_KEY is not set")
    return {"apiKey": api_key}


def _build_payload(address: str, chain: str) -> dict:
    """Create the request payload for the Nansen Profiler API."""
    return {
        "chain": chain,
        "address": address.lower(),
        "pagination": {"page": 1, "per_page": 100},
    }


@lru_cache(maxsize=512)
def is_smart_money(address: str, chain: str = "polygon") -> Tuple[bool, List[str]]:
    """Return whether the address has Smart Money labels and the labels themselves."""
    headers = _get_headers()
    payload = _build_payload(address, chain)

    try:
        response = requests.post(NANSEN_API_URL, json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:  # noqa: PERF203
        raise NansenError("Failed to call Nansen Profiler API") from exc

    if response.status_code != 200:
        raise NansenError(f"Nansen returned status {response.status_code}")

    data = response.json()
    labels = data.get("data", {}).get("items", [])
    if not isinstance(labels, list):
        raise NansenError("Unexpected Nansen response format")

    label_names = [item.get("label") for item in labels if isinstance(item, dict)]
    smart = any(label in SMART_LABELS for label in label_names)
    return smart, [label for label in label_names if label]
