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
    """Return the configured Polymarket subgraph endpoint."""
    return os.getenv("POLY_SUBGRAPH_URL", DEFAULT_SUBGRAPH_URL)


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
    except requests.RequestException as exc:  # noqa: PERF203
        raise PolymarketError("Failed to call Polymarket subgraph") from exc

    if response.status_code != 200:
        raise PolymarketError(
            f"Polymarket returned status {response.status_code}: {response.text}"
        )

    data = response.json()
    errors = data.get("errors")
    if errors:
        raise PolymarketError(f"Polymarket query errors: {errors}")

    fills = data.get("data", {}).get("fills", [])
    if not isinstance(fills, list):
        raise PolymarketError("Unexpected Polymarket response structure")

    return fills
