"""Formatting utilities for presenting trades in Telegram messages."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional


def shorten(address: str, prefix: int = 6, suffix: int = 4) -> str:
    """Return a shortened representation of an Ethereum address."""
    if not address or len(address) <= prefix + suffix:
        return address
    return f"{address[:prefix]}…{address[-suffix:]}"


def _format_labels(labels: Iterable[str]) -> str:
    """Format label list for display."""
    cleaned = [label for label in labels if label]
    if not cleaned:
        return ""
    return " (" + ", ".join(cleaned) + ")"


def _format_time(timestamp: Any) -> str:
    """Convert a timestamp into a UTC ISO representation."""
    try:
        seconds = int(timestamp)
    except (TypeError, ValueError):
        return str(timestamp)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def build_message(
    trades: List[dict[str, Any]],
    filter_outcome: Optional[str],
    max_rows: int = 12,
) -> str:
    """Build the Telegram message summarising the smart money trades."""
    header = "*Smart Money Trades (last 120m)*"
    if filter_outcome:
        header += f"\n_Filter: {filter_outcome}_"

    if not trades:
        return header + "\n\nTidak ada trade Smart Money yang ditemukan."

    lines: List[str] = []
    count = 0
    for trade in trades:
        outcome = (trade.get("outcome") or "").upper()
        if filter_outcome and outcome != filter_outcome:
            continue
        question = trade.get("market", {}).get("question", "Unknown market")
        maker = trade.get("makerAddress", "")
        labels = trade.get("labels", [])
        size = trade.get("size")
        price = trade.get("price")
        match_time = trade.get("matchTime")

        line = (
            f"• *{question}*\n"
            f"  Outcome: `{outcome}`\n"
            f"  Maker: `{shorten(maker)}`{_format_labels(labels)}\n"
            f"  Size @ Price: {size} @ {price}\n"
            f"  Waktu: {_format_time(match_time)}"
        )
        lines.append(line)
        count += 1
        if count >= max_rows:
            break

    if not lines:
        return header + "\n\nTidak ada trade Smart Money yang cocok dengan filter."

    body = "\n\n".join(lines)
    return f"{header}\n\n{body}"
