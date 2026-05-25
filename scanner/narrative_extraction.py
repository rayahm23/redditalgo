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

# Corporate M&A requires strong keywords — "buy/bought/deal/target" alone are insufficient.
STRONG_MNA_PHRASES: tuple[str, ...] = (
    "acquisition",
    "acquire",
    "acquired",
    "acquiring",
    "merger",
    "takeover",
    "buyout",
    "tender offer",
    "strategic buyer",
    "deal to acquire",
    "all-stock deal",
    "cash-and-stock deal",
    "merger agreement",
    "antitrust approval",
    "acquisition of",
    "merger with",
    "merger between",
    "buyout target",
    "takeover target",
    "being acquired",
    "getting bought",
    "acquisition target",
    "announced acquisition",
    "definitive agreement",
    "merger partner",
)

MNA_DENIAL_PHRASES: tuple[str, ...] = (
    "no acquisition",
    "not an acquisition",
    "no buyout",
    "fake buyout",
    "buyout rumor was denied",
    "acquisition rumor was denied",
    "rumor was denied",
    "not acquiring",
    "no merger",
    "denied acquisition",
    "denied the rumor",
)

MNA_SPECULATIVE_MARKERS: tuple[str, ...] = (
    "rumor",
    "speculation",
    "speculated",
    "could ",
    " may ",
    " might ",
    "possible",
    "potentially",
)

MNA_CONFIRMED_MARKERS: tuple[str, ...] = (
    "announced",
    "confirmed",
    "signed agreement",
    "definitive agreement",
    "completed acquisition",
    "deal closed",
    "approved merger",
)

TRADING_BUY_CLAIM_RULE: dict[str, Any] = {
    "id": "bullish_trading_interest",
    "claim_type": "Retail flow",
    "short_label": "bullish trading interest",
    "polarity": "bullish",
    "claim_template": "Users showed bullish trading interest in {ticker}, without clear corporate M&A discussion.",
    "supporting_terms": ("buy", "long", "calls"),
}

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


def _ticker_in_text(text: str, ticker: str) -> bool:
    symbol = ticker.lower()
    return symbol in text or f"${symbol}" in text


def _has_strong_mna_keyword(text: str) -> bool:
    for phrase in STRONG_MNA_PHRASES:
        if phrase in text and not _phrase_negated(text, phrase.strip()):
            return True
    return False


def _mna_denied(text: str) -> bool:
    return any(phrase in text for phrase in MNA_DENIAL_PHRASES)


def _mna_certainty_label(text: str) -> str | None:
    if any(marker in text for marker in MNA_CONFIRMED_MARKERS):
        return "confirmed"
    if any(marker in text for marker in MNA_SPECULATIVE_MARKERS):
        return "speculative"
    return None


