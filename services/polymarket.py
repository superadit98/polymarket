"""Utilities for querying Polymarket trades from the activity subgraph."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List
import requests


DEFAULT_SUBGRAPH_URL = (
    "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/"
    "subgraphs/activity-subgraph/0.0.4/gn"
)

SMART_QUERY = """
query RecentTrades($matchTime: BigInt!, $limit: Int!) {
  fills(
    first: $limit
    orderBy: matchTime
    orderDirection: desc
    where: { matchTime_gte: $matchTime }
  ) {
    id
    makerAddress
    outcome
    size
    price
    matchTime
    market {
      id
      question
    }
  }
}
"""


class PolymarketError(RuntimeError):
    """Raised when the Polymarket API request fails."""


def _get_subgraph_url() -> str:
    """Return a valid Polymarket subgraph endpoint."""
    env_url = (os.getenv("POLY_SUBGRAPH_URL") or "").strip()
    if not env_url or not env_url.startswith("http"):
        return DEFAULT_SUBGRAPH_URL
    return env_url


def query_trades(since_minutes: int = 120, limit: int = 200) -> List[Dict[str, Any]]:
    """Query the recent Polymarket trades within the given timeframe."""
    match_time = int(time.time()) - since_minutes * 60
    url = _get_subgraph_url()
    payload = {
        "query": SMART_QUERY,
        "variables": {"matchTime": match_time, "limit": limit},
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PolymarketError(f"Failed to call Polymarket subgraph: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise PolymarketError(f"Invalid JSON response from Polymarket: {response.text}") from exc

    if "errors" in data:
        raise PolymarketError(f"Polymarket query errors: {data['errors']}")

    fills = data.get("data", {}).get("fills", [])
    if not isinstance(fills, list):
        raise PolymarketError(f"Unexpected Polymarket response: {data}")

    return fills
