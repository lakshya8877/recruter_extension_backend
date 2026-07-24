import os
import re
import requests
from collections import OrderedDict
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

# ── In-memory cache (last 10 lookups) ───────────────────────────────────

_cache: OrderedDict[str, dict] = OrderedDict()
CACHE_MAX = 10


class LookupRequest(BaseModel):
    company: str


class LookupResponse(BaseModel):
    summary: str
    details: Dict[str, str]
    source: str
    link: Optional[str] = None
    cached: bool = False


# ── Link extraction ─────────────────────────────────────────────────────


_AGGREGATOR_DOMAINS = {
    "linkedin.com", "leadiq.com", "crunchbase.com", "owler.com",
    "tracxn.com", "zoominfo.com", "pitchbook.com", "cbinsights.com",
    "getlatka.com", "bitscale.ai", "checkthat.ai", "g2.com",
    "trustradius.com", "glassdoor.com", "indeed.com", "wikipedia.org",
}


def _pick_best_link(results: list[dict], company: str) -> Optional[str]:
    """Prefer official company domain over aggregator/profile sites."""
    company_slug = re.sub(r"[^a-z0-9]", "", company.lower())

    official = None
    fallback = None

    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        domain = _extract_domain(url)
        if not domain:
            continue

        # Skip aggregators unless no other option
        if any(agg in domain for agg in _AGGREGATOR_DOMAINS):
            if not fallback:
                fallback = url
            continue

        # Strong signal: company name appears in the domain
        if company_slug in domain.replace("-", "").replace(".", ""):
            official = url
            break

        # Moderate signal: short, clean domain (likely official)
        if not official and domain.count(".") <= 2 and "/" not in url.rstrip("/"):
            official = url

    return official or fallback or (results[0].get("url") if results else None)


def _extract_domain(url: str) -> str:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return m.group(1).lower() if m else ""


# ── Tavily (primary) ───────────────────────────────────────────────────


def search_tavily(company: str) -> Tuple[Optional[str], Dict[str, str], Optional[str]]:
    if not TAVILY_API_KEY:
        return None, {}, None

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": (
            f'"{company}" India company overview founded year employees '
            f"revenue funding headquarters CEO industry clients"
        ),
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": 10,
    }
    try:
        r = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()

        results = data.get("results", [])
        link = _pick_best_link(results, company)
        answer = data.get("answer", "")

        if answer:
            summary, details = _split_answer(answer)
            return summary, details, link

        if results:
            combined = " ".join(
                r.get("content", "") for r in results[:3] if r.get("content")
            )[:600]
            if combined.strip():
                summary, details = _split_answer(combined)
                return summary, details, link
    except Exception:
        pass
    return None, {}, None


# ── Answer parsing ──────────────────────────────────────────────────────


def _split_answer(text: str) -> Tuple[str, Dict[str, str]]:
    details: Dict[str, str] = {}

    # Founding year
    m = re.search(r"(?:founded|established|launched)\s*(?:in)?\s*(\d{4})", text, re.I)
    details["founding_year"] = m.group(1) if m else "Not found"

    # Headquarters
    m = re.search(
        r"(?:headquartered|based|located)\s*(?:in|at)?\s*([A-Z][a-zA-Z\s]+?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)(?:\.|,|\s+with|\s+and|\s+It|\s+The|$)",
        text, re.I,
    )
    hq = m.group(1).strip().rstrip(",") if m else ""
    # Filter out blended/multi-location noise
    countries = re.findall(r"\b(India|USA|UK|China|Brazil|Germany|France|Japan|Canada|Australia|Singapore|UAE|Nigeria|Kenya)\b", hq, re.I)
    cities = re.findall(r"\b([A-Z][a-z]+(?:pur|bad|garh|abad|giri|patnam|nagar)?)\b", hq)
    details["headquarters"] = hq if hq and len(countries) < 2 and len(cities) < 3 and len(hq) <= 60 else "Not found"

    # Employees / size
    m = re.search(
        r"(?:with\s+)?(?:over|about|around|approximately)?\s*([\d,]+(?:[–-][\d,]+)?)\s*(?:employees|staff|people|team members|workers)",
        text, re.I,
    )
    if m:
        details["size"] = m.group(1).replace(",", "") + " employees"
    else:
        m = re.search(r"(\d+[-–]\d+)\s*employees", text, re.I)
        details["size"] = m.group(1) + " employees" if m else "Not found"

    # ── Unified dollar-amount extraction (revenue + funding) ──────

    # Find all "$X unit" patterns with surrounding context
    dollar_hits = []
    for m in re.finditer(r"\$?([\d.]+)\s*(million|billion|thousand|[MBTK])\b", text, re.I):
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 40)
        ctx = text[start:end]
        dollar_hits.append((m.group(1), m.group(2), ctx))

    # Classify hits as revenue or funding based on nearby keywords
    details["revenue"] = "Not found"
    details["last_funding"] = "Not found"

    for num, unit, ctx in dollar_hits:
        # Skip amounts that are user/client counts, not money
        if re.search(r"\b(?:users|clients|customers|members|subscribers)\b", ctx, re.I):
            continue
        val = _clean_dollar(num + " " + unit)
        is_funding = bool(re.search(r"\b(?:funding|raised|secured|investment|investors|series [a-e]|seed|round)\b", ctx, re.I))
        is_revenue = bool(re.search(r"\b(?:revenue|sales|ARR|annual|income|turnover)\b", ctx, re.I))

        if is_funding and details["last_funding"] == "Not found":
            details["last_funding"] = val
        elif is_revenue and details["revenue"] == "Not found":
            details["revenue"] = val
        elif not is_funding and not is_revenue:
            # Unclear — check broader context: "in funding" vs "in revenue"
            if "funding" in ctx.lower():
                if details["last_funding"] == "Not found":
                    details["last_funding"] = val
            elif details["last_funding"] == "Not found":
                details["last_funding"] = val  # default to funding

    # Bootstrapped fallback
    if details["last_funding"] == "Not found" and re.search(r"bootstrapp|self.funded|no (?:external )?funding", text, re.I):
        details["last_funding"] = "Bootstrapped"

    # ── CEO / Leadership ──────────────────────────────────────────
    m = re.search(
        r"(?:CEO\s*(?:is|:)?|led by\s*(?:CEO\s*)?|founded by)\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})",
        text, re.I,
    )
    if not m:
        m = re.search(
            r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\s*(?:is the|serves as|,)\s*CEO",
            text, re.I,
        )
    details["leadership"] = m.group(1).strip() if m else "Not found"

    # ── Industry ──────────────────────────────────────────────────
    # Try explicit mentions first
    m = re.search(
        r"(?:industry|sector|operates in)\s*(?:is|:)?\s*(?:the)?\s*([a-zA-Z\s&]{3,40}?)(?:\.|,|\s+and|\s+with|\s+headquartered|\s+It|$)",
        text, re.I,
    )
    if not m:
        # Fallback: "is a/an/the [X] company/firm/platform"
        m = re.search(
            r"(?:is\s+)?(?:a|an|the)\s+([a-z]+(?:\s[a-z]+){0,2})\s+(?:company|firm|platform|startup|business)",
            text, re.I,
        )
    if not m:
        # Last resort: "is a [X], " pattern
        m = re.search(r"is an?\s+([a-z]+(?:\s[a-z]+){0,2}),", text, re.I)
    details["industry"] = m.group(1).strip() if m else "Not found"

    # ── Clients ───────────────────────────────────────────────────
    m = re.search(
        r"([\d,.]+(?:\s*[MBK]illion)?)\s*(?:active|paying|registered|daily)?\s*(?:clients|customers|users)",
        text, re.I,
    )
    if not m:
        m = re.search(
            r"(?:clients|customers|users)(?:\s*(?:include|of|:))?\s*(?:over|about|more than)?\s*([\d,.]+(?:\s*[MBK]illion)?)",
            text, re.I,
        )
    details["clients"] = m.group(1).strip() if m else "Not found"

    return text.strip(), details


