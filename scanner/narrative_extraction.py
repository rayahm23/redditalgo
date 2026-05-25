"""Rule-based Reddit discussion narrative and claim extraction per ticker."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

FALLBACK_NARRATIVE = "Discussion was too limited or scattered to identify a clear narrative."

CUSTOM_STOPWORDS = frozenset({
    "have", "this", "that", "what", "also", "would", "could", "should", "really",
    "think", "going", "still", "even", "just", "much", "very", "make", "made",
    "many", "some", "more", "well", "good", "great", "thing", "things", "stock",
    "company", "shares", "market", "today", "tomorrow", "people", "guys", "lol",
    "lmao", "bro", "yeah", "with", "from", "they", "them", "your", "about", "into",
    "been", "were", "will", "when", "than", "then", "here", "there", "where",
    "like", "know", "want", "need", "said", "says", "does", "dont", "doesnt",
    "been", "being", "only", "over", "under", "after", "before", "while", "because",
    "reddit", "post", "posts", "comment", "comments", "thread", "threads",
})

KNOWN_FINANCE_PHRASES: tuple[str, ...] = (
    "free cash flow",
    "margin expansion",
    "earnings guidance",
    "ai demand",
    "data center",
    "short squeeze",
    "short interest",
    "revenue growth",
    "analyst upgrade",
    "analyst downgrade",
    "price target",
    "loan growth",
    "ai lending",
)

FINANCE_PHRASE_BOOST = 3

_TOKEN_RE = re.compile(r"[a-z][a-z0-9'-]{1,}")
_TICKER_RE = re.compile(r"\$?([A-Z]{1,5})\b")

# --- AI subthemes: specific patterns only (no catch-all datacenter on vague "ai") ---

AI_SUBTHEME_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "ai_datacenter_gpu",
        "claim_type": "AI / infrastructure",
        "short_label": "AI GPU / datacenter demand",
        "polarity": "bullish",
        "keywords": (
            "datacenter", "data center", "gpu", "accelerator", "inference chip",
            "enterprise gpu", "ai chip", "hbm", "nvlink", "server gpu",
        ),
        "supporting_terms": ("AI chip demand", "datacenter GPU", "enterprise GPU adoption"),
        "claim_template": "Users linked {ticker} to AI accelerator demand and enterprise/datacenter GPU adoption.",
    },
    {
        "id": "ai_lending",
        "claim_type": "AI / business model",
        "short_label": "AI lending automation",
        "polarity": "bullish",
        "keywords": (
            "ai lending", "lending automation", "loan approval", "underwriting ai",
            "fintech ai", "automated lending", "credit decision",
        ),
        "supporting_terms": ("AI lending", "automation", "loan approvals"),
        "claim_template": (
            "Users discussed {ticker} as a potential beneficiary of AI-driven lending automation and fintech efficiency."
        ),
    },
    {
        "id": "ai_software",
        "claim_type": "AI / business model",
        "short_label": "AI software monetization",
        "polarity": "bullish",
        "keywords": (
            "ai software", "saas ai", "copilot", "ai monetization", "subscription ai",
            "genai product", "ai platform revenue",
        ),
        "supporting_terms": ("AI software", "monetization", "platform revenue"),
        "claim_template": "Users tied {ticker} to AI software monetization and product adoption.",
    },
    {
        "id": "ai_capex",
        "claim_type": "AI / infrastructure",
        "short_label": "AI capex beneficiary",
        "polarity": "bullish",
        "keywords": (
            "ai capex", "capex cycle", "infrastructure spend", "cloud capex",
            "ai infrastructure", "buildout beneficiary",
        ),
        "supporting_terms": ("AI capex", "infrastructure spend"),
        "claim_template": "Users framed {ticker} as an AI infrastructure or capex-cycle beneficiary.",
    },
    {
        "id": "ai_productivity",
        "claim_type": "AI / business model",
        "short_label": "AI productivity / cost savings",
        "polarity": "bullish",
        "keywords": (
            "cost cutting ai", "productivity ai", "automation savings", "efficiency gains ai",
            "ai automation", "operating efficiency ai",
        ),
        "supporting_terms": ("AI productivity", "cost savings", "automation"),
        "claim_template": "Users discussed {ticker} in the context of AI-driven productivity or cost efficiency.",
    },
    {
        "id": "ai_hype_vague",
        "claim_type": "AI / business model",
        "short_label": "AI mentioned (impact unclear)",
        "polarity": "neutral",
        "keywords": (" ai ", "artificial intelligence", " ai play", " ai story"),
        "supporting_terms": ("AI",),
        "claim_template": "AI was mentioned around {ticker}, but the specific business impact was unclear.",
        "requires_no_specific": True,
    },
)

MA_BUYER_PATTERNS = (
    "acquiring", "acquires", " buys ", " bought ", "acquisition of", "takeover of",
    "purchasing", "deal to buy", "to acquire", "will acquire", "plans to acquire",
)
MA_TARGET_PATTERNS = (
    "being acquired", "buyout target", "takeover target", "getting bought",
    "could be bought", "acquisition target", "takeover bid", "buyout rumor",
    "potential target", "sale target",
)
MA_MERGER_PATTERNS = (
    "merging with", "merger with", "merger between", "merge with", "all-stock merger",
)
MA_CONFIRMED_PATTERNS = (
    "announced acquisition", "definitive agreement", "deal closed", "completed acquisition",
    "signed merger", "approved merger", "confirmed acquisition",
)
MA_VAGUE_PATTERNS = (
    " m&a ", " merger ", " acquisition ", " takeover ", " buyout ", " deal rumors",
)

OTHER_CLAIM_RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "earnings_beat_guidance",
        "claim_type": "Earnings / guidance",
        "short_label": "earnings beat / guidance raise",
        "polarity": "bullish",
        "keywords": ("earnings beat", "beat estimates", "guidance raise", "raised guidance", "eps beat"),
        "supporting_terms": ("earnings beat", "guidance raise"),
        "claim_template": "Users highlighted {ticker} after an earnings beat or guidance raise.",
    },
    {
        "id": "margin_expansion_earnings",
        "claim_type": "Earnings / margins",
        "short_label": "margin expansion after earnings",
        "polarity": "bullish",
        "keywords": ("margin expansion", "margin improvement", "higher margins", "gross margin up"),
        "supporting_terms": ("margin expansion", "earnings"),
        "claim_template": "Discussion emphasized margin expansion for {ticker} following recent results.",
    },
    {
        "id": "revenue_loan_growth",
        "claim_type": "Growth",
        "short_label": "consumer loan / revenue growth",
        "polarity": "bullish",
        "keywords": (
            "loan growth", "origination growth", "revenue growth", "member growth",
            "deposit growth", "top-line growth",
        ),
        "supporting_terms": ("loan growth", "revenue growth"),
        "claim_template": "Users pointed to loan or revenue growth as a driver for {ticker}.",
    },
    {
        "id": "short_squeeze",
        "claim_type": "Short interest",
        "short_label": "short squeeze setup",
        "polarity": "bullish",
        "keywords": ("short squeeze", "high short interest", "covering shorts", "si%"),
        "supporting_terms": ("short squeeze", "short interest"),
        "claim_template": "Users discussed {ticker} as a potential short-squeeze or high short-interest setup.",
    },
    {
        "id": "valuation_concern",
        "claim_type": "Valuation",
        "short_label": "valuation concern after rally",
        "polarity": "bearish",
        "keywords": (
            "overvalued", "too expensive", "valuation concern", "priced in", "rich multiple",
            "after rally", "too far too fast",
        ),
        "supporting_terms": ("valuation", "overvalued"),
        "claim_template": "Bearish comments questioned {ticker}'s valuation or how much is already priced in.",
    },
    {
        "id": "dilution",
        "claim_type": "Capital structure",
        "short_label": "dilution concern",
        "polarity": "bearish",
        "keywords": ("dilution", "secondary offering", "share offering", "atm offering", "stock offering"),
        "supporting_terms": ("dilution", "offering"),
        "claim_template": "Users raised dilution or secondary offering concerns for {ticker}.",
    },
    {
        "id": "execution_risk",
        "claim_type": "Execution",
        "short_label": "execution risk",
        "polarity": "bearish",
        "keywords": ("execution risk", "missed targets", "guidance cut", "lowered guidance", "earnings miss"),
        "supporting_terms": ("execution", "guidance cut"),
        "claim_template": "Comments flagged execution risk or disappointing guidance for {ticker}.",
    },
    {
        "id": "analyst_upgrade",
        "claim_type": "Analyst",
        "short_label": "analyst target upside",
        "polarity": "bullish",
        "keywords": ("price target raised", "analyst upgrade", "outperform", "overweight", "buy rating"),
        "supporting_terms": ("upgrade", "price target"),
        "claim_template": "Users cited analyst upgrades or higher price targets for {ticker}.",
    },
    {
        "id": "fda_biotech",
        "claim_type": "FDA / biotech",
        "short_label": "FDA / trial catalyst",
        "polarity": "bullish",
        "keywords": ("fda approval", "phase 3", "clinical trial", "pdufa", "trial data"),
        "supporting_terms": ("FDA", "trial"),
        "claim_template": "Discussion centered on FDA or clinical-trial catalysts for {ticker}.",
    },
)


def _normalize_text(*parts: Any) -> str:
    cleaned = f" {' '.join(str(part or '') for part in parts).lower()} "
    cleaned = re.sub(r"[^a-z0-9$%'\s/-]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned)


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text):
        token = token.strip("'")
        if len(token) < 2 or token in CUSTOM_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _is_low_value_phrase(phrase: str) -> bool:
    words = phrase.lower().split()
    if not words:
        return True
    if len(words) == 1 and words[0] in CUSTOM_STOPWORDS:
        return True
    return all(word in CUSTOM_STOPWORDS for word in words)


def extract_finance_phrases(text: str, *, ticker: str = "") -> list[str]:
    """Extract ranked finance-aware phrases (bigrams/trigrams + known phrases)."""

    normalized = _normalize_text(text)
    ticker_lower = ticker.lower()
    phrase_counts: Counter[str] = Counter()
    for phrase in KNOWN_FINANCE_PHRASES:
        if phrase in normalized:
            phrase_counts[phrase] += normalized.count(phrase) * FINANCE_PHRASE_BOOST
    tokens = [token for token in _tokenize(normalized) if token != ticker_lower]
    for index in range(len(tokens) - 1):
        bigram = f"{tokens[index]} {tokens[index + 1]}"
        if not _is_low_value_phrase(bigram):
            phrase_counts[bigram] += 1
    return [phrase for phrase, _ in phrase_counts.most_common(8) if not _is_low_value_phrase(phrase)]


def _collect_source_text(source: dict[str, Any]) -> str:
    return _normalize_text(
        source.get("title"),
        source.get("selftext"),
        source.get("comments_excerpt"),
    )


def _snippet(text: str, *, max_len: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def _confidence_label(score: float) -> str:
    if score >= 0.65:
        return "High"
    if score >= 0.4:
        return "Medium"
    return "Low"


def _phrase_negated(text: str, phrase: str) -> bool:
    """True when phrase appears after a simple negation (not / isn't / no)."""

    for match in re.finditer(re.escape(phrase), text):
        start = match.start()
        window = text[max(0, start - 12) : start]
        if re.search(r"\b(not|no|isn't|isnt|aren't|arent|without)\b", window):
            return True
    return False


def detect_ma_directionality(text: str, ticker: str) -> str:
    """
    Return M&A direction: acquirer, target, merger, confirmed, vague, unclear, or none.
    """

    normalized = _normalize_text(text)
    if not any(pattern in normalized for pattern in MA_VAGUE_PATTERNS + MA_BUYER_PATTERNS + MA_TARGET_PATTERNS):
        return "none"

    ticker_lower = ticker.lower()
    ticker_present = ticker_lower in normalized or f"${ticker_lower}" in normalized
    if not ticker_present:
        return "none"

    if any(p in normalized for p in MA_CONFIRMED_PATTERNS):
        if any(p in normalized for p in MA_BUYER_PATTERNS):
            return "confirmed_acquirer" if ticker_present else "confirmed"
        if any(p in normalized for p in MA_TARGET_PATTERNS):
            return "confirmed_target" if ticker_present else "confirmed"
        return "confirmed"

    buyer_hits = sum(1 for p in MA_BUYER_PATTERNS if p in normalized)
    target_hits = sum(1 for p in MA_TARGET_PATTERNS if p in normalized)
    merger_hits = sum(1 for p in MA_MERGER_PATTERNS if p in normalized)

    if merger_hits and ticker_present:
        return "merger_partner"
    if buyer_hits > target_hits and buyer_hits > 0:
        return "acquirer" if ticker_present else "acquirer_context"
    if target_hits > buyer_hits and target_hits > 0:
        return "target" if ticker_present else "target_context"
    if buyer_hits and target_hits:
        return "unclear"
    if any(p in normalized for p in MA_VAGUE_PATTERNS):
        return "vague" if ticker_present else "vague_context"
    return "unclear"


def _ma_claim_from_direction(ticker: str, direction: str) -> dict[str, Any] | None:
    mapping = {
        "acquirer": (
            "M&A / corporate",
            "possible acquirer speculation",
            "bullish",
            "beneficiary",
            f"Users speculated that {ticker} may acquire another company.",
        ),
        "target": (
            "M&A / corporate",
            "buyout target rumor",
            "bullish",
            "target",
            f"Users speculated that {ticker} could be an acquisition target.",
        ),
        "merger_partner": (
            "M&A / corporate",
            "merger partner speculation",
            "neutral",
            "merger",
            f"Users discussed a potential merger involving {ticker}.",
        ),
        "confirmed_acquirer": (
            "M&A / corporate",
            "confirmed acquirer",
            "bullish",
            "confirmed_buyer",
            f"Users discussed a confirmed or announced acquisition where {ticker} is the buyer.",
        ),
        "confirmed_target": (
            "M&A / corporate",
            "confirmed acquisition target",
            "bullish",
            "confirmed_target",
            f"Users discussed a confirmed acquisition involving {ticker} as the target.",
        ),
        "confirmed": (
            "M&A / corporate",
            "confirmed M&A deal",
            "bullish",
            "confirmed",
            f"Users discussed a confirmed acquisition involving {ticker}.",
        ),
        "vague": (
            "M&A / corporate",
            "M&A language (direction unclear)",
            "neutral",
            "unclear",
            "M&A terms appeared, but the discussion did not clearly establish whether "
            f"{ticker} is buyer or target.",
        ),
        "unclear": (
            "M&A / corporate",
            "M&A language (direction unclear)",
            "neutral",
            "unclear",
            "M&A language appeared, but direction was unclear.",
        ),
    }
    if direction not in mapping:
        return None
    claim_type, short_label, polarity, directionality, claim_text = mapping[direction]
    return {
        "claim_id": f"ma_{direction}",
        "claim_text": claim_text,
        "claim_type": claim_type,
        "directionality": directionality,
        "short_label": short_label,
        "polarity": polarity,
        "supporting_terms": ["M&A", "acquisition"],
    }


def _detect_ai_subtheme(text: str, *, specific_ids: set[str]) -> dict[str, Any] | None:
    """Pick the most specific AI subtheme supported by text."""

    best: dict[str, Any] | None = None
    best_score = 0
    for rule in AI_SUBTHEME_RULES:
        if rule.get("requires_no_specific") and specific_ids - {"ai_hype_vague"}:
            continue
        if rule["id"] == "ai_datacenter_gpu" and _phrase_negated(text, "datacenter"):
            continue
        hits = sum(1 for keyword in rule["keywords"] if keyword in text and not _phrase_negated(text, keyword.strip()))
        if hits > best_score:
            best_score = hits
            best = rule
    if best_score == 0:
        return None
    return best


def _rule_matches(text: str, rule: dict[str, Any]) -> bool:
    for keyword in rule["keywords"]:
        if keyword in text and not _phrase_negated(text, keyword.strip()):
            return True
    return False


def _claim_from_rule(ticker: str, rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": rule["id"],
        "claim_text": rule["claim_template"].format(ticker=ticker),
        "claim_type": rule["claim_type"],
        "directionality": rule.get("directionality", "neutral"),
        "short_label": rule["short_label"],
        "polarity": rule["polarity"],
        "supporting_terms": list(rule.get("supporting_terms", ())),
    }


def _detect_claims_for_source(ticker: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = _collect_source_text(source)
    claims: list[dict[str, Any]] = []
    specific_ai_ids: set[str] = set()

    for rule in AI_SUBTHEME_RULES:
        if rule.get("requires_no_specific"):
            continue
        if rule["id"] == "ai_datacenter_gpu" and _phrase_negated(text, "datacenter"):
            continue
        if _rule_matches(text, rule):
            specific_ai_ids.add(rule["id"])

    ai_rule = _detect_ai_subtheme(text, specific_ids=specific_ai_ids)
    if ai_rule:
        claims.append(_claim_from_rule(ticker, ai_rule))

    ma_dir = detect_ma_directionality(text, ticker)
    ma_claim = _ma_claim_from_direction(ticker, ma_dir)
    if ma_claim:
        claims.append(ma_claim)

    for rule in OTHER_CLAIM_RULES:
        if _rule_matches(text, rule):
            claims.append(_claim_from_rule(ticker, rule))

    return claims


def _aggregate_claims(
    ticker: str,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge per-source claim hits with evidence and confidence."""

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_indices": set(),
            "subreddits": set(),
            "snippets": [],
            "titles": [],
            "supporting_terms": Counter(),
        }
    )

    for index, source in enumerate(sources):
        subreddit = str(source.get("subreddit") or "unknown")
        title = str(source.get("title") or "").strip()
        snippet = _snippet(title) or _snippet(source.get("comments_excerpt") or source.get("selftext"))
        for claim in _detect_claims_for_source(ticker, source):
            key = claim["claim_id"]
            bucket = buckets[key]
            bucket.setdefault("claim", claim)
            bucket["source_indices"].add(index)
            bucket["subreddits"].add(subreddit)
            if snippet and snippet not in bucket["snippets"]:
                bucket["snippets"].append(snippet)
            if title and title not in bucket["titles"]:
                bucket["titles"].append(title)
            for term in claim.get("supporting_terms", []):
                bucket["supporting_terms"][term] += 1

    aggregated: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        base = dict(bucket["claim"])
        source_count = len(bucket["source_indices"])
        subreddit_count = len(bucket["subreddits"])
        directionality = base.get("directionality", "neutral")
        direction_clear = directionality not in {"unclear", "neutral", "vague"}

        score = 0.2
        score += min(0.35, source_count / 8)
        score += min(0.2, subreddit_count / 4 * 0.2)
        score += 0.1 if len(bucket["supporting_terms"]) >= 2 else 0.0
        if direction_clear:
            score += 0.12
        if base.get("claim_id") == "ai_hype_vague":
            score -= 0.15
        if "unclear" in str(base.get("claim_id", "")):
            score -= 0.1
        score = max(0.0, min(1.0, round(score, 4)))

        aggregated.append({
            **base,
            "source_count": source_count,
            "subreddit_count": subreddit_count,
            "confidence_score": score,
            "confidence_label": _confidence_label(score),
            "supporting_terms": [t for t, _ in bucket["supporting_terms"].most_common(5)],
            "evidence_snippets": bucket["snippets"][:3],
            "evidence_source_titles": bucket["titles"][:3],
            "evidence_subreddits": sorted(bucket["subreddits"])[:3],
        })

    aggregated.sort(key=lambda item: item["confidence_score"], reverse=True)
    return aggregated


def _ma_direction_summary(claims: list[dict[str, Any]]) -> str | None:
    ma_claims = [c for c in claims if c.get("claim_type") == "M&A / corporate"]
    if not ma_claims:
        return None
    directions = {c.get("directionality") for c in ma_claims}
    labels = []
    if "beneficiary" in directions or "confirmed_buyer" in directions or "acquirer" in directions:
        labels.append("possible acquirer")
    if "target" in directions or "confirmed_target" in directions:
        labels.append("possible target")
    if "merger" in directions:
        labels.append("merger partner")
    if "unclear" in directions or not labels:
        labels.append("unclear")
    return " / ".join(dict.fromkeys(labels))


def _compose_primary_claim(ticker: str, claims: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not claims:
        return None
    # Prefer highest-confidence non-vague AI over generic hype
    for claim in claims:
        if claim.get("claim_id") != "ai_hype_vague":
            return claim
    return claims[0]


def _narrative_confidence_from_claims(
    claims: list[dict[str, Any]],
    *,
    source_count: int,
    unique_subreddits: int,
    meme_share: float,
) -> tuple[str, float]:
    if not claims or source_count < 1:
        return "LOW", 0.0
    top = claims[0]["confidence_score"]
    score = top * 0.6 + min(0.25, source_count / 12) + min(0.15, unique_subreddits / 5 * 0.15)
    if meme_share >= 0.5:
        score -= 0.15
    if any(c.get("claim_id") == "ai_hype_vague" for c in claims[:2]):
        score -= 0.08
    score = max(0.0, min(1.0, round(score, 4)))
    if score >= 0.65:
        return "HIGH", score
    if score >= 0.4:
        return "MEDIUM", score
    return "LOW", score


def extract_ticker_narrative(
    ticker: str,
    sources: list[dict[str, Any]],
    *,
    post_types: list[str] | None = None,
    unique_subreddits: int = 0,
) -> dict[str, Any]:
    """Extract ticker-specific claims and narrative confidence from Reddit text."""

    empty = {
        "primary_narrative": FALLBACK_NARRATIVE,
        "primary_claim": None,
        "bullish_themes": [],
        "bearish_themes": [],
        "neutral_themes": [],
        "bullish_claims": [],
        "bearish_claims": [],
        "claims": [],
        "ma_direction": None,
        "narrative_confidence": "LOW",
        "narrative_confidence_score": 0.0,
        "narrative_keywords": [],
        "narrative_sources_count": 0,
        "evidence_snippets": [],
        "evidence_source_titles": [],
        "evidence_subreddits": [],
    }

    if not sources:
        return empty

    claims = _aggregate_claims(ticker, sources)
    if not claims:
        combined = "".join(_collect_source_text(s) for s in sources)
        keywords = extract_finance_phrases(combined, ticker=ticker)
        return {**empty, "narrative_keywords": keywords, "narrative_sources_count": len(sources)}

    primary = _compose_primary_claim(ticker, claims)
    primary_claim = dict(primary) if primary else None
    primary_narrative = primary["claim_text"] if primary else FALLBACK_NARRATIVE

    bullish_claims = [c for c in claims if c.get("polarity") == "bullish"]
    bearish_claims = [c for c in claims if c.get("polarity") == "bearish"]
    neutral_claims = [c for c in claims if c.get("polarity") == "neutral"]

    bullish_themes = [c["short_label"] for c in bullish_claims[:4]]
    bearish_themes = [c["short_label"] for c in bearish_claims[:3]]
    neutral_themes = [c["short_label"] for c in neutral_claims[:3]]

    post_types = post_types or []
    meme_share = 0.0
    if post_types:
        meme_share = sum(1 for item in post_types if item in {"Meme", "YOLO"}) / len(post_types)

    conf_label, conf_score = _narrative_confidence_from_claims(
        claims,
        source_count=len(sources),
        unique_subreddits=unique_subreddits,
        meme_share=meme_share,
    )

    combined = "".join(_collect_source_text(s) for s in sources)
    keywords = extract_finance_phrases(combined, ticker=ticker)

    evidence_snippets = primary.get("evidence_snippets", []) if primary else []
    evidence_titles = primary.get("evidence_source_titles", []) if primary else []
    evidence_subs = primary.get("evidence_subreddits", []) if primary else []

    return {
        "primary_narrative": primary_narrative,
        "primary_claim": primary_claim,
        "bullish_themes": bullish_themes,
        "bearish_themes": bearish_themes,
        "neutral_themes": neutral_themes,
        "bullish_claims": bullish_claims[:4],
        "bearish_claims": bearish_claims[:3],
        "claims": claims,
        "ma_direction": _ma_direction_summary(claims),
        "narrative_confidence": conf_label,
        "narrative_confidence_score": conf_score,
        "narrative_keywords": keywords,
        "narrative_sources_count": len(sources),
        "evidence_snippets": evidence_snippets,
        "evidence_source_titles": evidence_titles,
        "evidence_subreddits": evidence_subs,
    }


def build_narrative_summary(
    ticker: str,
    narrative: dict[str, Any],
    *,
    attention_phrase: str,
    quality_phrase: str,
    market_phrase: str,
    street_phrase: str = "",
) -> str:
    """Combine extracted claims with attention and market context."""

    primary = narrative.get("primary_claim") or {}
    primary_text = str(
        primary.get("claim_text") or narrative.get("primary_narrative") or FALLBACK_NARRATIVE
    )
    if primary_text == FALLBACK_NARRATIVE:
        return (
            f"{ticker} mention activity {attention_phrase}, but {primary_text.lower()} "
            f"{quality_phrase} {market_phrase}{street_phrase}"
        ).strip()

    focus = primary_text
    if focus.lower().startswith("users "):
        focus_clause = focus[6:].rstrip(".")
    else:
        focus_clause = focus.rstrip(".")

    ma_direction = narrative.get("ma_direction")
    ma_note = ""
    if ma_direction:
        ma_note = (
            f" Some comments referenced M&A ({ma_direction}); treat that as weaker evidence "
            "unless direction is confirmed."
        )
        if "unclear" in ma_direction:
            ma_note = (
                " Some comments referenced M&A, but the direction was unclear, "
                "so this should be treated as weak evidence."
            )

    bearish = narrative.get("bearish_claims") or narrative.get("bearish_themes") or []
    caution = ""
    if bearish:
        labels = [
            b.get("short_label") if isinstance(b, dict) else str(b) for b in bearish[:2]
        ]
        caution = f" Bearish pushback focused on {', '.join(labels)}."

    return (
        f"{ticker} discussion {attention_phrase} as users debated {focus_clause}, {quality_phrase}."
        f"{ma_note} {market_phrase}{street_phrase}{caution}"
    ).strip()
