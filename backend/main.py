import os
import re
import requests
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


class LookupRequest(BaseModel):
    company: str


class LookupResponse(BaseModel):
    summary: str
    details: dict[str, str]
    source: str
    link: str | None = None


# ── Tavily (primary) ───────────────────────────────────────────────────


def search_tavily(company: str) -> tuple[str | None, dict[str, str], str | None]:
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
        link = results[0].get("url") if results else None
        answer = data.get("answer", "")

        if answer:
            return _split_answer(answer), link

        # Fallback: stitch snippets
        if results:
            combined = " ".join(
                r.get("content", "") for r in results[:3] if r.get("content")
            )[:600]
            if combined.strip():
                return _split_answer(combined), link
    except Exception:
        pass
    return None, {}, None


def _split_answer(text: str) -> tuple[str, dict[str, str]]:
    """
    Parse the answer text into a 1-2 sentence summary + structured details.
    The answer from the keyword query naturally contains:
    founded, headquarters, employees, revenue, funding, CEO, industry, clients.
    """
    details: dict[str, str] = {}

    # ── Founding year ──────────────────────────────────────────────
    m = re.search(r"(?:founded|established|launched)\s*(?:in)?\s*(\d{4})", text, re.I)
    details["founding_year"] = m.group(1) if m else "Not found"

    # ── Headquarters ───────────────────────────────────────────────
    m = re.search(
        r"(?:headquartered|based|located)\s*(?:in|at)?\s*([A-Z][a-zA-Z\s]+?(?:,\s*[A-Z]{2})?(?:,\s*[A-Z][a-z]+)?)(?:\.|,|\s+with|\s+and|\s+It|\s+The|$)",
        text, re.I,
    )
    details["headquarters"] = m.group(1).strip().rstrip(",") if m else "Not found"

    # ── Employees / size ───────────────────────────────────────────
    m = re.search(
        r"(?:with\s+)?(?:over|about|around)?\s*([\d,]+(?:[–-][\d,]+)?)\s*(?:employees|staff|people|team members|workers)",
        text, re.I,
    )
    if m:
        details["size"] = m.group(1).replace(",", "") + " employees"
    else:
        m = re.search(r"(\d+[-–]\d+)\s*employees", text, re.I)
        details["size"] = m.group(1) + " employees" if m else "Not found"

    # ── Revenue ────────────────────────────────────────────────────
    m = re.search(
        r"(?:revenue|annual revenue)(?:\s*(?:of|is|:))?\s*\$?([\d.]+(?:\s*[MBTK]illion)?)",
        text, re.I,
    )
    details["revenue"] = f"${m.group(1)}" if m and "$" not in m.group(1) else (m.group(1).strip() if m else "Not found")

    # ── Funding ────────────────────────────────────────────────────
    m = re.search(
        r"(?:raised|secured|funding of)\s*\$?([\d.]+(?:\s*[MBTK]illion)?(?:\s*(?:in|to date|total))?)",
        text, re.I,
    )
    if m:
        val = m.group(1).strip()
        details["last_funding"] = f"${val}" if "$" not in val else val
    elif re.search(r"bootstrapp|self.funded|no (?:external )?funding", text, re.I):
        details["last_funding"] = "Bootstrapped"
    else:
        details["last_funding"] = "Not found"

    # ── CEO / Leadership ───────────────────────────────────────────
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

    # ── Industry ───────────────────────────────────────────────────
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

    # ── Clients ────────────────────────────────────────────────────
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

    # Summary is the full answer (it's already concise 1-3 sentences)
    return text.strip(), details


# ── Serper (fallback) ──────────────────────────────────────────────────


def search_serper(company: str) -> tuple[str | None, dict[str, str], str | None]:
    if not SERPER_API_KEY:
        return None, {}, None

    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {
        "q": f"{company} company overview founded employees revenue",
        "num": 10,
    }
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
            link = organic[0].get("link")

        parts = []
        if kg.get("description"):
            parts.append(kg["description"])
        for item in organic[:3]:
            s = item.get("snippet", "")
            if s:
                parts.append(s)

        summary = " | ".join(parts)[:600] if parts else None

        details: dict[str, str] = {}
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
    company = req.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    summary, details, link = search_tavily(company)
    if summary:
        return LookupResponse(
            summary=summary, details=details, source="tavily", link=link,
        )

    summary, details, link = search_serper(company)
    if summary:
        return LookupResponse(
            summary=summary, details=details, source="serper", link=link,
        )

    raise HTTPException(
        status_code=404,
        detail=f"No information found for '{company}'.",
    )


@app.get("/health")
def health():
    return {"status": "ok"}
