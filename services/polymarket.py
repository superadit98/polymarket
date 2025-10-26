"""Utilities for querying Polymarket trades from the activity subgraph."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List
import requests


# Endpoint default: versi yang (masih) punya 'fills'
DEFAULT_SUBGRAPH_URL = (
    "https://api.goldsky.com/api/public/project_clt2s6h8u00hm35xj2dz1h1fg/"
    "subgraphs/activity/0.0.3/gn"
)

# Query lama (schema dengan 'fills')
FILLS_QUERY = """
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

# Fallback untuk schema baru (tanpa 'fills') – beberapa endpoint mengganti ke 'trades'
TRADES_QUERY = """
query RecentTrades($matchTime: BigInt!, $limit: Int!) {
  trades(
    first: $limit
    orderBy: timestamp
    orderDirection: desc
    where: { timestamp_gte: $matchTime }
  ) {
    id
    maker
    outcome
    amount
    price
    timestamp
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


def _post_graphql(url: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    payload = {"query": query, "variables": variables}
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PolymarketError(f"Failed to call Polymarket subgraph: {exc}") from exc
    try:
        data = resp.json()
    except ValueError as exc:
        raise PolymarketError(f"Invalid JSON from Polymarket: {resp.text[:500]}") from exc
    if "errors" in data and data["errors"]:
        raise PolymarketError(f"Polymarket query errors: {data['errors']}")
    return data


def _normalize_from_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map schema 'trades' -> schema 'fills' agar downstream tidak berubah."""
    out: List[Dict[str, Any]] = []
    for t in trades:
        out.append(
            {
                "id": t.get("id"),
                "makerAddress": t.get("maker"),
                "outcome": t.get("outcome"),
                "size": t.get("amount"),
                "price": t.get("price"),
                "matchTime": t.get("timestamp"),
                "market": t.get("market") or {},
            }
        )
    return out


def query_trades(since_minutes: int = 120, limit: int = 200) -> List[Dict[str, Any]]:
    """Query recent Polymarket trades; works with both old/new schemas."""
    match_time = int(time.time()) - since_minutes * 60
    url = _get_subgraph_url()
    vars_ = {"matchTime": match_time, "limit": limit}

    # 1) Coba schema lama ('fills')
    try:
        data = _post_graphql(url, FILLS_QUERY, vars_)
        fills = data.get("data", {}).get("fills")
        if isinstance(fills, list):
            return fills
        # kalau bukan list, coba fallback
    except PolymarketError as e:
        msg = str(e)
        # Kalau error memang "no field `fills`", kita lanjut ke fallback
        if "`fills`" not in msg and "has no field" not in msg:
            # Error bukan karena schema; lempar lagi
            raise

    # 2) Fallback ke schema baru ('trades') dan normalisasi
    data2 = _post_graphql(url, TRADES_QUERY, vars_)
    trades = data2.get("data", {}).get("trades")
    if not isinstance(trades, list):
        raise PolymarketError(f"Unexpected Polymarket response: {data2}")
    return _normalize_from_trades(trades)
