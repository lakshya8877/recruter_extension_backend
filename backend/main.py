import os
import re
import asyncio
from collections import OrderedDict
from typing import Optional, Dict, Tuple

import httpx
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
API_TIMEOUT = 4.0  # seconds

# ── Reusable HTTP client (survives across Vercel warm starts) ───────────

_http_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(API_TIMEOUT),
        )
    return _http_client


@app.on_event("shutdown")
async def _shutdown():
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None


# ── In-memory cache (last 10 lookups) ───────────────────────────────────

_cache: OrderedDict[str, dict] = OrderedDict()
CACHE_MAX = 10


# ── Precompiled regex patterns ──────────────────────────────────────────

# Founding year — added "created" (e.g. "Created in 2008")
RE_FOUNDING = re.compile(
    r"(?:founded|established|launched|started|created|incorporated)"
    r"\s*(?:in)?\s*(\d{4})",
    re.I,
)

# Employees
RE_EMPLOYEES = re.compile(
    r"(?:has|with|have|employs|employing)?\s*"
    r"(?:over|about|around|approximately|nearly|more than)?\s*"
    r"([\d,]+(?:[–-][\d,]+)?)\s*\+?\s*"
    r"(?:employees|staff|people|team members|workers)",
    re.I,
)
RE_EMPLOYEES_ALT = re.compile(r"(\d+[-–]\d+)\s*employees", re.I)

# Dollar amounts
RE_DOLLAR = re.compile(r"\$?([\d.]+)\s*(million|billion|thousand|[MBTK])\b", re.I)
RE_USERS_CTX = re.compile(r"\b(?:users|clients|customers|members|subscribers)\b", re.I)
RE_FUNDING_CTX = re.compile(
    r"\b(?:funding|raised|secured|investment|investors|"
    r"series [a-e]|seed|round|venture|capital)\b",
    re.I,
)
RE_REVENUE_CTX = re.compile(
    r"\b(?:revenue|sales|ARR|annual|income|turnover)\b", re.I
)
RE_BOOTSTRAPPED = re.compile(
    r"bootstrapp|self.funded|no (?:external )?funding", re.I
)

# CEO — uses inline (?i:…) for keywords, CASE-SENSITIVE name capture so
# "IIT", "API", etc. don't match as person names.
RE_CEO_PATTERNS = [
    re.compile(
        r"(?i:(?:CEO\s*(?:is|:)?|led by\s*(?:CEO\s*)?|Co-founder\s*&?\s*CEO))"
        r"\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})"
    ),
    re.compile(
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})"
        r"(?i:\s*(?:is the|serves as|,)\s*CEO)"
    ),
    re.compile(
        r"(?i:CEO\s+(?:of\s+\S+\s+)?(?:is\s+)?)"
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})"
    ),
    re.compile(
        r"(?i:Co-founder\s*(?:&|and)\s*CEO[,.]?\s*)"
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})"
    ),
    re.compile(
        r"(?i:(?:founded|co-founded)\s+by)\s+"
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3})"
    ),
]
RE_CEO_CLEAN = re.compile(
    r"\s+(?:leads?\s+the|and\s+raised|of\s+\S+\s+(?:is\s+)?).*", re.I
)

# Headquarters — requires preposition "in" / "at" to avoid matching
# "cloud-based software" or "based company" as HQ.
RE_HQ = re.compile(
    r"(?:headquartered|based|located)\s+(?:in|at)\s+"
    r"([A-Z][a-zA-Z\s]+?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)"
    r"(?:\.|,|\s+with|\s+and|\s+It|\s+The|\s+\d|$)",
    re.I,
)
RE_HQ_STRUCTURED = re.compile(
    r"(?:HQ|Headquarters)\s*[,:]\s*([A-Z][a-zA-Z\s,]+?)(?:\.|;|\s+\d|$)",
    re.I,
)

