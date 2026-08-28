---
description: Multi-agent project review — spawns a full expert team (PM, UI/UX, QA, Backend, BA, Navigation, Security) to audit the current project and produce a prioritized report
allowed-tools: Agent, Bash, Read, WebSearch, Write
---

Perform a comprehensive multi-agent review of the current project. Spawn a full expert team in parallel — each agent reviews from their own specialist lens and returns a prioritized findings report.

---

## Step 1 — Gather project context

Run all of these in parallel before doing anything else:

```bash
# Structure
ls -la

# Tech stack files (parentheses required for correct -maxdepth scoping)
find . -maxdepth 3 \( -name "*.json" -o -name "*.toml" -o -name "*.yaml" -o -name "*.yml" \) \
  ! -path "*/node_modules/*" ! -path "*/.git/*" ! -path "*/venv/*" | head -30

# Recent work
git log --oneline -15

# What changed recently
git diff HEAD~5...HEAD --stat

# Dependency files
find . -maxdepth 2 \( -name "package.json" -o -name "requirements.txt" -o -name "go.mod" \
  -o -name "Cargo.toml" -o -name "Gemfile" -o -name "pyproject.toml" \) \
  ! -path "*/node_modules/*" | head -10
```

Also read `CLAUDE.md` if it exists.

From these results, determine:

**A. Project summary** — 3–5 sentences: tech stack, purpose, recent changes. This will be injected into every agent prompt.

**B. Project type** — classify as one or more of:
- `fullstack` — has both frontend (HTML/JS/React/Vue/etc.) and backend
- `frontend-only` — only UI code, no server
- `backend-only` — API, CLI, library, or service with no user-facing UI
- `mobile` — iOS/Android/Flutter/React Native
- `data` — analytics, ML, data pipeline

**C. Agent selection** — based on project type, decide which agents to skip:
- Skip **Agent 2 (UI/UX)** if `backend-only` or `data`
- Skip **Agent 5 (Business Analyst)** if `backend-only` with no metrics/reporting surface
- Skip **Agent 6 (Navigation Auditor)** if `backend-only`, `data`, or `frontend-only` with a single page
- Run all other agents regardless of project type

---

## Step 2 — Spawn expert agents in parallel

Launch all selected agents **at the same time**. Pass the `project_context` string (from Step 1A) and `project_type` (from Step 1B) at the start of every agent prompt, like this:

```
PROJECT CONTEXT:
<your 3–5 sentence summary here>

PROJECT TYPE: <fullstack | frontend-only | backend-only | mobile | data>

Your role: <role description below>
...
```

Each agent must:
- Explore the actual codebase — read real files, run real commands — before writing findings
- Never give generic advice that could apply to any project
- Format every finding as:
  ```
  [P0|P1|P2|P3] file:line — Issue description. Recommendation.
  ```
  P0 = critical/blocking, P1 = high, P2 = medium, P3 = low/nice-to-have

---

### Agent 1 — PM (Product Manager) · model: sonnet

Role: data accuracy, feature completeness, workflow correctness, user-facing bugs.

Instructions:
- Map out the main user-facing features from routes, components, or screens
- For each feature: does it handle empty state, loading state, and error state?
- Check if form validations are user-friendly and complete
- Find features that are partially built (code exists but UI is unreachable or incomplete)
- Check copy/labels for accuracy — are field names, button labels, and messages sensible?
- Return: numbered findings with P0–P3 severity, grouped by feature area

---

### Agent 2 — UI/UX Designer · model: sonnet

*(Skip if project type is `backend-only` or `data`)*

Role: visual consistency, layout, interaction patterns, accessibility.

Instructions:
- Scan component/template files for spacing/alignment patterns — look for hard-coded pixel values that break consistency
- Check for missing focus states, hover states, and disabled states on interactive elements
- Look for color values — are they using a design token system or raw hex? Flag raw hex that doesn't match the apparent palette
- Check for accessibility basics: `alt` attributes on images, `aria-label` on icon buttons, keyboard navigation traps
- Identify dead-end flows: pages or modals with no clear exit path
- Check responsive design — are there fixed widths that will break on mobile?
- Flag quick wins (< 1 hr fix) with `[QUICK WIN]` prefix
- Return: findings split into "Quick Wins" and "Larger Issues"

---

### Agent 3 — QA Tester · model: sonnet

Role: race conditions, validation gaps, security surface, test coverage.

Instructions:
- Find all forms and API inputs — check for missing server-side validation (client-only validation is not enough)
- Look for async operations that run without loading indicators or error handling
- Check for XSS vectors: user input rendered as raw HTML, dangerouslySetInnerHTML, or unescaped template variables
- Look for missing null/undefined checks on data that comes from an API or user
- Find CSRF exposure: state-mutating endpoints that don't check origin or use tokens
- Check test files: what percentage of critical paths have tests? What's obviously untested?
- Look for race conditions: parallel async calls whose results are used without coordination
- Return: severity-ranked bugs and test gaps, with exact file locations

---

### Agent 4 — Backend Developer · model: sonnet

Role: performance, correctness, code quality, security.

Instructions:
- Find N+1 query patterns: loops that call the database or an API, ORM calls without `select_related`/`includes`/joins
- Look for multi-step writes (create + update + delete in sequence) without database transactions
- Check authentication and authorization: are protected routes actually checking auth? Can a user access another user's data by changing an ID?
- Find DRY violations: the same logic copy-pasted in 3+ places that should be a shared function
- Check error handling: are errors swallowed silently (bare `except`, `catch(e) {}`)? Are stack traces leaked to API responses?
- Look for missing database indexes on columns used in WHERE clauses or JOIN conditions
- Find dead code: functions, routes, or modules that are defined but never called
- Return: findings with file:line references, ordered P0 → P3

