---
description: UI/UX design intelligence for web and mobile. Covers design system generation, 50+ styles, color palettes, font pairings, 99 UX guidelines, and 25 chart types across React, Next.js, Vue, Svelte, SwiftUI, React Native, Flutter, Tailwind, shadcn/ui, and HTML/CSS.
allowed-tools: Bash, Read, Write, WebSearch
---

# UI/UX Pro Max — Design Intelligence

Comprehensive design intelligence for building and reviewing UI across web and mobile platforms. Use this skill whenever the task involves UI structure, visual design decisions, interaction patterns, or UX quality.

## When to Apply

**Must use:**
- Designing new pages (landing page, dashboard, admin panel, SaaS, mobile app)
- Creating or refactoring UI components (buttons, modals, forms, tables, charts)
- Choosing color schemes, typography systems, spacing, or layout systems
- Reviewing UI code for UX, accessibility, or visual consistency
- Implementing navigation, animations, or responsive behavior

**Skip:**
- Pure backend logic, API-only, database, infrastructure, or DevOps work

**Decision rule:** If the task changes how something *looks, feels, moves, or is interacted with* — use this skill.

---

## Workflow

### Step 1 — Analyze Requirements

Extract from the user's request:
- **Product type**: SaaS / e-commerce / portfolio / dashboard / landing page / mobile app / healthcare / fintech / entertainment / wellness / education
- **Target audience**: consumer (age group, context) vs. professional
- **Tone keywords**: minimal, playful, luxurious, brutalist, dark, corporate, organic, vibrant
- **Tech stack**: React / Next.js / Vue / Svelte / Tailwind / shadcn/ui / SwiftUI / React Native / Flutter / HTML+CSS

### Step 2 — Generate Design System

Based on product type + tone, recommend a complete design system using the **Design System Matrix** below. Always output:

```
DESIGN SYSTEM: [Project Name]
─────────────────────────────
PATTERN:    [layout/content strategy — e.g. Hero-Centric + Social Proof]
STYLE:      [visual language — e.g. Soft UI / Glassmorphism / Minimalism]
PRIMARY:    #XXXXXX  [name] — [reason]
SECONDARY:  #XXXXXX  [name] — [reason]
CTA:        #XXXXXX  [name] — [reason]
BACKGROUND: #XXXXXX  [name]
TEXT:       #XXXXXX  [name]
HEADING:    [Font] — [character description]
BODY:       [Font] — [character description]
EFFECTS:    [shadows, blur, radius, animation style]
AVOID:      [anti-patterns specific to this product type]
```

#### Design System Matrix

