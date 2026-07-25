# Recruiter Quick Search — PRD v3.0

> July 24, 2026 | Status: Live (Vercel)

### Product Summary

A Chrome extension for recruiters. Highlight a company name on any page, press `Ctrl+Shift+Y`, and a popup shows an instant summary with eight structured facts. No new tabs, no Googling, no context-switching.

### Problem Statement

A candidate's past employer is one of the strongest signals on a resume — but only if the recruiter can evaluate it. During high-volume screening, recruiters frequently encounter unfamiliar company names and must decide in seconds whether that employer makes the candidate relevant and credible.

Today, verifying an unfamiliar company means a six-step detour: highlight, right-click, open a new tab, scan results, piece together a mental picture, then navigate back. Each detour costs 15–30 seconds and breaks screening flow. Over 50–100 resumes a day, recruiters produce 20–50 of these context switches — and unfamiliar companies often get skipped rather than investigated. This means strong candidates from lesser-known employers are silently rejected, and fabricated employers pass through unchallenged.

### Target User

Agency and in-house recruiters screening 50–100 resumes per day, with a focus on the Indian hiring market.

### Data Points — What the Recruiter Needs and Why

- **Summary** — 1–3 sentence description of what the company does. The go/no-go gate. A BPO for a product-engineering role gets rejected in 3 seconds instead of 30.
- **Industry** — Fastest hard filter. A fintech role drops non-fintech candidates immediately. When domain experience is a "nice to have," it serves as a ranking signal.
- **Size** — Headcount calibrates title meaning. An "Engineering Manager" at a 10-person startup and at a 10,000-person enterprise are different jobs. Predicts environment fit — mismatched scale is a known attrition risk.
- **Founded** — Legitimacy and context. A candidate claiming 6 years at a company founded 2 years ago is an immediate red flag. Age signals whether the experience was early-stage scrappiness or mature, process-driven operations.
- **Funding** — Stage proxy. Seed-stage means 0-to-1 work, Series-D means scaling processes, bootstrapped means capital-efficient. Matching candidate stage to hiring company stage is a strong predictor of startup-hire success.
- **Revenue** — Makes impact claims falsifiable. "Managed a Rs.50 Cr portfolio" at a negligible-revenue company doesn't add up. Separates substantive businesses from shell companies.
- **Clients** — Validates scale-of-work claims and reveals B2B vs. B2C exposure. Notable client logos transfer credibility — the candidate survived enterprise-grade scrutiny.
- **Leadership** — Known founders upgrade unknown companies. "Ex-Flipkart leader" reframes a no-name startup as a pedigree employer. Provides a concrete reference backchannel.
- **Headquarters** — Reveals which market the candidate knows — India-market vs. global exposure. Supports location verification on the resume.
- **Official Link** — One click to the employer's website for deeper diligence on shortlist-worthy profiles.
- **"Not found"** — Absence of information is itself information. The tool never hallucinates. A company with no discoverable footprint is a screening signal: obscure but real, or fabricated.

### Restricted Pages (Google Drive, Docs)

On canvas-rendered pages where `window.getSelection()` fails, the extension reads the clipboard as fallback. The user workflow is: highlight text, press `Ctrl+C` to copy, then `Ctrl+Shift+Y` to search. The popup shows an orange tip explaining this. On normal web pages, text selection works directly — no copy step needed.

### Usage

Highlight a company name anywhere — LinkedIn, PDF, Excel, job boards — press `Ctrl+Shift+Y`, and a floating popup appears top-right with the summary, bullet-point details, and a link to the official website. Dismiss with `Escape`, the close button, or a click anywhere outside. Repeat lookups return instantly with a green "cached" badge (last 10 cached). On restricted pages like Google Drive, use `Ctrl+C` then `Ctrl+Shift+Y`.

### How It Works

Highlighted text is sent to a FastAPI backend on Vercel, which queries the Tavily Search API and parses results into a summary and eight structured data points. The popup renders on-page in 1–3 seconds. Repeat lookups hit an in-memory cache.

### Limitations

- **Ambiguous names** — May blend data from similarly-named companies (mitigated with exact-phrase matching)
- **Obscure companies** — May return "No information found" (Serper fallback active)
- **Cold starts** — First lookup after idle takes 3–5s (loading state shown)

### Planned

- Indian government startup database APIs (Startup India, MCA registry) for authoritative legitimacy data
- Improved disambiguation for shared company names
- Copy-to-clipboard on the popup for ATS note pasting
- Dark mode support

### Tech Stack

| Component | Technology |
|---|---|
| Extension | Chrome Manifest V3, vanilla JS |
| Backend | FastAPI (Python), Vercel |
| Search | Tavily API (primary), Serper (fallback) |
| Cache | In-memory LRU, 10 entries |
| Triggers | `Ctrl+Shift+Y`, toolbar icon, right-click context menu |
| Response | 1–3 seconds |