# Industry — includes "service|provider|enterprise" and has a blocklist
# for generic adjectives that shouldn't be industry names.
RE_INDUSTRY_PATTERNS = [
    re.compile(
        r"(?:Industry|Sector)\s*[,:]\s*([a-zA-Z\s&]{3,40}?)"
        r"(?:\.|,|\s+(?:and|with|headquartered|Number|Founded|Revenue|$))",
        re.I,
    ),
    re.compile(
        r"(?:industry|sector|operates in)\s*(?:is|:)?\s*(?:the)?\s*"
        r"([a-zA-Z\s&]{3,40}?)"
        r"(?:\.|,|\s+and|\s+with|\s+headquartered|\s+It|$)",
        re.I,
    ),
    re.compile(
        r"(?:is\s+)?(?:a|an|the)\s+"
        r"([a-z]+(?:\s[a-z]+){0,3})\s+"
        r"(?:company|firm|platform|startup|business|service|provider|enterprise)",
        re.I,
    ),
]
_INDUSTRY_BLOCKLIST = frozenset({
    "public", "private", "single", "large", "small", "leading", "global",
    "first", "major", "new", "other", "such", "biggest", "fastest",
    "largest", "top", "best", "premier", "prominent", "indian",
    "american", "multinational", "holding", "listed",
})

# Clients
RE_CLIENTS_PATTERNS = [
    re.compile(
        r"([\d,.]+(?:\s*[MBK](?:illion)?)?)\s*"
        r"(?:active|paying|registered|daily)?\s*"
        r"(?:clients|customers|users)",
        re.I,
    ),
    re.compile(
        r"(?:clients|customers|users)(?:\s*(?:include|of|:))?\s*"
        r"(?:over|about|more than)?\s*"
        r"([\d,.]+(?:\s*[MBK](?:illion)?)?)",
        re.I,
    ),
]

# Utilities
RE_DOMAIN = re.compile(r"https?://(?:www\.)?([^/]+)")
RE_DOLLAR_NOISE = re.compile(
    r"\s+(?:in\b.*|to\s+date.*|total.*|funding.*|as\s+of.*)", re.I
)
RE_SLUG_CLEAN = re.compile(r"[^a-z0-9]")
RE_HQ_COUNTRIES = re.compile(
    r"\b(India|USA|UK|China|Brazil|Germany|France|Japan|Canada|Australia|"
    r"Singapore|UAE|Nigeria|Kenya)\b",
    re.I,
)
RE_HQ_CITIES = re.compile(
    r"\b([A-Z][a-z]+(?:pur|bad|garh|abad|giri|patnam|nagar)?)\b"
)


# ── Models ──────────────────────────────────────────────────────────────


class LookupRequest(BaseModel):
    company: str


class LookupResponse(BaseModel):
    summary: str
    details: Dict[str, str]
    source: str
    link: Optional[str] = None
    cached: bool = False


# ── Aggregator domains ──────────────────────────────────────────────────

_AGGREGATOR_DOMAINS = {
    "linkedin.com", "leadiq.com", "crunchbase.com", "owler.com",
    "tracxn.com", "zoominfo.com", "pitchbook.com", "cbinsights.com",
    "getlatka.com", "bitscale.ai", "checkthat.ai", "g2.com",
    "trustradius.com", "glassdoor.com", "indeed.com", "wikipedia.org",
}


# ── Link extraction ─────────────────────────────────────────────────────


def _extract_domain(url: str) -> str:
    m = RE_DOMAIN.search(url)
    return m.group(1).lower() if m else ""


def _pick_best_link(results: list[dict], company: str) -> Optional[str]:
    """Prefer official company domain over aggregator/profile sites."""
    company_slug = RE_SLUG_CLEAN.sub("", company.lower())
    official = None
    fallback = None

    for r in results:
        url = r.get("url", "") or r.get("link", "")
        if not url:
            continue
        domain = _extract_domain(url)
        if not domain:
            continue

        if any(agg in domain for agg in _AGGREGATOR_DOMAINS):
            if not fallback:
                fallback = url
            continue

        if company_slug in domain.replace("-", "").replace(".", ""):
            return url

        if not official and domain.count(".") <= 2 and "/" not in url.rstrip("/"):
            official = url

    return official or fallback or (
        (results[0].get("url") or results[0].get("link")) if results else None
    )


# ── Answer parsing ──────────────────────────────────────────────────────


