import os
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
    source: str
    link: str | None = None


# ── Search query builders ──────────────────────────────────────────────


def india_query(company: str) -> str:
    """Clean keyword query biased toward Indian results."""
    return f"{company} company India overview funding employees headquarters"


def global_query(company: str) -> str:
    """Fallback: broader international search."""
    return f"{company} company overview industry funding employees headquarters"


# ── Tavily (primary) ───────────────────────────────────────────────────


def search_tavily(company: str) -> tuple[str | None, str | None]:
    if not TAVILY_API_KEY:
        return None, None

    # Try India-first, then global fallback
    for query in [india_query(company), global_query(company)]:
        result = _tavily_call(query)
        if result[0]:
            return result
    return None, None


def _tavily_call(query: str) -> tuple[str | None, str | None]:
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": 10,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()

        results = data.get("results", [])
        link = results[0].get("url") if results else None

        answer = data.get("answer", "")
        if answer:
            return answer.strip(), link

        # Fallback: stitch top snippets
        if results:
            combined = " ".join(
                r.get("content", "") for r in results[:3] if r.get("content")
            )[:800]
            if combined.strip():
                return combined.strip(), link
    except Exception:
        pass
    return None, None


# ── Serper (fallback) ──────────────────────────────────────────────────


def search_serper(company: str) -> tuple[str | None, str | None]:
    if not SERPER_API_KEY:
        return None, None

    for query in [india_query(company), global_query(company)]:
        result = _serper_call(query)
        if result[0]:
            return result
    return None, None


def _serper_call(query: str) -> tuple[str | None, str | None]:
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    payload = {"q": query, "num": 10}

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        kg = data.get("knowledgeGraph", {})
        organic = data.get("organic", [])

        link = kg.get("websiteUrl") or kg.get("website")
        if not link and organic:
            link = organic[0].get("link")

        parts = []
        if kg:
            if kg.get("description"):
                parts.append(kg["description"])
            if kg.get("type"):
                parts.append(f"Type: {kg['type']}")
            if kg.get("employeeCount"):
                parts.append(f"Employees: ~{kg['employeeCount']}")

        for item in organic[:5]:
            snippet = item.get("snippet", "")
            if snippet:
                parts.append(snippet)

        combined = " | ".join(parts)[:800]
        if combined.strip():
            return combined.strip(), link
    except Exception:
        pass
    return None, None


# ── Routes ─────────────────────────────────────────────────────────────


@app.post("/lookup", response_model=LookupResponse)
def lookup(req: LookupRequest):
    company = req.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    summary, link = search_tavily(company)
    if summary:
        return LookupResponse(summary=summary, source="tavily", link=link)

    summary, link = search_serper(company)
    if summary:
        return LookupResponse(summary=summary, source="serper", link=link)

    raise HTTPException(
        status_code=404,
        detail=f"No information found for '{company}'.",
    )


@app.get("/health")
def health():
    return {"status": "ok"}
