# Recruiter Quick Search — Product Requirements Document

> **Version 2.0** | July 24, 2026 | Status: Live (Vercel)

---

## 1. What It Does

A Chrome extension that lets recruiters look up a company without leaving the resume. Highlight any company name on any webpage, press `Ctrl+Shift+Y`, and a popup appears with an instant summary plus key facts. No new tabs, no Googling, no context-switching.

**One flow, three seconds:** Highlight → shortcut → read → dismiss.

---

## 2. Problem Statement

### Context

During high-volume resume screening, recruiters frequently encounter unfamiliar company names and need to quickly verify their industry, legitimacy, and scale. A candidate's past employer is one of the strongest signals on a resume — but only if the recruiter can evaluate it.

### The Problem

The current verification workflow is heavily fragmented. A recruiter must:

1. Highlight the company name
2. Right-click to search
3. Wait for a new tab to open
4. Scan through multiple search results
5. Piece together a mental summary from snippets
6. Close the tab and navigate back to the original document

This constant context-switching breaks focus, introduces cognitive friction, and significantly slows down the evaluation process.

### Impact

Recruiters screen 50-100 resumes a day. Every unfamiliar company name forces this detour. Each one costs 15-30 seconds and breaks the recruiter's flow. Over a single day, that adds up to 20-50 context switches — wasted time, mental fatigue, and companies that get skipped rather than investigated.

This tool collapses that detour into a single keystroke on the same page.

---

## 3. What the Recruiter Sees

### Trigger
- Highlight a company name anywhere (LinkedIn, PDF, Excel, job boards)
- Press `Ctrl+Shift+Y` — or click the extension icon in the toolbar

### The Popup
A floating card appears in the top-right corner of the page:

```
┌─────────────────────────────────────────┐
│  Company Lookup                      ×  │
│                                         │
│  Zerodha is an Indian financial         │
│  services company founded in 2010,      │
│  headquartered in Bengaluru, offering   │
│  brokerage-free stock trading. It has   │
│  over 7.5 million active clients.   [cached]
│                                         │
│  Founded:     2010                      │
│  Headquarters: Bengaluru                │
│  Size:        Not found                 │
│  Revenue:     Not found                 │
│  Funding:     Bootstrapped              │
│  Industry:    Financial Services        │
│  Leadership:  Nithin Kamath             │
│  Clients:     7.5 million               │
│                                         │
│  Visit Official Website                 │
└─────────────────────────────────────────┘
```

### Dismissal
- Click the × button
- Press `Escape`
- Click anywhere outside the popup

### Cache
If you look up the same company again, it returns instantly with a green "cached" badge. The last 10 lookups are cached automatically.

---

## 4. What Data It Shows

| Field | Description | Example |
|---|---|---|
| **Summary** | 1-3 sentence narrative about the company | "Fintech company founded in 2010..." |
| **Founded** | Year the company was established | 2010 |
| **Headquarters** | City and country | Bengaluru |
| **Size** | Employee count or range | 4,000 employees |
| **Revenue** | Annual revenue estimate | $250M |
| **Funding** | Total funding raised, or "Bootstrapped" | $433M |
| **Industry** | Sector the company operates in | Financial Services |
| **Leadership** | CEO or founder names | Nithin Kamath |
| **Clients** | User/customer count or notable names | 7.5 million |
| **Official Link** | Direct link to company website | zerodha.com |

Fields that can't be found show "Not found" — the tool never guesses.

---

## 5. How It Works (Non-Technical)

1. You highlight text and trigger the extension
2. The extension sends the company name to a backend API on Vercel
3. The backend searches the web using the Tavily Search API
4. Results are parsed into a summary + 8 structured data points
5. The popup renders everything on the same page
6. Repeated lookups hit an in-memory cache (instant)

The entire round-trip takes 2-4 seconds. If the backend is waking up from idle (Vercel cold start), it may take up to 5 seconds — a loading message is shown.

---

## 6. Error Handling

| Situation | What the recruiter sees |
|---|---|
| No text highlighted | "Please highlight a company name first." |
| Searching | "Searching for 'CompanyName'..." |
| Company not found | "No information found for 'CompanyName'." |
| Network issue | "Could not reach the backend. Check your connection." |
| Backend error | A clear error message, no crash |

The extension never breaks the host page. On restricted pages (chrome://, edge://), it silently does nothing.

---

## 7. Current Limitations & Known Issues

| Issue | Impact | Status |
|---|---|---|
| Ambiguous company names | Search may blend data from similarly-named companies | Mitigated with exact-phrase matching |
| Obscure/very new companies | May return "No information found" | Acceptable for now |
| Cold start delay | First lookup after idle takes 3-5s | Loading state shown |
| India bias is keyword-based | Not a geo-filter, just query prioritization | Works for most Indian companies |

---

## 8. What's Planned Next

- Serper (Google Search) as a fallback API when Tavily returns no results
- Government startup database APIs for Indian company data (Startup India, MCA registry)
- Improved disambiguation for companies with shared or similar names
- Copy-to-clipboard button on the popup for pasting into ATS notes
- Dark mode detection to match the host page theme

---

## 9. Technical Summary (For Developers)

| Component | Technology |
|---|---|
| Browser Extension | Chrome Manifest V3, vanilla JS |
| Backend | FastAPI (Python), deployed on Vercel |
| Primary Search | Tavily Search API (AI-powered answers) |
| Cache | In-memory LRU, last 10 lookups |
| API Keys | Stored in Vercel environment variables |

**Files:**
- `extension/` — manifest.json, background.js, content.js, icons/
- `backend/` — main.py, requirements.txt, vercel.json

**Endpoints:**
- `POST /lookup` — returns `{ summary, details: {...}, source, link, cached }`
- `GET /health` — returns `{ status: "ok" }`

**Response time:** 2-4 seconds