def _split_answer(text: str) -> Tuple[str, Dict[str, str]]:
    """Extract structured details from text using precompiled regex."""
    details: Dict[str, str] = {}

    # Founding year
    m = RE_FOUNDING.search(text)
    details["founding_year"] = m.group(1) if m else "Not found"

    # Employees / size
    m = RE_EMPLOYEES.search(text)
    if m:
        details["size"] = m.group(1).replace(",", "") + " employees"
    else:
        m = RE_EMPLOYEES_ALT.search(text)
        details["size"] = m.group(1) + " employees" if m else "Not found"

    # ── Dollar amounts (revenue + funding) ───────────────────────
    dollar_hits = []
    for m in RE_DOLLAR.finditer(text):
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 40)
        ctx = text[start:end]
        dollar_hits.append((m.group(1), m.group(2), ctx))

    details["revenue"] = "Not found"
    details["last_funding"] = "Not found"

    for num, unit, ctx in dollar_hits:
        if RE_USERS_CTX.search(ctx):
            continue
        val = _clean_dollar(num + " " + unit)
        is_funding = bool(RE_FUNDING_CTX.search(ctx))
        is_revenue = bool(RE_REVENUE_CTX.search(ctx))

        if is_funding and details["last_funding"] == "Not found":
            details["last_funding"] = val
        elif is_revenue and details["revenue"] == "Not found":
            details["revenue"] = val
        elif not is_funding and not is_revenue:
            if "funding" in ctx.lower():
                if details["last_funding"] == "Not found":
                    details["last_funding"] = val
            elif details["last_funding"] == "Not found":
                details["last_funding"] = val

    if details["last_funding"] == "Not found" and RE_BOOTSTRAPPED.search(text):
        details["last_funding"] = "Bootstrapped"

    # ── CEO / Leadership (case-sensitive name matching) ──────────
    ceo = ""
    for pat in RE_CEO_PATTERNS:
        m = pat.search(text)
        if m:
            ceo = m.group(1).strip()
            ceo = RE_CEO_CLEAN.sub("", ceo)
            if ceo:
                break
            ceo = ""
    details["leadership"] = ceo if ceo else "Not found"

    # ── Headquarters (requires "in"/"at" preposition) ────────────
    m = RE_HQ.search(text) or RE_HQ_STRUCTURED.search(text)
    hq = m.group(1).strip().rstrip(",") if m else ""
    countries = RE_HQ_COUNTRIES.findall(hq)
    cities = RE_HQ_CITIES.findall(hq)
    details["headquarters"] = (
        hq if hq and len(countries) < 2 and len(cities) < 3 and len(hq) <= 60
        else "Not found"
    )

    # ── Industry (with blocklist for generic adjectives) ─────────
    industry = "Not found"
    for pat in RE_INDUSTRY_PATTERNS:
        m = pat.search(text)
        if m:
            candidate = m.group(1).strip()
            first_word = candidate.lower().split()[0] if candidate else ""
            if first_word and first_word not in _INDUSTRY_BLOCKLIST:
                industry = candidate
                break
    details["industry"] = industry

    # ── Clients (must contain at least one digit) ────────────────
    clients = "Not found"
    for pat in RE_CLIENTS_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            if re.search(r"\d", val):
                clients = val
                break
    details["clients"] = clients

    return text.strip(), details


def _clean_dollar(val: str) -> str:
    """Normalize '120 million' → '$120M'."""
    val = val.strip().rstrip(",")
    val = RE_DOLLAR_NOISE.sub("", val)
    val = re.sub(r"\s*million", "M", val, flags=re.I)
    val = re.sub(r"\s*billion", "B", val, flags=re.I)
    val = re.sub(r"\s*thousand", "K", val, flags=re.I)
    val = re.sub(r"\s+([MBTK])\b", r"\1", val, flags=re.I)
    if not val.startswith("$"):
        val = "$" + val
    return val


# ── Async API fetchers ──────────────────────────────────────────────────


async def _fetch_tavily(
    client: httpx.AsyncClient, company: str
) -> Optional[dict]:
    """Fetch from Tavily with AI answer. Verbose query → best data extraction."""
    if not TAVILY_API_KEY:
        return None
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"{company} overview founded CEO funding industry revenue employees",
        "search_depth": "basic",
        "include_answer": True,
        "max_results": 3,
    }
    try:
        r = await client.post("https://api.tavily.com/search", json=payload)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


