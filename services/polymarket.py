"""Utilities for querying Polymarket trades from (various) activity subgraphs."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_SUBGRAPH_URL = (
    "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/"
    "subgraphs/activity-subgraph/0.0.4/gn"
)

# Kandidat nama koleksi di root Query (bervariasi antar versi subgraph)
CANDIDATE_COLLECTIONS = [
    "fills",
    "marketFills",
    "trades",
    "tradeEvents",
    "swaps",
    "orders",          # jaga-jaga
    "marketTrades",    # jaga-jaga
]

# Kandidat field waktu yang biasa digunakan untuk order/filter
CANDIDATE_TIME_FIELDS = [
    "matchTime",
    "timestamp",
    "createdAt",
    "blockTimestamp",
    "filledAt",
]

# Kandidat field maker / size / price / outcome di item
CANDIDATE_MAKER_FIELDS = ["makerAddress", "maker", "trader", "from", "user"]
CANDIDATE_SIZE_FIELDS = ["size", "amount", "qty", "quantity"]
CANDIDATE_PRICE_FIELDS = ["price", "avgPrice", "fillPrice"]
CANDIDATE_OUTCOME_FIELDS = ["outcome", "side", "position"]
CANDIDATE_MARKET_FIELD = "market"  # hampir selalu "market"
CANDIDATE_MARKET_ID_FIELDS = ["id", "marketId"]
CANDIDATE_MARKET_QUESTION_FIELDS = ["question", "title", "name"]

class PolymarketError(RuntimeError):
    """Raised when the Polymarket API request fails."""


def _get_subgraph_url() -> str:
    """Return a valid Polymarket subgraph endpoint."""
    env_url = (os.getenv("POLY_SUBGRAPH_URL") or "").strip()
    if not env_url or not env_url.startswith("http"):
        return DEFAULT_SUBGRAPH_URL
    return env_url


def _post_graphql(url: str, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    try:
        resp = requests.post(url, json={"query": query, "variables": variables}, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PolymarketError(f"Failed to call Polymarket subgraph: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise PolymarketError(f"Invalid JSON from Polymarket: {resp.text[:500]}") from exc

    if "errors" in data:
        # Biarkan caller mencoba kombinasi lain; lempar error apa adanya
        raise PolymarketError(f"Polymarket query errors: {data['errors']}")
    return data


def _first_existing(d: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _normalize_item(it: Dict[str, Any], time_field: str) -> Dict[str, Any]:
    # id
    _id = it.get("id")

    # maker
    maker = _first_existing(it, CANDIDATE_MAKER_FIELDS)

    # outcome
    outcome = _first_existing(it, CANDIDATE_OUTCOME_FIELDS)

    # size/amount
    size = _first_existing(it, CANDIDATE_SIZE_FIELDS)

    # price
    price = _first_existing(it, CANDIDATE_PRICE_FIELDS)

    # matchTime (pakai field yang berhasil dipakai untuk order/filter; kalau tidak ada, coba cari)
    match_time = it.get(time_field)
    if match_time is None:
        match_time = _first_existing(it, CANDIDATE_TIME_FIELDS)

    # market (id, question)
    market_raw = it.get(CANDIDATE_MARKET_FIELD) or {}
    if isinstance(market_raw, dict):
        market_id = _first_existing(market_raw, CANDIDATE_MARKET_ID_FIELDS)
        market_question = _first_existing(market_raw, CANDIDATE_MARKET_QUESTION_FIELDS)
    else:
        market_id = None
        market_question = None

    return {
        "id": _id,
        "makerAddress": maker,
        "outcome": outcome,
        "size": size,
        "price": price,
        "matchTime": match_time,
        "market": {"id": market_id, "question": market_question},
    }


def _build_query(collection: str, time_field: str) -> str:
    """
    Bangun query GraphQL untuk koleksi & field waktu tertentu.
    - Pakai 'orderBy: <time_field>' dan filter 'where: { <time_field>_gte: $since }'
    - Project field-field umum + market{id question}
    """
    return f"""
    query Q($since: BigInt!, $limit: Int!) {{
      {collection}(
        first: $limit
        orderBy: {time_field}
        orderDirection: desc
        where: {{ {time_field}_gte: $since }}
      ) {{
        id
        {" ".join(set(CANDIDATE_MAKER_FIELDS + CANDIDATE_OUTCOME_FIELDS + CANDIDATE_SIZE_FIELDS + CANDIDATE_PRICE_FIELDS + [time_field]))}
        market {{
          {" ".join(set(CANDIDATE_MARKET_ID_FIELDS + CANDIDATE_MARKET_QUESTION_FIELDS))}
        }}
      }}
    }}
    """


def query_trades(since_minutes: int = 120, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Query recent trades secara defensif:
    - Coba beberapa nama koleksi + nama field waktu
    - Begitu ada kombinasi yang valid & mengembalikan data, langsung return (dinormalisasi)
    """
    since = int(time.time()) - since_minutes * 60
    url = _get_subgraph_url()

    last_error: Optional[str] = None

    for collection in CANDIDATE_COLLECTIONS:
        for tfield in CANDIDATE_TIME_FIELDS:
            query = _build_query(collection, tfield)
            variables = {"since": since, "limit": int(limit)}

            try:
                data = _post_graphql(url, query, variables)
            except PolymarketError as e:
                # Simpan error terakhir untuk diagnosa, lalu lanjut coba kombinasi lain
                last_error = str(e)
                continue

            items = data.get("data", {}).get(collection, [])
            if not isinstance(items, list):
                last_error = f"Unexpected response for {collection} using {tfield}: {data}"
                continue

            if items:
                # sukses; normalisasi & kembalikan
                return [_normalize_item(it, tfield) for it in items]

            # kalau kosong, tetap catat bahwa kombinasi valid tapi tidak ada data
            last_error = f"Combination valid but empty: {collection}/{tfield}"

    # Jika semua gagal
    raise PolymarketError(
        "Unable to query trades from the subgraph. "
        f"Last attempt error: {last_error}. "
        "Coba set env POLY_SUBGRAPH_URL ke endpoint activity subgraph yang benar untuk akun/proyekmu."
    )
