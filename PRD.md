# Product Requirements Document: Recruiter Quick Search

> **Status:** Draft v1.0  
> **Date:** July 24, 2026  
> **Author:** Hermes Agent (based on existing implementation and problem statement)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Solution Overview](#3-solution-overview)
4. [Current Implementation](#4-current-implementation)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [Architecture & Data Flow](#7-architecture--data-flow)
8. [API Specification](#8-api-specification)
9. [User Experience Flow](#9-user-experience-flow)
10. [Success Metrics](#10-success-metrics)
11. [Future Roadmap](#11-future-roadmap)
12. [Risks & Mitigations](#12-risks--mitigations)
13. [Appendix: Technology Stack](#13-appendix-technology-stack)

---

## 1. Executive Summary

**Recruiter Quick Search** is a lightweight Chrome extension + FastAPI backend that eliminates context-switching during resume screening. When a recruiter highlights an unfamiliar company name on any webpage and triggers the tool (keyboard shortcut or toolbar click), a floating popup instantly displays a concise summary sourced from search APIs — no new tabs, no leaving the document.

The initial implementation is fully functional: a Manifest V3 Chrome extension paired with a FastAPI backend deployed on Vercel, with a dual-API (Tavily → Serper) fallback chain for reliability.

---

## 2. Problem Statement

### Context

During high-volume resume screening, recruiters frequently encounter unfamiliar company names and need to quickly verify their industry, legitimacy, and scale.

### The Problem

The current verification workflow is heavily fragmented. A recruiter must:

1. Highlight the company name
2. Right-click → "Search Google for…"
3. Wait for a new tab to open
4. Scan through multiple search results
5. Piece together a mental summary from snippets
6. Close the tab and navigate back to the original document

This constant context-switching breaks focus, introduces cognitive friction, and significantly slows down evaluation.

### Impact

| Metric | Estimate |
|---|---|
| Time lost per lookup | 15–30 seconds (vs. 2–3 seconds with inline tool) |
| Context switches per session | 20–50 (for a typical screening batch of 50 resumes) |
| Cognitive overhead | High — recruiter must re-orient after each interruption |
| Missed flags | Unknown companies may be skipped entirely rather than investigated |

---

## 3. Solution Overview

A **browser-native tool** that surfaces company information directly inside the workflow:

> **Trigger:** Highlight company name → press `Ctrl+Shift+Y` (or click extension icon)  
> **Result:** A floating popup appears on the same page with a 1–2 sentence summary, source attribution, and optional link to the company website  
> **Dismissal:** Close button, `Escape` key, or click outside  
> **Stay in flow:** The recruiter never leaves the resume

### Core Design Principles

1. **Zero context-switching** — everything happens on the current page
2. **Speed over depth** — 2-sentence summary, not a Wikipedia article
3. **Minimal permissions** — `activeTab` + `scripting` only; access granted on explicit user action
4. **Resilient** — multi-API fallback chain; one broken API doesn't kill the tool
5. **Self-contained** — no external accounts or complex setup required

---

## 4. Current Implementation

What has already been built and is operational:

### 4.1 Chrome Extension (`extension/`)

| File | Purpose | Status |
|---|---|---|
| `manifest.json` | Manifest V3 config: permissions, commands, icons | Complete |
| `background.js` | Service worker — injects `content.js` on icon click or shortcut | Complete |
| `content.js` | IIFE injected into page: reads selection, calls backend, renders popup | Complete |
| `icons/` | Icons at 16px, 48px, 128px (generated from `main.png` via `resize.py`) | Complete |

**Key implementation details (content.js):**
- Idempotency issue: no injection guard (`window.__rqsLoaded` check). Each trigger re-injects and re-executes the IIFE → overwrites previous popup via `removePopup()` at the start of `showPopup()`. Functional but suboptimal (re-fetches font/stylesheet on every injection).
- Dismissal: close button + `Escape` key. No click-outside-to-dismiss.
- Error states: "no selection" warning, loading spinner, API error display, network failure message.
- Result rendering: summary text + clickable "Visit Official Page →" link when available.
- Backend URL hardcoded to `https://recruter-exten.vercel.app/lookup`.

### 4.2 FastAPI Backend (`backend/`)

| File | Purpose | Status |
|---|---|---|
| `main.py` | FastAPI app: `/lookup` (POST) + `/health` (GET), dual-API chain | Complete |
| `requirements.txt` | Dependencies: fastapi, uvicorn, pydantic, requests | Complete |
| `vercel.json` | Vercel deployment config: Python runtime, catch-all route | Complete |

**API chain (resilient fallback):**

```
POST /lookup { company: "Acme Corp" }
    │
    ├─ search_tavily(company)
    │    ├─ Tavily Search API (with include_answer=true)
    │    └─ Returns: (summary, link) or (None, None) on failure
    │
    └─ search_serper(company)  ← only called if Tavily returned None
         ├─ Serper Google Search API
         ├─ Prefers Knowledge Graph description
         └─ Falls back to concatenated organic snippets
```

**Key implementation details:**
- Each search function catches its own exceptions — one API failure doesn't crash the endpoint.
- Tavily prompt: "What does the company X do? Keep it to 2 short sentences." (Targeted, concise.)
- Serper uses `knowledgeGraph.description` preferentially (more authoritative).
- Both return a `link` (company website or top search result) alongside the summary.
- CORS: wide open (`allow_origins=["*"]`) — acceptable since the API only does lookups, no auth.
- API keys read from environment: `TAVILY_API_KEY`, `SERPER_API_KEY`.
- Deployed on Vercel at `recruter-exten.vercel.app`.

---

## 5. Functional Requirements

### FR-1: Text Selection Detection
- The extension SHALL read the user's currently highlighted text via `window.getSelection()`.
- If no text is highlighted when triggered, the extension SHALL display an inline warning: "Please highlight a company name first."

### FR-2: One-Click Trigger
The extension SHALL be triggerable via two methods:
- **Keyboard shortcut:** `Ctrl+Shift+Y` (Windows/Linux) / `Command+Shift+Y` (macOS)
- **Toolbar icon click:** Clicking the extension icon in the Chrome toolbar

### FR-3: Company Lookup
- The extension SHALL send the highlighted text to the backend as a JSON POST: `{ "company": "<text>" }`.
- The backend SHALL return: `{ "summary": "...", "source": "tavily|serper", "link": "..." }`.
- The backend SHALL use a fallback chain: Tavily → Serper → 404.

### FR-4: Inline Popup Display
- Results SHALL appear as a floating `<div>` overlay on the current page (not a new tab or window).
- The popup SHALL include: title bar, summary text, source attribution, and optional link.
- The popup SHALL appear at top-right of the viewport (`position: fixed; top: 20px; right: 20px`).

### FR-5: Popup Dismissal
The user SHALL be able to dismiss the popup via:
- Close button (×) in the popup header
- `Escape` key press
- (Future) Click outside the popup boundary

### FR-6: Loading & Error States
| State | Display |
|---|---|
| No selection | "Please highlight a company name first." |
| In progress | "Searching for "CompanyName"..." |
| Success | Summary text + optional "Visit Official Page →" link |
| Not found (404) | "No information found for 'CompanyName'." |
| Network error | "Could not reach the backend. Check your connection." |
| Validation error | "Validation Error: Backend expected a different data format." |

### FR-7: Health Check
- The backend SHALL expose `GET /health` returning `{ "status": "ok" }` for monitoring and cold-start detection.

---

## 6. Non-Functional Requirements

### NFR-1: Performance
| Metric | Target |
|---|---|
| Popup appearance (from trigger) | < 500ms (local render only) |
| Backend response time (Tavily) | < 3 seconds (p95) |
| Backend response time (Serper fallback) | < 5 seconds (p95) |
| Vercel cold start | < 5 seconds (acceptable, shown as loading state) |

### NFR-2: Reliability
- Backend uptime target: 99.5% (Vercel SLA-dependent)
- Dual-API fallback ensures availability even if one API is down or rate-limited
- Extension SHALL NOT crash the host page under any DOM manipulation failure

### NFR-3: Security & Privacy
- Extension uses `activeTab` permission — only accesses the current tab on explicit user action
- No data persistence: company names are not logged, stored, or sent to third parties beyond the search APIs
- API keys stored server-side (Vercel environment variables), never in client code
- Content script injected into page context — uses `textContent` assignment (not `innerHTML`) for summary display to prevent XSS

### NFR-4: Compatibility
- Chrome 88+ (Manifest V3 support)
- Edge, Brave, Opera, and other Chromium-based browsers (untested but compatible)
- All web pages except `chrome://`, `edge://`, and extension pages (blocked by browser)

### NFR-5: Maintainability
- Backend: single-file FastAPI app (< 130 lines) — easy to modify or extend
- Extension: clean separation of concerns (background → injection → UI)
- API chain pattern: adding a new search provider requires only one new function + one line in the orchestrator

---

## 7. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────────────┐
│                        USER'S BROWSER                          │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Web Page (e.g., LinkedIn, Indeed, PDF resume viewer)    │  │
│  │                                                          │  │
│  │  1. User highlights "Acme Corp"                          │  │
│  │  2. User presses Ctrl+Shift+Y                            │  │
│  │     ─ OR clicks extension icon ─                         │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────┐                │  │
│  │  │  content.js (injected into page)     │                │  │
│  │  │                                      │                │  │
│  │  │  3. window.getSelection() → "Acme"   │                │  │
│  │  │  4. Show loading popup               │                │  │
│  │  │  5. POST /lookup {company:"Acme"}    │────────────────│──┐
│  │  │  6. Render result in popup           │                │  │
│  │  │  7. User dismisses (Esc / × / click) │                │  │
│  │  └──────────────────────────────────────┘                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  background.js (service worker)                          │  │
│  │  chrome.action.onClicked → executeScript(content.js)     │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS POST
                              ▼
┌────────────────────────────────────────────────────────────────┐
│                    VERCEL (recruter-exten.vercel.app)          │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FastAPI (main.py)                                       │  │
│  │                                                          │  │
│  │  POST /lookup                                            │  │
│  │    │                                                     │  │
│  │    ├── search_tavily(company) ──── Tavily Search API     │  │
│  │    │     └─ returns (summary, link) or None              │  │
│  │    │                                                     │  │
│  │    └── search_serper(company) ──── Serper Google API     │  │
│  │          └─ returns (summary, link) or None              │  │
│  │                                                          │  │
│  │  Returns: {summary, source, link}                        │  │
│  │                                                          │  │
│  │  GET /health → {"status":"ok"}                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

---

## 8. API Specification

### 8.1 `POST /lookup`

**Request:**
```json
{
  "company": "Acme Corp"
}
```
| Field | Type | Required | Description |
|---|---|---|---|
| `company` | string | Yes | The company name to look up. Trimmed server-side. |

**Response (200 OK):**
```json
{
  "summary": "Acme Corp is a multinational manufacturing company specializing in anvils, explosives, and rocket-powered roller skates.",
  "source": "tavily",
  "link": "https://www.acmecorp.com"
}
```
| Field | Type | Description |
|---|---|---|
| `summary` | string | 1–2 sentence summary from the search API |
| `source` | string | Which API produced the result: `"tavily"` or `"serper"` |
| `link` | string \| null | Company website or top search result URL |

**Response (404 Not Found):**
```json
{
  "detail": "No information found for 'Acme Corp'."
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Company name is required."
}
```

### 8.2 `GET /health`

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

## 9. User Experience Flow

### Primary Flow (Happy Path)

```
1. Recruiter opens resume in browser (LinkedIn, PDF, Excel, etc.)
2. Reads: "Senior Engineer at [UnfamiliarCompany]"
3. Highlights "UnfamiliarCompany" with mouse
4. Presses Ctrl+Shift+Y
   → Popup appears top-right: "Searching for 'UnfamiliarCompany'..."
   → (~1.5 seconds)
   → Popup updates: "UnfamiliarCompany is a Series B fintech startup
      building AI-powered invoice processing for mid-market enterprises."
      [Visit Official Page →]
5. Recruiter reads summary, mentally categorizes company (legit, mid-size, fintech)
6. Presses Escape → popup disappears
7. Continues reading resume (total interruption: ~3 seconds)
```

### Edge Cases

| Scenario | Behavior |
|---|---|
| No text selected | Show "Please highlight a company name first." |
| Very long selection (paragraph) | Sends full text to backend; backend handles it (API will return results for the first recognizable entity or no results) |
| Backend cold start | Loading spinner shows for 2–5 seconds (Vercel cold start) |
| Tavily rate-limited | Falls through to Serper automatically |
| Both APIs fail | 404 — "No information found" |
| Network offline | "Could not reach the backend." |
| chrome:// page | Injection blocked by browser; service worker catches error silently |

---

## 10. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Time per lookup | ≤ 5 seconds | Instrument backend with response time logging |
| Reduction in tab switches | 90%+ | Self-reported (user survey) |
| Daily active users | 1+ (personal tool) | Vercel analytics / request count |
| Backend availability | 99.5% | Vercel uptime monitoring |
| User satisfaction | "Would recommend" | Qualitative feedback |

---

## 11. Future Roadmap

### Phase 2: Polish & Robustness
- [ ] **Injection guard:** Add `window.__rqsLoaded` check in `content.js` to avoid redundant re-injection
- [ ] **Click-outside dismissal:** Close popup when user clicks anywhere outside it
- [ ] **Configurable backend URL:** Store in `chrome.storage.local` with a default, add options page
- [ ] **Keyboard shortcut customization:** Allow user to change from `Ctrl+Shift+Y` to another combo via `chrome://extensions/shortcuts`
- [ ] **Timeout handling:** Add AbortController with 10-second timeout on fetch

### Phase 3: Feature Expansion
- [ ] **Multi-source enrichment:** Add Crunchbase API for funding/employee count data
- [ ] **Copy-to-clipboard:** Button to copy the summary for pasting into notes/ATS
- [ ] **History panel:** Keep last 5 lookups accessible in a side panel (stored in session)
- [ ] **Dark mode:** Detect page color scheme and match popup theme
- [ ] **Offline cache:** Cache recent lookups in `chrome.storage.local` for instant recall

### Phase 4: Team Readiness
- [ ] **Packaging:** Prepare for Chrome Web Store submission (privacy policy, screenshots, description)
- [ ] **Configurable API keys:** Allow teams to bring their own Tavily/Serper keys
- [ ] **Usage dashboard:** Simple admin panel showing lookup volume and API health
- [ ] **Browser support:** Test and validate on Firefox (Manifest V3 port)

---

## 12. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Tavily API deprecation or pricing change | High | Dual-API architecture already in place; Serper serves as immediate fallback. Adding a third provider (e.g., Brave Search, Bing) is a one-function change. |
| Vercel cold starts degrade UX | Medium | Loading state already shown. For production, upgrade to Vercel Pro (no cold starts on paid tier) or migrate to always-warm instance. |
| Content script injection blocked on certain pages | Low | `chrome://`, `edge://`, and extension pages are explicitly caught. For PDF viewers and other restricted contexts, no workaround exists — documented limitation. |
| Company name ambiguity ("Apple" = tech vs. fruit) | Low | Search APIs handle this reasonably well with the targeted prompt. If it becomes an issue, add a disambiguation UI ("Did you mean Apple Inc. or Apple Bank?"). |
| API key exposure if Vercel environment is compromised | Low | Vercel env vars are encrypted at rest. Keys are never sent to the client. |
| Chrome Web Store rejection | Medium | Manifest V3, minimal permissions (`activeTab`), no data collection. Should pass review, but have appeal arguments prepared. |

---

## 13. Appendix: Technology Stack

| Component | Technology | Version |
|---|---|---|
| Browser extension | Chrome Manifest V3 | — |
| Extension language | Vanilla JavaScript (no framework) | ES2020+ |
| Backend framework | FastAPI (Python) | 0.115.6 |
| Backend deployment | Vercel (serverless) | — |
| Primary search API | Tavily Search | — |
| Fallback search API | Serper (Google Search) | — |
| HTTP client | requests (Python) | 2.32.3 |
| Data validation | Pydantic | 2.10.3 |
| CORS | FastAPI CORSMiddleware | built-in |

---

> **Document maintained in:** `D:\Documents\GitHub\recruter_extension_backend\PRD.md`  
> **Last updated:** July 24, 2026