async def _fetch_serper(
    client: httpx.AsyncClient, company: str
) -> Optional[dict]:
    """Fetch from Serper (Google search). Fallback for links + data."""
    if not SERPER_API_KEY:
        return None
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": f"{company} company overview", "num": 3}
    try:
        r = await client.post(
            "https://google.serper.dev/search", json=payload, headers=headers,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ── Parallel search ─────────────────────────────────────────────────────


async def _search_parallel(
    company: str,
) -> Tuple[Optional[str], Dict[str, str], Optional[str], str]:
    """
    Fire Tavily + Serper concurrently.
    If Tavily returns an AI answer quickly, cancel Serper to return immediately.
    """
    client = await _get_client()
    
    tavily_task = asyncio.create_task(_fetch_tavily(client, company))
    serper_task = asyncio.create_task(_fetch_serper(client, company))

    tavily_data = None
    try:
        tavily_data = await tavily_task
    except Exception:
        pass

    serper_data = None
    # If Tavily has a good AI answer, cancel Serper to save time
    if tavily_data and tavily_data.get("answer"):
        if not serper_task.done():
            serper_task.cancel()
    else:
        try:
            serper_data = await serper_task
        except Exception:
            pass

    # Collect link candidates
    link_candidates: list[dict] = []

    if serper_data:
        for item in serper_data.get("organic", [])[:3]:
            link_candidates.append({
                "url": item.get("link", ""),
                "title": item.get("title", ""),
            })
        kg = serper_data.get("knowledgeGraph", {})
        if kg:
            kg_link = kg.get("websiteUrl") or kg.get("website")
            if kg_link:
                link_candidates.insert(0, {"url": kg_link})

    if tavily_data:
        for item in tavily_data.get("results", [])[:3]:
            link_candidates.append({"url": item.get("url", "")})

    link = _pick_best_link(link_candidates, company) if link_candidates else None

    # ── Priority 1: Tavily AI answer (best quality) ──────────────
    if tavily_data:
        answer = tavily_data.get("answer", "")
        if answer:
            summary, details = _split_answer(answer)
            return summary, details, link, "tavily"

        # Tavily returned results but no AI answer — combine raw content
        tavily_results = tavily_data.get("results", [])
        if tavily_results:
            combined = " ".join(
                r.get("content", "") for r in tavily_results[:3] if r.get("content")
            )[:600]
            if combined.strip():
                summary, details = _split_answer(combined)
                return summary, details, link, "tavily"

    # ── Priority 2: Serper fallback ──────────────────────────────
    if serper_data:
        kg = serper_data.get("knowledgeGraph", {})
        organic = serper_data.get("organic", [])

        combined = " | ".join(
            item.get("snippet", "") for item in organic[:3] if item.get("snippet")
        )[:1000]

        if combined.strip():
            summary, details = _split_answer(combined)
            # Enrich details from KG if available
            if kg:
                if kg.get("type") and details.get("industry") == "Not found":
                    details["industry"] = kg["type"]
                if kg.get("employeeCount") and details.get("size") == "Not found":
                    details["size"] = f"{kg['employeeCount']} employees"
            return summary, details, link, "serper"

        if kg.get("description"):
            desc = kg["description"]
            summary, details = _split_answer(desc)
            if kg.get("type") and details.get("industry") == "Not found":
                details["industry"] = kg["type"]
            if kg.get("employeeCount") and details.get("size") == "Not found":
                details["size"] = f"{kg['employeeCount']} employees"
            return desc, details, link, "serper"

    return None, {}, None, ""


# ── Routes ──────────────────────────────────────────────────────────────


@app.post("/lookup", response_model=LookupResponse)
async def lookup(req: LookupRequest):
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

    summary, details, link, source = await _search_parallel(company)
    if summary:
        _add_to_cache(company, summary, details, link, source)
        return LookupResponse(
            summary=summary,
            details=details,
            source=source,
            link=link,
            cached=False,
        )

    raise HTTPException(
        status_code=404,
        detail=f"No information found for '{company}'.",
    )


def _add_to_cache(
    company: str, summary: str, details: dict, link: Optional[str], source: str
):
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