def _matches_trading_buy_patterns(text: str, ticker: str) -> bool:
    normalized = _normalize_text(text)
    if not _ticker_in_text(normalized, ticker):
        return False
    symbol = re.escape(ticker.lower())
    patterns = (
        rf"\b(?:should\s+i\s+)?(?:buy|buying|bought)\s+\$?{symbol}\b",
        rf"\b(?:buy|buying|bought)\s+\$?{symbol}\s+instead\b",
        rf"\b{symbol}\s+is\s+a\s+buy\b",
        rf"\bbuy\s+{symbol}\s+or\b",
        rf"\b(?:buy|buying)\s+(?:the\s+)?dip\b",
        rf"\bbought\s+calls\b",
        rf"\bbuy\s+calls\b",
        rf"\bbuy\s+shares\b",
        rf"\bloading\s+up\b",
        rf"\badding\s+shares\b",
        rf"\blong\s+this\s+stock\b",
        rf"\bcalls\s+on\s+\$?{symbol}\b",
        rf"\b(?:i'm|im|i\s+am)\s+buying\s+\$?{symbol}\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def detect_trading_buy_intent(text: str, ticker: str) -> bool:
    """Detect retail trading-buy language (not corporate M&A)."""

    normalized = _normalize_text(text)
    if not _matches_trading_buy_patterns(text, ticker):
        return False
    if _has_strong_mna_keyword(normalized) and not _mna_denied(normalized):
        if _corporate_mna_direction(normalized, ticker) != "none":
            return False
    return True


def _corporate_mna_direction(text: str, ticker: str) -> str:
    """Classify corporate M&A direction when strong keywords are present."""

    normalized = _normalize_text(text)
    symbol = re.escape(ticker.lower())
    ticker_present = _ticker_in_text(normalized, ticker)

    merger_patterns = (
        rf"\b{symbol}\s+merging\s+with\b",
        r"\bmerger\s+with\b",
        r"\bmerger\s+between\b",
        r"\bmerging\s+with\b",
        r"\ball-stock\s+merger\b",
    )
    if ticker_present and any(re.search(pattern, normalized) for pattern in merger_patterns):
        return "merger"

    target_patterns = (
        rf"\b{symbol}\s+could\s+be\s+acquired\b",
        rf"\b{symbol}\s+is\s+a\s+buyout\s+target\b",
        rf"\b{symbol}\s+is\s+an\s+acquisition\s+target\b",
        r"\bbuyout\s+target\b",
        r"\btakeover\s+target\b",
        r"\bbeing\s+acquired\b",
        r"\bgetting\s+bought\b",
        r"\bacquisition\s+target\b",
        r"\btakeover\s+bid\b",
        r"\bmay\s+acquire\s+\$?" + symbol,
        r"\bsomeone\s+(?:may|might|could)\s+acquire\s+\$?" + symbol,
        r"\bshould\s+acquire\s+\$?" + symbol,
    )
    if ticker_present and any(re.search(pattern, normalized) for pattern in target_patterns):
        return "target"

    acquirer_patterns = (
        rf"\b{symbol}\s+is\s+acquiring\b",
        rf"\b{symbol}\s+acquiring\b",
        rf"\b{symbol}\s+announced\s+acquisition\b",
        rf"\b{symbol}\s+(?:will|plans\s+to)\s+acquire\b",
        r"\bacquisition\s+of\b",
        r"\bdeal\s+to\s+acquire\b",
        r"\btakeover\s+of\b",
        r"\bto\s+acquire\b",
        rf"\b{symbol}\s+buys\b",
        rf"\b{symbol}\s+bought\b",
    )
    if ticker_present and any(re.search(pattern, normalized) for pattern in acquirer_patterns):
        # "buys/bought" only counts as acquirer alongside explicit M&A nouns.
        if re.search(rf"\b{symbol}\s+buys?\b", normalized):
            if not re.search(r"\b(acquir|acquisition|merger|takeover|buyout)\w*\b", normalized):
                return "unclear"
        return "acquirer"

    if ticker_present and _has_strong_mna_keyword(normalized):
        return "unclear"
    return "none"


def analyze_corporate_mna(text: str, ticker: str) -> dict[str, Any]:
    """
    Analyze corporate M&A intent separately from trading-buy language.

    Returns mna_detected, mna_direction, mna_certainty, mna_status, and evidence snippet.
    """

    normalized = _normalize_text(text)
    empty = {
        "mna_detected": False,
        "mna_direction": None,
        "mna_certainty": None,
        "mna_status": "none",
        "mna_evidence_snippet": None,
        "mna_confidence_score": 0.0,
        "corporate_mna_intent": False,
        "trading_buy_intent": _matches_trading_buy_patterns(text, ticker),
    }

    if not _has_strong_mna_keyword(normalized):
        return {**empty, "trading_buy_intent": detect_trading_buy_intent(text, ticker)}

    if not _ticker_in_text(normalized, ticker):
        return empty

    snippet_source = text.strip()
    certainty = _mna_certainty_label(normalized)
    if _mna_denied(normalized):
        return {
            **empty,
            "mna_detected": True,
            "mna_direction": _corporate_mna_direction(normalized, ticker) or "unclear",
            "mna_certainty": certainty,
            "mna_status": "denied_or_negated",
            "mna_evidence_snippet": _snippet(snippet_source),
            "corporate_mna_intent": False,
        }

    direction = _corporate_mna_direction(normalized, ticker)
    if direction == "none":
        return empty

    confidence = 0.45
    if certainty == "confirmed":
        confidence += 0.25
    elif certainty == "speculative":
        confidence += 0.1
    if direction in {"acquirer", "target", "merger"}:
        confidence += 0.15
    confidence = round(min(1.0, confidence), 4)

    return {
        "mna_detected": True,
        "mna_direction": direction,
        "mna_certainty": certainty or "speculative",
        "mna_status": "active",
        "mna_evidence_snippet": _snippet(snippet_source),
        "mna_confidence_score": confidence,
        "corporate_mna_intent": True,
        "trading_buy_intent": False,
    }


def detect_ma_directionality(text: str, ticker: str) -> str:
    """Backward-compatible direction string for tests and legacy callers."""

    analysis = analyze_corporate_mna(text, ticker)
    if not analysis.get("mna_detected") or analysis.get("mna_status") == "denied_or_negated":
        return "none"
    direction = str(analysis.get("mna_direction") or "unclear")
    certainty = analysis.get("mna_certainty")
    if certainty == "confirmed":
        if direction == "acquirer":
            return "confirmed_acquirer"
        if direction == "target":
            return "confirmed_target"
        return "confirmed"
    if direction == "merger":
        return "merger_partner"
    if direction == "acquirer":
        return "acquirer"
    if direction == "target":
        return "target"
    return "unclear"


def _ma_claim_from_analysis(ticker: str, analysis: dict[str, Any]) -> dict[str, Any] | None:
    if not analysis.get("corporate_mna_intent"):
        return None

    direction = str(analysis.get("mna_direction") or "unclear")
    certainty = str(analysis.get("mna_certainty") or "speculative")
    direction_key = direction
    if certainty == "confirmed":
        if direction == "acquirer":
            direction_key = "confirmed_acquirer"
        elif direction == "target":
            direction_key = "confirmed_target"
        else:
            direction_key = "confirmed"

    mapping = {
        "acquirer": (
            "possible acquirer speculation",
            "bullish",
            "acquirer",
            f"Users speculated that {ticker} may acquire another company.",
        ),
        "target": (
            "buyout target rumor",
            "bullish",
            "target",
            f"Users speculated that {ticker} could be an acquisition target.",
        ),
        "merger": (
            "merger partner speculation",
            "neutral",
            "merger",
            f"Users discussed a potential merger involving {ticker}.",
        ),
        "confirmed_acquirer": (
            "confirmed acquirer",
            "bullish",
            "confirmed_buyer",
            f"Users discussed a confirmed or announced acquisition where {ticker} is the buyer.",
        ),
        "confirmed_target": (
            "confirmed acquisition target",
            "bullish",
            "confirmed_target",
            f"Users discussed a confirmed acquisition involving {ticker} as the target.",
        ),
        "confirmed": (
            "confirmed M&A deal",
            "bullish",
            "confirmed",
            f"Users discussed a confirmed acquisition involving {ticker}.",
        ),
        "unclear": (
            "M&A language (direction unclear)",
            "neutral",
            "unclear",
            "M&A language appeared, but posts did not clearly identify whether the company was buyer or target.",
        ),
    }
    entry = mapping.get(direction_key) or mapping["unclear"]
    short_label, polarity, directionality, claim_text = entry
    if certainty == "speculative" and direction_key in {"target", "acquirer", "unclear"}:
        claim_text = claim_text.replace("speculated", "speculated (mostly rumor-based)")
        if "rumor" not in claim_text.lower():
            claim_text = claim_text.rstrip(".") + ", but evidence was limited and mostly rumor-based."

    return {
        "claim_id": f"ma_{direction_key}",
        "claim_text": claim_text,
        "claim_type": "M&A / corporate",
        "directionality": directionality,
        "short_label": short_label,
        "polarity": polarity,
        "supporting_terms": ["M&A", "acquisition"],
        "mna_certainty": certainty,
        "mna_status": analysis.get("mna_status"),
    }


def _ma_claim_from_direction(ticker: str, direction: str) -> dict[str, Any] | None:
    """Legacy wrapper — build claim from direction string via analyze_corporate_mna heuristics."""

    if direction == "none":
        return None
    analysis = {
        "corporate_mna_intent": True,
        "mna_direction": direction.replace("merger_partner", "merger").replace("confirmed_", ""),
        "mna_certainty": "confirmed" if "confirmed" in direction else "speculative",
        "mna_status": "active",
    }
    if direction in {"vague", "unclear"}:
        analysis["mna_direction"] = "unclear"
    if direction == "merger_partner":
        analysis["mna_direction"] = "merger"
    if direction == "confirmed_acquirer":
        analysis["mna_direction"] = "acquirer"
        analysis["mna_certainty"] = "confirmed"
    if direction == "confirmed_target":
        analysis["mna_direction"] = "target"
        analysis["mna_certainty"] = "confirmed"
    return _ma_claim_from_analysis(ticker, analysis)


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

    mna_analysis = analyze_corporate_mna(text, ticker)
    if mna_analysis.get("corporate_mna_intent"):
        ma_claim = _ma_claim_from_analysis(ticker, mna_analysis)
        if ma_claim:
            claims.append(ma_claim)
    elif detect_trading_buy_intent(text, ticker):
        claims.append(_claim_from_rule(ticker, TRADING_BUY_CLAIM_RULE))

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


def _aggregate_intent_metrics(ticker: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate trading-buy vs corporate M&A signals across sources."""

    trading_buy_mentions_count = 0
    corporate_mna_mentions_count = 0
    mna_snippets: list[str] = []
    best_mna: dict[str, Any] | None = None

    for source in sources:
        text = _collect_source_text(source)
        if detect_trading_buy_intent(text, ticker):
            trading_buy_mentions_count += 1
        analysis = analyze_corporate_mna(text, ticker)
        if analysis.get("mna_detected"):
            corporate_mna_mentions_count += 1
        if analysis.get("corporate_mna_intent"):
            snippet = analysis.get("mna_evidence_snippet")
            if snippet and snippet not in mna_snippets:
                mna_snippets.append(str(snippet))
            if best_mna is None or float(analysis.get("mna_confidence_score") or 0) > float(
                best_mna.get("mna_confidence_score") or 0
            ):
                best_mna = analysis

    if best_mna:
        return {
            "trading_buy_mentions_count": trading_buy_mentions_count,
            "corporate_mna_mentions_count": corporate_mna_mentions_count,
            "mna_detected": True,
            "mna_direction": best_mna.get("mna_direction"),
            "mna_certainty": best_mna.get("mna_certainty"),
            "mna_status": best_mna.get("mna_status"),
            "mna_evidence_snippets": mna_snippets[:3],
            "mna_confidence_score": best_mna.get("mna_confidence_score"),
        }

    return {
        "trading_buy_mentions_count": trading_buy_mentions_count,
        "corporate_mna_mentions_count": corporate_mna_mentions_count,
        "mna_detected": corporate_mna_mentions_count > 0,
        "mna_direction": None,
        "mna_certainty": None,
        "mna_status": "none",
        "mna_evidence_snippets": [],
        "mna_confidence_score": 0.0,
    }


def _ma_direction_summary(claims: list[dict[str, Any]], *, mna_metrics: dict[str, Any] | None = None) -> str | None:
    metrics = mna_metrics or {}
    direction = metrics.get("mna_direction")
    if metrics.get("mna_detected") and direction:
        labels = []
        if direction == "acquirer":
            labels.append("possible acquirer")
        elif direction == "target":
            labels.append("possible target")
        elif direction == "merger":
            labels.append("merger partner")
        else:
            labels.append("unclear")
        if metrics.get("mna_certainty") == "speculative":
            labels.append("rumor-based")
        return " / ".join(labels)

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
        "trading_buy_mentions_count": 0,
        "corporate_mna_mentions_count": 0,
        "mna_detected": False,
        "mna_direction": None,
        "mna_certainty": None,
        "mna_status": "none",
        "mna_evidence_snippets": [],
        "mna_confidence_score": 0.0,
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

    intent_metrics = _aggregate_intent_metrics(ticker, sources)
    claims = _aggregate_claims(ticker, sources)
    if not claims:
        combined = "".join(_collect_source_text(s) for s in sources)
        keywords = extract_finance_phrases(combined, ticker=ticker)
        return {
            **empty,
            **intent_metrics,
            "narrative_keywords": keywords,
            "narrative_sources_count": len(sources),
        }

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
        "ma_direction": _ma_direction_summary(claims, mna_metrics=intent_metrics),
        **intent_metrics,
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

    trading_count = int(narrative.get("trading_buy_mentions_count") or 0)
    mna_detected = narrative.get("mna_detected")
    ma_direction = narrative.get("ma_direction")
    mna_certainty = narrative.get("mna_certainty")
    ma_note = ""

    if mna_detected and ma_direction:
        if mna_certainty == "speculative":
            ma_note = (
                f" Users speculated about corporate M&A ({ma_direction}), "
                "but evidence was limited and mostly rumor-based."
            )
        elif "unclear" in str(ma_direction):
            ma_note = (
                " M&A language appeared, but posts did not clearly identify "
                "whether the company was buyer or target."
            )
        else:
            ma_note = (
                f" Some comments referenced corporate M&A ({ma_direction}); "
                "treat unconfirmed rumors cautiously."
            )
    elif trading_count > 0 and not mna_detected:
        ma_note = (
            " Users showed bullish trading interest, but there was no clear corporate M&A discussion."
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
