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


def search_tavily(company: str) -> str | None:
    """Primary: Tavily Search API with a targeted prompt."""
    if not TAVILY_API_KEY:
        return None

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"What does the company {company} do? Keep it to 2 short sentences.",
        "search_depth": "basic",
        "include_answer": True,
        "max_results": 3,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()

        answer = data.get("answer", "")
        if answer:
            return answer.strip()

        # Fallback inside Tavily: use top result content
        results = data.get("results", [])
        if results:
            return results[0].get("content", "")[:400].strip()
    except Exception:
        pass
    return None


def search_serper(company: str) -> str | None:
    """Fallback: Serper API — prefer Knowledge Graph, then organic snippets."""
    if not SERPER_API_KEY:
        return None

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": f"{company} company overview", "num": 3}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        kg = data.get("knowledgeGraph", {})
        if kg and kg.get("description"):
            return kg["description"].strip()

        organic = data.get("organic", [])
        snippets = [
            item.get("snippet", "")
            for item in organic[:2]
            if item.get("snippet")
        ]
        if snippets:
            return " ".join(snippets)[:500].strip()
    except Exception:
        pass
    return None


@app.post("/lookup", response_model=LookupResponse)
def lookup(req: LookupRequest):
    company = req.company.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required.")

    summary = search_tavily(company)
    if summary:
        return LookupResponse(summary=summary, source="tavily")

    summary = search_serper(company)
    if summary:
        return LookupResponse(summary=summary, source="serper")

    raise HTTPException(
        status_code=404,
        detail=f"No information found for '{company}'.",
    )


@app.get("/health")
def health():
    return {"status": "ok"}