---

### Agent 5 — Business Analyst · model: haiku

*(Skip if project type is `backend-only` with no metrics/reporting surface)*

Role: KPI correctness, business logic accuracy, reporting integrity.

Instructions:
- Find all places where metrics, counts, sums, or percentages are calculated — verify the formula is correct
- Check date filter logic: are date ranges inclusive/exclusive correctly? Are timezone offsets applied? What happens on the first/last day of a month?
- Find business events that should be tracked but aren't (e.g. a checkout flow with no conversion event)
- Look for discrepancies: does the UI claim to show "total revenue" but the query only sums one product type?
- Check for off-by-one errors in pagination, ranking, or threshold logic
- Return: findings with business impact explained, not just technical description

---

### Agent 6 — Navigation & Feature Completeness Auditor · model: haiku

*(Skip if `backend-only` or `data`, or single-page frontend)*

Role: sitemap completeness, unreachable features, navigation consistency.

Instructions:
- Extract all defined routes (from router files, `urls.py`, `routes.rb`, Next.js pages, etc.)
- Extract all navigation links from sidebar, navbar, and menu components
- Cross-reference: are all routes reachable from the navigation? List orphaned routes
- Cross-reference: are all nav links pointing to real routes? List broken links
- Find features that exist in the codebase (components, pages, controllers) but are not linked anywhere
- Check breadcrumbs and back-navigation: do they accurately reflect the user's location?
- Propose a clean navigation structure if the current one has gaps
- Return: navigation map with gaps marked, list of orphaned routes, list of broken nav links

---

### Agent 7 — Security & DevOps Auditor · model: sonnet

Role: secrets exposure, infrastructure security, CI/CD gaps, dependency risks.

Instructions:
- Scan for hardcoded secrets: API keys, passwords, tokens, private keys in source files and config files
  ```bash
  grep -rE "(api_key|secret|password|token|private_key)\s*=\s*['\"][^'\"]{8,}" \
    --include="*.py" --include="*.js" --include="*.ts" --include="*.env" \
    --include="*.yaml" --include="*.yml" . 2>/dev/null | grep -v ".git" | head -30
  ```
- Check `.gitignore`: are `.env`, `secrets.*`, `*.pem`, `*.key` properly ignored?
- Look for `.env` or `secrets.*` files that were accidentally committed:
  ```bash
  git log --all --full-history -- "*.env" "*.pem" "*.key" "secrets*" 2>/dev/null | head -20
  ```
- Check Docker files: are secrets passed as ENV in Dockerfile (bad) vs build args or runtime env?
- Check CI/CD config (`.github/workflows/`, `.gitlab-ci.yml`, etc.): are secrets used correctly via CI variables, not hardcoded?
- Check dependency files for known-vulnerable package versions (flag any that are >2 major versions behind)
- Look for `DEBUG=True` or equivalent in production config paths
- Return: P0 for any confirmed secret exposure, P1 for misconfigurations, P2/P3 for hardening recommendations

---

## Step 3 — Filter false positives

After all agents return, for any finding you are uncertain about, quickly verify it against the actual code before including it in the report. Remove:
- Findings that reference code that doesn't exist (hallucinated file paths)
- Pre-existing issues that are clearly intentional (e.g. a comment saying "TODO: remove after migration")
- Duplicate findings across agents — keep the one with the most detail

---

## Step 4 — Compile and save the report

Create the directory `reviews/` if it doesn't exist. Save the full report to `reviews/project-review-YYYY-MM-DD.md` with this structure:

```markdown
# Project Review — <project name>
**Date:** <YYYY-MM-DD>
**Project type:** <fullstack | backend-only | etc.>
**Agents run:** <list of agents that were not skipped>
**Skipped:** <list of agents that were skipped and why>

---

## Critical Issues (P0)
<all P0 findings across all agents, deduplicated>

## High Priority (P1)
<all P1 findings across all agents, deduplicated>

---

## 1. PM Review
<agent 1 full findings>

## 2. UI/UX Designer Review
<agent 2 findings, or "Skipped — project type: backend-only">

## 3. QA Tester Review
<agent 3 full findings>

## 4. Backend Developer Review
<agent 4 full findings>

## 5. Business Analyst Review
<agent 5 findings, or "Skipped">

## 6. Navigation & Feature Completeness Audit
<agent 6 findings, or "Skipped">

## 7. Security & DevOps Audit
<agent 7 full findings>

---

## Top 10 Priority Issues (cross-team)
| # | Severity | Agent | Issue | File |
|---|----------|-------|-------|------|
| 1 | P0 | ... | ... | ... |
...
```

After saving, print **only** the following to the terminal:
1. The path to the saved report
2. All P0 findings (if any) — displayed prominently with a warning header
3. The "Top 10 Priority Issues" table

Do not print the full report to the terminal.

---

## Notes

- Every finding must cite a real file and line number. If you cannot find the file, do not include the finding.
- Do not recommend things that are already done correctly in the codebase.
- If the project has a `CLAUDE.md`, cross-check findings against any conventions documented there — violations of documented conventions are P1 minimum.
- To add a new agent or modify an existing one, edit `config/claude-skills/project-review.md` in the jarvis project and run `jarvis sys claude-skill` to redeploy.
