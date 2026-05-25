"""Sector and peer-group context for ranked tickers."""

from __future__ import annotations

from typing import Any

PEER_GROUPS: dict[str, tuple[str, ...]] = {
    "semiconductors": ("NVDA", "AMD", "AVGO", "INTC", "ARM", "MRVL", "TSM", "MU", "SMCI"),
    "ai_software": ("PLTR", "MSFT", "GOOGL", "GOOG", "META", "SNOW", "AI", "ORCL", "CRM"),
    "space_aerospace": ("RKLB", "ASTS", "LUNR", "BA", "LMT", "NOC", "RTX"),
    "ev_clean_energy": ("TSLA", "RIVN", "LCID", "NIO", "XPEV", "ENPH", "FSLR"),
    "fintech": ("SOFI", "AFRM", "HOOD", "PYPL", "SQ", "UPST"),
    "crypto_equities": ("COIN", "MSTR", "MARA", "RIOT", "CLSK", "HUT"),
    "biotech": ("MRNA", "BNTX", "CRSP", "EDIT", "NTLA", "RXRX"),
}

SECTOR_LABELS = {
    "semiconductors": "Semiconductors",
    "ai_software": "AI / software",
    "space_aerospace": "Space / aerospace",
    "ev_clean_energy": "EV / clean energy",
    "fintech": "Fintech",
    "crypto_equities": "Crypto equities",
    "biotech": "Biotech",
}

_TICKER_TO_GROUP: dict[str, str] = {}
for group_id, tickers in PEER_GROUPS.items():
    for ticker in tickers:
        _TICKER_TO_GROUP[ticker.upper()] = group_id


def peer_group_for_ticker(ticker: str) -> tuple[str | None, str | None, list[str]]:
    """Return (sector_group label, peer_group id, peer ticker list)."""

    symbol = ticker.upper()
    group_id = _TICKER_TO_GROUP.get(symbol)
    if not group_id:
        return None, None, []
    return SECTOR_LABELS.get(group_id, group_id), group_id, list(PEER_GROUPS[group_id])


def apply_peer_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate ranked rows with peer attention/score ranks within sector."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        sector, group_id, _peers = peer_group_for_ticker(ticker)
        row["sector_group"] = sector
        row["peer_group"] = group_id
        if group_id:
            grouped.setdefault(group_id, []).append(row)

    for group_rows in grouped.values():
        by_attention = sorted(
            group_rows,
            key=lambda item: float(item.get("attention_acceleration") or 0),
            reverse=True,
        )
        by_score = sorted(group_rows, key=lambda item: float(item.get("final_score") or 0), reverse=True)
        for index, row in enumerate(by_attention, start=1):
            row["peer_attention_rank"] = index
        for index, row in enumerate(by_score, start=1):
            row["peer_score_rank"] = index
        leader = by_attention[0] if by_attention else None
        for row in group_rows:
            row["peer_context_summary"] = _peer_summary(row, leader, by_attention)

    for row in rows:
        row.setdefault("sector_group", None)
        row.setdefault("peer_group", None)
        row.setdefault("peer_attention_rank", None)
        row.setdefault("peer_score_rank", None)
        row.setdefault("peer_context_summary", None)
    return rows


def _peer_summary(
    row: dict[str, Any],
    leader: dict[str, Any] | None,
    ordered: list[dict[str, Any]],
) -> str | None:
    ticker = str(row.get("ticker") or "").upper()
    sector = row.get("sector_group")
    if not sector or not leader:
        return None
    if ticker == str(leader.get("ticker") or "").upper():
        peers = [str(item.get("ticker")) for item in ordered[1:3] if item.get("ticker")]
        if peers:
            return f"{ticker} is the top {sector} ticker by Reddit acceleration today, ahead of {', '.join(peers)}."
        return f"{ticker} leads {sector} Reddit attention in today's scan."
    leader_ticker = str(leader.get("ticker") or "")
    rank = row.get("peer_attention_rank")
    return f"{ticker} ranks #{rank} for Reddit acceleration among {sector} peers today (leader: {leader_ticker})."