def _clean_dollar(val: str) -> str:
    """Normalize '120 million' → '$120M', '60K' → '$60K', strip trailing noise."""
    val = val.strip().rstrip(",")
    val = re.sub(r"\s+(?:in\b.*|to\s+date.*|total.*|funding.*|as\s+of.*)", "", val, flags=re.I)
    val = re.sub(r"\s*million", "M", val, flags=re.I)
    val = re.sub(r"\s*billion", "B", val, flags=re.I)
    val = re.sub(r"\s*thousand", "K", val, flags=re.I)
    if not val.startswith("$"):
        val = "$" + val
    return val


# ── Serper (fallback) ──────────────────────────────────────────────────


def search_serper(company: str) -> Tuple[Optional[str], Dict[str, str], Optional[str]]:
    if not SERPER_API_KEY:
        return None, {}, None

    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": f'"{company}" India company overview founded employees revenue', "num": 10}
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            json=payload, headers=headers, timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        kg = data.get("knowledgeGraph", {})
        organic = data.get("organic", [])

        link = kg.get("websiteUrl") or kg.get("website")
        if not link and organic:
            link = _pick_best_link(organic, company)

        parts = []
        if kg.get("description"):
            parts.append(kg["description"])
        for item in organic[:3]:
            s = item.get("snippet", "")
            if s:
                parts.append(s)

        summary = " | ".join(parts)[:600] if parts else None

        details: Dict[str, str] = {}
        if kg.get("type"):
            details["industry"] = kg["type"]
        if kg.get("employeeCount"):
            details["size"] = f"{kg['employeeCount']} employees"

        return summary, details, link
    except Exception:
        pass
    return None, {}, None


# ── Routes ─────────────────────────────────────────────────────────────


@app.post("/lookup", response_model=LookupResponse)
def lookup(req: LookupRequest):
    company = req.company.strip().lower()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    # Cache hit?
    if company in _cache:
        cached = _cache[company]
        return LookupResponse(
            summary=cached["summary"],
            details=cached["details"],
            source=cached["source"],
            link=cached.get("link"),
            cached=True,
        )

    summary, details, link = search_tavily(company)
    if summary:
        _add_to_cache(company, summary, details, link, "tavily")
        return LookupResponse(
            summary=summary, details=details, source="tavily", link=link, cached=False,
        )

    summary, details, link = search_serper(company)
    if summary:
        _add_to_cache(company, summary, details, link, "serper")
        return LookupResponse(
            summary=summary, details=details, source="serper", link=link, cached=False,
        )

    raise HTTPException(
        status_code=404,
        detail=f"No information found for '{company}'.",
    )


def _add_to_cache(company: str, summary: str, details: dict, link: Optional[str], source: str):
    if company in _cache:
        del _cache[company]
    elif len(_cache) >= CACHE_MAX:
        _cache.popitem(last=False)
    _cache[company] = {
        "summary": summary,
        "details": details,
        "link": link,
        "source": source,
    }


@app.get("/health")
def health():
    return {"status": "ok"}
