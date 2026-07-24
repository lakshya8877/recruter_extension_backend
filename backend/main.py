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
            f"{company} company overview founded year employees "
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
    details["headquarters"] = m.group(1).strip().rstrip(",") if m else "Not found"

    # Employees / size
    m = re.search(
        r"(?:with\s+)?(?:over|about|around)?\s*([\d,]+(?:[–-][\d,]+)?)\s*(?:employees|staff|people|team members|workers)",
        text, re.I,
    )
    if m:
        details["size"] = m.group(1).replace(",", "") + " employees"
    else:
        m = re.search(r"(\d+[-–]\d+)\s*employees", text, re.I)
        details["size"] = m.group(1) + " employees" if m else "Not found"

    # Revenue
    m = re.search(
        r"(?:revenue|annual revenue)(?:\s*(?:of|is|:))?\s*\$?([\d.]+(?:\s*[MBTK]illion)?)",
        text, re.I,
    )
    details["revenue"] = _fmt_dollar(m.group(1)) if m else "Not found"

    # Funding
    m = re.search(
        r"(?:raised|secured|funding of)\s*\$?([\d.]+(?:\s*[MBTK]illion)?(?:\s*(?:in|to date|total))?)",
        text, re.I,
    )
    if m:
        details["last_funding"] = _fmt_dollar(m.group(1))
    elif re.search(r"bootstrapp|self.funded|no (?:external )?funding", text, re.I):
        details["last_funding"] = "Bootstrapped"
    else:
        details["last_funding"] = "Not found"

    # CEO / Leadership
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

    # Industry
    m = re.search(
        r"(?:operates in|industry|sector)(?:\s*(?:is|:))?\s*(?:the)?\s*([a-zA-Z\s&]+?)(?:\.|,| and|$)",
        text, re.I,
    )
    if not m:
        m = re.search(
            r"(?:a|an|the)\s+([a-z]+(?:\s[a-z]+){0,3})\s+(?:company|firm|platform|startup|business)",
            text, re.I,
        )
    details["industry"] = m.group(1).strip() if m else "Not found"

    # Clients
    m = re.search(
        r"(?:clients|customers|users)(?:\s*(?:include|of|:))?\s*(?:over|about|more than)?\s*([\d,.]+(?:\s*[MBK]illion)?(?:\s*(?:active|paying|registered|daily))?)",
        text, re.I,
    )
    if not m:
        m = re.search(
            r"([\d,.]+(?:\s*[MBK]illion)?)\s*(?:active|paying|registered|daily)?\s*(?:clients|customers|users)",
            text, re.I,
        )
    details["clients"] = m.group(1).strip() if m else "Not found"

    return text.strip(), details


def _fmt_dollar(val: str) -> str:
    """Normalize '169 million' → '$169M', '2 billion' → '$2B'."""
    val = val.strip().rstrip(",")
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
    payload = {"q": f"{company} company overview founded employees revenue", "num": 10}
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