**SaaS / Productivity**
- Style: Clean Minimalism or Flat Design
- Colors: Blue-dominant (#2563EB primary), neutral grays, white surfaces
- Fonts: Inter + Inter (or) Plus Jakarta Sans + DM Sans
- Pattern: Sidebar nav + content area, feature-grid sections
- Avoid: Heavy gradients, overly decorative elements, purple-on-white AI cliché

**Fintech / Banking**
- Style: Corporate Flat or Subtle Glassmorphism
- Colors: Deep navy (#0F172A), electric blue (#3B82F6), gold accent (#F59E0B)
- Fonts: Sora + Inter (or) IBM Plex Sans + IBM Plex Mono (for numbers)
- Pattern: Dashboard with KPI cards, data tables, charts
- Avoid: Playful fonts, bright neons, decorative animations

**Healthcare / Wellness**
- Style: Soft UI or Organic Minimalism
- Colors: Calm blue-green (#0EA5E9), sage (#A8D5BA), warm white (#FAFAFA)
- Fonts: Nunito + Source Sans 3 (or) Lato + Open Sans
- Pattern: Clean card layouts, progress indicators, reassuring empty states
- Avoid: Dark mode by default, aggressive reds, cluttered dashboards

**E-commerce / Retail**
- Style: Clean Flat or Modern Editorial
- Colors: Brand-forward primary, high-contrast CTA (#F97316 or #EF4444), neutral backgrounds
- Fonts: Playfair Display + Lato (luxury) or Outfit + Inter (modern)
- Pattern: Product grid, sticky CTA, progressive disclosure in checkout
- Avoid: More than 3 font sizes in listings, hidden shipping costs UX

**Luxury / Beauty / Spa**
- Style: Soft UI Evolution or Refined Minimalism
- Colors: Warm rose (#E8B4B8), sage green (#A8D5BA), gold (#D4AF37), warm white (#FFF5F5)
- Fonts: Cormorant Garamond + Montserrat (or) Playfair Display + Raleway
- Pattern: Hero-centric, testimonials, booking CTA, generous whitespace
- Avoid: Bright neon, dark mode, heavy animations, AI purple gradients

**Entertainment / Gaming**
- Style: Dark Glassmorphism or Neon Brutalism
- Colors: Deep black/navy base, electric accent (#7C3AED or #06B6D4 or #F59E0B)
- Fonts: Rajdhani + Exo 2 (or) Bebas Neue + Roboto
- Pattern: Immersive hero, content-grid, badge/reward system
- Avoid: Light backgrounds, serif fonts, corporate flatness

**Portfolio / Creative**
- Style: Bold Minimalism or Brutalism or Bento Grid
- Colors: High-contrast black/white base + one strong accent
- Fonts: Space Grotesk + Syne (or) Clash Display + Satoshi
- Pattern: Project showcase grid, case study detail, about/contact
- Avoid: Generic blue SaaS look, overly colorful distractions

**Landing Page (generic)**
- Style: Match product industry above
- Pattern: Hero → Social proof → Features → Pricing → CTA → Footer
- Always: Above-fold CTA, trust badges, mobile-first layout

**Dashboard / Admin**
- Style: Clean Flat or Subtle Depth
- Colors: Neutral base (slate-50/100 background), blue primary, semantic status colors
- Fonts: Inter + Inter Mono (for data)
- Pattern: Sidebar navigation, KPI cards, data table + chart pairing
- Avoid: Decorative animations on data, color-only status indicators

**Mobile App (iOS / Android / React Native / Flutter)**
- Follow platform idioms: iOS → HIG conventions; Android → Material Design 3
- Style: Match product type above, but adapt for platform
- Avoid: Web-specific hover interactions, non-native-feeling controls

---

### Step 3 — Apply Domain Guidelines

Use the relevant section from the rules below when implementing or reviewing.

---

## Rules Reference (99 UX Guidelines)

### 1. Accessibility — CRITICAL

- Minimum 4.5:1 contrast ratio for body text; 3:1 for large text (WCAG AA)
- Visible focus rings on all interactive elements (2–4px outline)
- Descriptive `alt` text on all meaningful images
- `aria-label` on icon-only buttons; `accessibilityLabel` in native apps
- Tab order matches visual reading order; full keyboard navigation
- `<label for>` on every form input — never placeholder-only
- Heading hierarchy is sequential (h1→h2→h3, no skipping)
- Never convey information by color alone — add icon or text
- Support `prefers-reduced-motion` — disable/reduce animations when requested
- Provide skip-to-main-content link for keyboard users
- Screen reader reading order is logical; VoiceOver/TalkBack traversal works
- All modals and sheets have a clear dismiss/cancel affordance

### 2. Touch & Interaction — CRITICAL

- Minimum touch target: 44×44pt (iOS) / 48×48dp (Android)
- Minimum 8px gap between adjacent touch targets
- Never rely on hover-only for primary interactions
- Disable button and show spinner during async operations
- Show error messages near the problem element, not only at top
- `cursor: pointer` on all clickable elements (web)
- Use `touch-action: manipulation` to eliminate 300ms tap delay
- Avoid requiring precise taps on small icons without expanded hit area
- Swipe actions must show a visual affordance or hint
- Provide real-time visual tracking for drag/swipe gestures
- Use a movement threshold before initiating drag (prevents accidental drags)
- Keep primary touch targets away from notch, Dynamic Island, home gesture bar
- Use haptic feedback for confirmations — avoid overuse

### 3. Performance — HIGH

- Use WebP/AVIF for images; declare `width`/`height` to prevent layout shift (CLS)
- Lazy-load all below-the-fold images and heavy media
- `font-display: swap` or `optional` to avoid invisible text (FOIT)
- Preload only critical fonts (max 2 variants)
- Split code by route/feature; avoid loading everything upfront
- Load third-party scripts `async`/`defer`
- Virtualize lists with 50+ items
- Keep per-frame work under ~16ms for 60fps; move heavy work off main thread
- Use skeleton screens / shimmer for operations >1s — not a blocking spinner
- Debounce/throttle high-frequency events (scroll, resize, input)
- Provide offline state messaging and graceful network degradation
- Reserve space for async content to prevent Cumulative Layout Shift

### 4. Style Selection — HIGH

- Match visual style to product type (use Design System Matrix above)
- Use the same style consistently across all pages — no mixing
- Use SVG icons (Heroicons, Lucide, Phosphor) — never emojis as structural icons
- Use one icon set with consistent stroke width and corner radius throughout
- Shadows, blur, border-radius must align with chosen style
- Each screen has exactly one primary CTA; secondary actions are visually subordinate
- Hover / pressed / disabled states are visually distinct within the style
- Design light and dark variants together — don't invert light mode colors for dark
- Use system/native controls where possible; only customize when branding requires it
- Use blur to indicate background dismissal (modals, sheets) — not pure decoration

### 5. Layout & Responsive — HIGH

- `<meta name="viewport" content="width=device-width, initial-scale=1">` — never disable zoom
- Design mobile-first, then scale up to tablet (768px) and desktop (1024px / 1440px)
- Use systematic breakpoints: 375 / 768 / 1024 / 1440
- Minimum 16px body text on mobile (prevents iOS auto-zoom)
- Line length: 35–60 chars/line mobile; 60–75 chars/line desktop
- No horizontal scroll on mobile
- 4pt/8dp spacing increment system (Material Design)
- Consistent max-width on desktop (max-w-6xl / 7xl)
- Define a z-index scale: 0 / 10 / 20 / 40 / 100 / 1000
- Fixed navbar/bottom bar must offset underlying content with correct padding
- Prefer `min-h-dvh` over `100vh` on mobile
- Test landscape orientation — layout must remain readable and operable
- Avoid nested scroll regions that interfere with main scroll

### 6. Typography & Color — MEDIUM

- Base body font size: 16px minimum
- Line-height: 1.5–1.75 for body text
- Font scale: consistent steps — e.g. 12 / 14 / 16 / 18 / 24 / 32 / 48
- Font-weight hierarchy: headings 600–700, body 400, labels 500
- Define semantic color tokens (primary, secondary, error, surface, on-surface) — never raw hex in components
- Dark mode: use desaturated / lighter tonal variants — not inverted colors
- All foreground/background pairs must meet 4.5:1 (AA) or 7:1 (AAA)
- Functional color (error red, success green) must include icon/text — not color-only meaning
- Prefer wrapping over truncation; when truncating use ellipsis + tooltip
- Use tabular/monospaced figures for prices, data columns, timers
- Use whitespace intentionally to group and separate — avoid visual clutter
- Avoid Inter/Roboto/Arial/system fonts + purple gradient on white (AI cliché)

### 7. Animation — MEDIUM

- Duration: 150–300ms for micro-interactions; max 400ms for complex transitions
- Animate only `transform` and `opacity` — never `width`/`height`/`top`/`left`
- Easing: `ease-out` for entering; `ease-in` for exiting — never linear
- Prefer spring/physics-based curves for natural feel
- Exit animations should be 60–70% of enter duration (feels responsive)
- Stagger list/grid entrance by 30–50ms per item
- Every animation must express cause-effect — no purely decorative animation
- State transitions (hover, expand, modal) animate smoothly — never snap
- Page transitions maintain spatial continuity (directional slide or shared element)
- Animations must be interruptible — user tap cancels in-progress animation
- Never block user input during animation
- Use crossfade for content replacement within the same container
- Subtle scale (0.95–1.05) on press for tappable cards/buttons
- Respect `prefers-reduced-motion` — disable or reduce all animations

### 8. Forms & Feedback — MEDIUM

- Every input has a visible label — never placeholder-only
- Show errors below the related field (not only a summary at top)
- Mark required fields (asterisk or explicit label)
- Show loading then success/error state on every form submit
- Validate on blur — not on every keystroke
- Error messages must state the cause and how to fix it (not just "Invalid input")
- Use semantic input types (`email`, `tel`, `number`) to trigger correct mobile keyboard
- Provide show/hide toggle for password fields
- Support `autocomplete` / `textContentType` attributes for system autofill
- Auto-save long form drafts to prevent data loss
- Confirm before dismissing a sheet/modal with unsaved changes
- Multi-step flows show step indicator; allow back navigation
- After submit error, auto-focus the first invalid field
- Toasts auto-dismiss in 3–5s; use `aria-live="polite"` — don't steal focus
- Confirm before destructive actions (delete, clear all)
- `disabled` elements: 0.38–0.5 opacity + cursor change + semantic attribute
- Empty states show a helpful message and action — never a blank space

### 9. Navigation Patterns — HIGH

- Bottom navigation: max 5 items, always show icon + text label
- Use drawer/sidebar for secondary navigation — not primary actions
- Back navigation must be predictable; preserve scroll position and filter state
- All key screens reachable via deep link / URL
- iOS: Tab Bar at bottom for top-level nav (Apple HIG)
- Android: Top App Bar with nav icon for primary structure (Material Design)
- Current location is visually highlighted in navigation (color, weight, indicator)
- Modals must have a clear close affordance; swipe-down to dismiss on mobile
- Breadcrumbs on web for 3+ level deep hierarchies
- Support system gesture navigation (iOS swipe-back, Android predictive back)
- Bottom nav is for top-level screens only — never nest sub-navigation inside it
- Large screens (≥1024px): prefer sidebar; small screens: bottom/top nav
- Never mix Tab + Sidebar + Bottom Nav at the same hierarchy level
- Modals must not be used for primary navigation flows
- After route change, move focus to main content region (screen reader)
- Core navigation must remain reachable from deep pages
- Dangerous actions (delete account, logout) are visually and spatially separated from normal nav

### 10. Charts & Data Visualization — MEDIUM

- Match chart type to data type:
  - Trend over time → Line chart
  - Category comparison → Bar / Column chart
  - Part-of-whole → Pie / Donut (max 5 categories)
  - Distribution → Histogram
  - Correlation → Scatter plot
  - Flow / funnel → Funnel chart
  - Hierarchy → Treemap
- Use accessible color palettes — avoid red/green only pairs (colorblind)
- Supplement color with patterns, shapes, or textures
- Always show legend; position near the chart — not below a scroll fold
- Provide tooltip/data labels on hover (web) or tap (mobile)
- Label axes with units; avoid rotated labels on mobile
- Charts must reflow or simplify on small screens
- Show meaningful empty state when no data — not a blank axis frame
- Use skeleton/shimmer while chart data loads
- Respect `prefers-reduced-motion` for chart entrance animations
- Virtualize / aggregate for 1000+ data points
- Data lines/bars vs background ≥3:1 contrast; data text labels ≥4.5:1
- Legends should be clickable to toggle series visibility
- Interactive chart elements must have ≥44pt tap area on mobile
- Provide CSV/image export option for data-heavy products
- For data tables: support sorting with `aria-sort`; keep columns keyboard-navigable

---

## Common Professional UI Rules

### Icons

| Rule | Do | Avoid |
|------|----|-------|
| Icon type | SVG vector icons (Lucide, Heroicons, Phosphor) | Emojis as structural icons |
| Sizing | Design tokens: icon-sm / icon-md (24pt) / icon-lg | Arbitrary mixed sizes |
| Stroke | Consistent stroke width (1.5px or 2px throughout) | Mixed thick/thin strokes |
| Style | One style per hierarchy level (all filled or all outline) | Mixing filled + outline at same level |
| Touch target | Min 44×44pt hit area — use `hitSlop` if icon is smaller | Icon-only tap without expanded area |
| Contrast | 4.5:1 for small icons; 3:1 for large UI glyphs | Low-contrast icons |
| Alignment | Aligned to text baseline; consistent padding | Misaligned or inconsistently spaced icons |

### Interaction States (Every Interactive Element)

| State | Visual Treatment |
|-------|-----------------|
| Default | Base style |
| Hover (web) | Subtle background tint or underline — cursor: pointer |
| Pressed / Active | Scale 0.95–0.98 or opacity 0.85; ripple on Android |
| Focus | 2–4px outline ring (never remove!) |
| Disabled | 0.38–0.5 opacity + cursor: not-allowed + `disabled` attr |
| Loading | Spinner / skeleton replacing content; button disabled |
| Error | Red border + error message below + aria-describedby |
| Success | Brief checkmark or toast — not a blocking modal |

### Pre-Delivery Checklist

Before marking UI work as done, verify:

- [ ] All touch targets ≥44pt; no content hidden behind safe areas
- [ ] Contrast ratios pass WCAG AA (4.5:1 body, 3:1 large text)
- [ ] Focus rings visible; keyboard navigation works end-to-end
- [ ] No horizontal scroll on 375px viewport
- [ ] Landscape orientation layout is readable
- [ ] Dark mode contrast verified independently (not just inverted)
- [ ] `prefers-reduced-motion` disables/reduces all animations
- [ ] All forms: labels visible, errors actionable, submit has loading state
- [ ] Empty states have message + action
- [ ] No raw hex in components — semantic color tokens only
- [ ] Icons are SVG vector — no emojis used as UI elements
- [ ] Dynamic Type / system text scaling does not break layout

---

## Quick Troubleshooting

| Problem | Check These Rules |
|---------|------------------|
| UI looks generic / AI-sloppy | §4 Style Selection + Design System Matrix — pick a bold direction |
| Dark mode broken | §6 `color-dark-mode` + `color-accessible-pairs` |
| Animations feel unnatural | §7 `spring-physics` + `easing` + `exit-faster-than-enter` |
| Form UX is poor | §8 `inline-validation` + `error-clarity` + `focus-management` |
| Navigation confusing | §9 `nav-hierarchy` + `bottom-nav-limit` + `back-behavior` |
| Layout breaks on small screen | §5 `mobile-first` + `breakpoint-consistency` + `horizontal-scroll` |
| Performance / jank | §3 `virtualize-lists` + `main-thread-budget` + `debounce-throttle` |
| Charts hard to read | §10 — check chart type match, color accessibility, legend placement |
| Icons look inconsistent | Icons table above — check style, stroke, sizing tokens |

---

## Review Mode

When asked to **review** existing UI (not build new), run through these checks in order:

1. **Critical** — §1 Accessibility + §2 Touch targets (fix these first; they're P0/P1)
2. **High** — §4 Style consistency + §5 Layout/responsive + §9 Navigation
3. **Medium** — §6 Typography/color tokens + §7 Animations + §8 Forms
4. **Polish** — Icons table + Interaction States table + Pre-Delivery Checklist

Report findings as:
```
[P0|P1|P2|P3] file:line — Issue. Recommendation.
```
