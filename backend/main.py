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


def build_search_query(company: str) -> str:
    """Build an India-focused search query that also instructs Tavily's answer LLM
    to format the response in the structured recruiter format."""
    return (
        f"Research the company '{company}' focusing on its India presence, "
        f"funding rounds, employee count, CEO, industry, culture, and recent news. "
        f"Provide a structured summary with these exact sections:\n"
        f"**Industry & Market Position:** what they do and market standing\n"
        f"**Financial Health & Scale:** funding stage, employee count, revenue\n"
        f"**Culture & Environment:** work style, remote/hybrid, engineering pace\n"
        f"**Mission & Values:** goals and company DNA\n"
        f"**Leadership:** founders, CEO, notable executives\n"
        f"**Recent Momentum:** latest launches, funding, acquisitions, news\n"
        f"If any section cannot be determined, state 'Data unavailable for this metric'. "
        f"Keep the entire response under 500 words."
    )


def search_tavily(company: str) -> tuple[str | None, str | None]:
    """Primary: Tavily Search API with structured recruiter prompt."""
    if not TAVILY_API_KEY:
        return None, None

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": build_search_query(company),
        "search_depth": "advanced",
        "include_answer": True,
        "max_results": 10,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()

        # Collect rich search context for the answer
        results = data.get("results", [])
        link = results[0].get("url") if results else None

        # Build context snippet from top results to enrich Tavily's answer generation
        # (Tavily already feeds results to its answer LLM, but a richer query helps)
        answer = data.get("answer", "")
        if answer:
            # Post-process: prepend the structured format instruction
            # The answer already incorporates the search results; we format it
            formatted = format_as_recruiter_summary(answer, company)
            return formatted, link

        # Fallback: build from result snippets
        if results:
            snippets = []
            for r_item in results[:5]:
                title = r_item.get("title", "")
                content = r_item.get("content", "")
                if content:
                    snippets.append(f"{title}: {content}")
            combined = "\n\n".join(snippets)[:2000]
            formatted = format_as_recruiter_summary(combined, company)
            return formatted, link
    except Exception:
        pass
    return None, None


def search_serper(company: str) -> tuple[str | None, str | None]:
    """Fallback: Serper API — India-focused with Knowledge Graph preference."""
    if not SERPER_API_KEY:
        return None, None

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": build_search_query(company), "num": 10}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()

        kg = data.get("knowledgeGraph", {})
        organic = data.get("organic", [])

        link = kg.get("websiteUrl") or kg.get("website")
        if not link and organic:
            link = organic[0].get("link")

        # Build rich context from KG + organic results
        parts = []
        if kg:
            kg_parts = []
            if kg.get("title"):
                kg_parts.append(f"Company: {kg['title']}")
            if kg.get("type"):
                kg_parts.append(f"Type: {kg['type']}")
            if kg.get("description"):
                kg_parts.append(f"Description: {kg['description']}")
            if kg.get("attributes"):
                for k, v in kg["attributes"].items():
                    kg_parts.append(f"{k}: {v}")
            if kg.get("employeeCount"):
                kg_parts.append(f"Employees: {kg['employeeCount']}")
            parts.append("\n".join(kg_parts))

        for item in organic[:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if snippet:
                parts.append(f"{title}: {snippet}")

        combined = "\n\n".join(parts)[:2000]
        if combined.strip():
            formatted = format_as_recruiter_summary(combined, company)
            return formatted, link
    except Exception:
        pass
    return None, None


def format_as_recruiter_summary(raw_data: str, company: str) -> str:
    """
    Wrap raw search data with the structured recruiter format.
    Since we don't have an LLM in this pipeline, we build the prompt
    and return it alongside the data — the raw data is rich enough
    that Tavily's answer (or the structured snippets) provide value.

    If raw_data is already well-structured (from Tavily's answer LLM),
    it passes through. Otherwise, we provide a best-effort extraction.
    """
    # If Tavily's answer LLM already produced good structured output, return as-is
    # Check if it has recognizable section markers
    section_markers = [
        "Industry", "Financial", "Culture", "Mission", "Leadership", "Momentum"
    ]
    marker_count = sum(1 for m in section_markers if m.lower() in raw_data.lower())

    if marker_count >= 4:
        # Already well-structured — return clean
        return raw_data.strip()

    # Fallback: wrap raw data with the recruiter prompt format
    # The search data contains relevant info; present it under appropriate headers
    return (
        f"The search returned the following information about **{company}**:\n\n"
        f"{raw_data.strip()}\n\n"
        f"---\n"
        f"*Note: For best results, configure an LLM API key (OpenAI/Anthropic) in the "
        f"backend to generate fully structured recruiter summaries. "
        f"The data above contains the raw search context for manual review.*"
    )


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
