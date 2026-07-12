# Evidence-First Harness Landing Page — Implementation Plan

> **For Hermes:** Use subagent-driven-development or Codex CLI to implement this plan task-by-task.

**Goal:** Build a single-page SvelteKit 5 static landing page for the Evidence-First Harness project, deployed to GitHub Pages at `rmax-ai.github.io/evidence-first-harness`, using a dark developer-tool aesthetic (Linear / Vercel style).

**Architecture:** SvelteKit 5 + Tailwind CSS v4 + @sveltejs/adapter-static. Pre-rendered statically with no client-side JS framework overhead. Hand-written SVG pipeline diagram (no mermaid.js). Shared data file for metrics, stack, pricing table. Component tree: shell layout → page orchestrator → section components.

**Design Language:** "Deterministic Emerald" — dark, high-density, monospaced-heavy aesthetic. Emerald green accent for "pass" indicators and cryptographic certainty. Rejects soft SaaS gradients in favor of raw, command-line-inspired precision. Strict 1px borders, `rounded-sm` (2px) corners only, alternating row tints, index columns on all tables.

**Tech Stack:** Svelte 5 (runes), TypeScript, Tailwind v4 (Vite plugin), pnpm, adapter-static → `docs/` output, GitHub Pages.

---

## Acceptance Criteria

- [ ] `pnpm build` completes without errors, outputs to `docs/`
- [ ] `docs/index.html` exists and is a complete static page
- [ ] Page renders dark theme correctly (bg-slate-950, no light mode toggle)
- [ ] Pipeline SVG diagram is embedded and visually clear (spec → plan → impl → evidence → decision)
- [ ] Agent model routing table shown with live/stub status indicators
- [ ] Pricing table ($/1M tokens) matches `state.py` values
- [ ] Smoke test output displayed in styled code block
- [ ] Architecture boundary table (deterministic vs LLM) shown
- [ ] Mobile responsive — all sections readable at 375px width
- [ ] GitHub Pages deploy: `docs/.nojekyll` present, `_app/` directory served correctly
- [ ] No client-side JS errors (prerendered static — only CSS + HTML)
- [ ] All external links (GitHub repo, license) open correctly

---

## Implementation Tasks

All tasks under `site/` subdirectory of the harness repo.

### Task 1: Scaffold SvelteKit 5 project with Tailwind v4

**Objective:** Create the project skeleton with correct configs.

**Files:**
- Create: `site/package.json`
- Create: `site/svelte.config.js`
- Create: `site/vite.config.ts`
- Create: `site/tsconfig.json`
- Create: `site/src/app.html`
- Create: `site/src/app.css`
- Create: `site/src/routes/+layout.ts`
- Create: `site/src/routes/+layout.svelte`
- Create: `site/src/lib/data/meta.ts`

**Step 1: Scaffold SvelteKit**

```bash
cd site
npx sv create . --template minimal --types ts --no-add-ons
pnpm add -D @sveltejs/adapter-static tailwindcss @tailwindcss/vite
```

**Step 2: Configure svelte.config.js**

```js
import adapter from "@sveltejs/adapter-static";
const config = {
  kit: {
    adapter: adapter({ pages: "../docs", assets: "../docs", fallback: undefined }),
    paths: { base: "/evidence-first-harness" },
  },
};
export default config;
```

**Step 3: Configure vite.config.ts**

```ts
import tailwindcss from "@tailwindcss/vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";
export default defineConfig({ plugins: [tailwindcss(), sveltekit()] });
```

**Step 4: Wire Tailwind import**

Create `src/app.css`:
```css
@import "tailwindcss";
```

**Step 5: Set dark theme in app.html**

```html
<!doctype html>
<html lang="en" class="bg-slate-950">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Evidence-First Harness</title>
    <meta name="description" content="Deterministic assurance system for AI-generated code." />
    %sveltekit.head%
  </head>
  <body class="bg-slate-950 text-slate-300 font-sans antialiased">%sveltekit.body%</body>
</html>
```

**Step 6: Set prerender + trailingSlash**

Create `src/routes/+layout.ts`:
```ts
export const prerender = true;
export const trailingSlash = "always";
```

**Step 7: Create shared data module**

Create `src/lib/data/meta.ts` with project constants: version (`v0.1.0`), stack list, agent routing table (names + live/stub status), pricing table, evidence tiers, CLI commands.

**Step 8: Verify scaffold builds**

```bash
cd site && pnpm build
```
Expected: builds without error, `docs/index.html` exists.

**Step 9: Commit**

---

### Task 2: Build shell layout and hero section

**Objective:** Create the global layout shell and hero banner.

**Files:**
- Modify: `site/src/routes/+layout.svelte`
- Create: `site/src/lib/components/ui/Section.svelte`
- Create: `site/src/lib/components/sections/Hero.svelte`

**Step 1: Layout shell**

```svelte
<script>
  import "../app.css";
  let { children } = $props();
</script>

<header class="fixed top-0 w-full z-50 backdrop-blur-sm bg-slate-950/80 border-b border-slate-800">
  <nav class="max-w-4xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
    <span class="text-white font-semibold text-sm tracking-tight">Evidence-First Harness</span>
    <a href="https://github.com/rmax-ai/evidence-first-harness" class="text-slate-400 hover:text-white text-sm">GitHub →</a>
  </nav>
</header>

<main class="pt-14">
  {@render children?.()}
</main>

<footer class="border-t border-slate-800 py-8 text-center text-slate-600 text-xs">
  Evidence-First Harness · MIT License · <a href="https://github.com/rmax-ai/evidence-first-harness" class="hover:text-slate-400">GitHub</a>
</footer>
```

**Step 2: Section wrapper component**

```svelte
<script lang="ts">
  let { tag = "section", children }: { tag?: string; children?: import("svelte").Snippet } = $props();
</script>
<svelte:element this={tag} class="py-16 px-4 sm:px-6 max-w-4xl mx-auto">
  {@render children?.()}
</svelte:element>
```

**Step 3: Hero section**

- Title: "Evidence-First Harness"
- Subtitle: "Deterministic assurance for AI-generated code"
- Principle quote block
- Status badge + 73 tests + 18 commits
- Two CTA buttons: "Run Smoke Test" → `#smoke-test`, "View on GitHub" → external

**Step 4: Commit**

---

### Task 3: Build pipeline SVG diagram

**Objective:** Hand-write an SVG flowchart showing the 17-node evidence pipeline.

**Files:**
- Create: `site/static/pipeline.svg`

**Step 1: Design the flow**

```
[Spec → Opus 4.6] → [Plan → Sonnet 5] → [Impl → DeepSeek]
   → [Impact Analysis] → [Evidence Checks ×5]
   → [Adversarial Review] → [Independent Review]
   → [Decision Engine → accept/reject/repair]
```

**Step 2: Write SVG**

Use the skill's color palette:
```
Background: fill="#0f172a" (slate-900)
Node fill:  fill="#1e293b" (slate-800)
Node stroke: stroke="#334155" (slate-700)
Text:       fill="#e2e8f0" (slate-200)
Arrows:     stroke="#6366f1" (indigo-500)
Fail path:  stroke="#ef4444" (red-500), dashed
Pass path:  stroke="#22c55e" (green-500)
```

Layout: 3 rows × 6-7 columns. Each node is a rounded rectangle with label + model name. Arrows between them. Color-code LLM nodes (indigo border) vs deterministic nodes (slate border).

**Step 3: Embed in Section component**

Reference with `{base}/pipeline.svg` from `$app/paths`.

**Step 4: Verify** — `pnpm build`, check `docs/pipeline.svg` exists.

**Step 5: Commit**

---

### Task 4: Build architecture and model routing sections

**Objective:** Display the deterministic vs probabilistic boundary table and agent model routing.

**Files:**
- Create: `site/src/lib/components/sections/Architecture.svelte`
- Create: `site/src/lib/components/sections/ModelRouting.svelte`

**Step 1: Architecture boundary table**

Two-column layout: Component | Type | Controls. Highlight "Deterministic" rows with green-left-border, "LLM" rows with indigo-left-border.

**Step 2: Agent model routing table**

Columns: Agent | Model | Provider | Live? | Typical Tokens. Use colored badges (green "Live" / amber "Stub") for status.

**Step 3: Pricing table**

Columns: Model | Input $/1M | Output $/1M. Sourced from `meta.ts`.

**Step 4: Commit**

---

### Task 5: Build smoke test and evidence tiers sections

**Objective:** Display the smoke test output and evidence tier table.

**Files:**
- Create: `site/src/lib/components/sections/SmokeTest.svelte`
- Create: `site/src/lib/components/sections/EvidenceTiers.svelte`

**Step 1: Smoke test section**

- Show the exact `efh run --repo .` command in a styled code block
- Below: the cost summary table (agent | model | in | out | cost) from the README
- Link to full output

**Step 2: Evidence tiers section**

Three-tier table with colored tier badges:
- Tier 3 (green): automated approval
- Tier 2 (amber): code owner approval
- Tier 1 (red): code owner + security owner

**Step 3: Quick start commands**

```bash
uv sync --extra dev
uv run pytest tests/ -q        # 73 tests
uv run efh run --repo .         # Full E2E
```

**Step 4: Commit**

---

### Task 6: Wire page orchestrator and polish

**Objective:** Assemble all sections into the page, add final polish.

**Files:**
- Modify: `site/src/routes/+page.svelte`

**Step 1: Page orchestrator**

Import all section components. Order:
1. Hero
2. Pipeline diagram
3. Architecture boundary table
4. Agent model routing + pricing
5. Smoke test output
6. Evidence tiers
7. Quick start

**Step 2: Add inter-section spacing and scroll anchors**

Each section gets an `id` for anchor linking from the hero CTAs.

**Step 3: Responsive polish**

Test at 375px, 768px, 1024px widths. Tables may need horizontal scroll. Pipeline SVG should scale with `w-full h-auto`.

**Step 4: Remove boilerplate**

Delete SvelteKit default files (`Counter.svelte`, etc.) that ship with `--template minimal`.

**Step 5: Build and verify**

```bash
cd site && pnpm build
```

Expected: clean build, `docs/` populated with `index.html`, `pipeline.svg`, `_app/` directory.

```bash
touch docs/.nojekyll
ls docs/index.html docs/pipeline.svg docs/.nojekyll docs/_app/
```

**Step 6: Commit and push**

---

### Task 7: GitHub Pages deploy

**Objective:** Configure GitHub Pages to serve from `docs/` directory.

**Step 1: Verify output**

```bash
ls docs/index.html docs/.nojekyll
```

**Step 2: Push to `main`**

```bash
git add site/ docs/
git commit -m "feat: landing page — SvelteKit 5 static, dark theme, SVG pipeline"
git push
```

**Step 3: Enable GitHub Pages**

Via GitHub UI: Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs` → Save.

Or via CLI:
```bash
gh api repos/rmax-ai/evidence-first-harness/pages -X POST -f 'source[branch]=main' -f 'source[path]=/docs'
```

**Step 4: Verify deployment**

Wait ~30s for build. Visit `https://rmax-ai.github.io/evidence-first-harness/`. Check:
- Page loads dark theme
- Pipeline SVG renders
- All tables visible
- Mobile responsive

**Step 5: Commit any fixes**

---

## Open Questions

1. **Design system choice:** Default to Linear-like dark theme (precise, developer-tool aesthetic). Alternates: Supabase (emerald accent), Vercel (Geist font, b/w). Settle on one — no mixing.
2. **Font:** Geist (Google Fonts, available via CDN) or Inter? Geist matches Vercel/Linear style. Both free.
3. **Light mode?** No — always dark. Matches project identity (developer tooling, terminal-native).
4. **Analytics?** Skip for now — not needed for project landing page.

---

## Execution Notes

- **Framework decision:** SvelteKit static → GitHub Pages `docs/` — no server, no CDN config, free.
- **No mermaid.js:** Hand-write SVG pipeline diagram. ~1MB bundle savings, no client JS.
- **Shared data:** `meta.ts` is the single source of truth for all tables/metrics.
- **Deploy flow:** `pnpm build` → `touch docs/.nojekyll` → `git push` → GitHub Pages auto-deploys.
- **Site lives in repo:** `site/` subdirectory, output to `docs/`. No separate repo needed.

---

## Design Specification (from Gemini 3.5 Flash with Thinking)

### Design Language: "Deterministic Emerald"

Platform engineers and AI infrastructure architects value auditability, determinism, and speed. This design uses razor-sharp `rounded-sm` (2px) corners, strict 1px solid borders, monospaced typography for all data, and an uncompromising dark palette. The primary accent is a high-visibility Emerald, symbolizing passed tests, verified signatures, and cryptographic certainty.

### Color Palette

| Token | Hex | Tailwind v4 | Purpose |
|-------|-----|-------------|---------|
| Canvas BG | `#030712` | `bg-slate-950` | Main page background |
| Surface | `#0b0f19` | `bg-slate-900/60` | Cards, table headers, containers |
| Terminal BG | `#020617` | `bg-slate-950` | Code blocks, CLI output (deepest black) |
| Border Muted | `#1e293b` | `border-slate-800` | Grid lines, standard borders |
| Border Active | `#0f766e` | `border-teal-700` | Hover states, focus borders |
| Text Primary | `#f8fafc` | `text-slate-50` | Headings, critical readouts |
| Text Secondary | `#94a3b8` | `text-slate-400` | Body text, descriptions, labels |
| Text Muted | `#475569` | `text-slate-600` | Table indexes, inactive states |
| Accent Primary | `#10b981` | `text-emerald-500` | Pass indicators, CTAs, key metrics |
| Accent Muted | `#064e3b` | `bg-emerald-950/50` | Badge backgrounds, active row highlights |
| Warning/Alert | `#f59e0b` | `text-amber-500` | LLM-agent steps, unverified warnings |

### Typography

- **UI & Body:** Geist Sans or Inter (sans-serif)
- **Data & Code:** Geist Mono or JetBrains Mono (monospace) — used for ALL tables, CLI commands, model names, and metrics

| Level | Size | Weight | Tracking | Class |
|-------|------|--------|----------|-------|
| H1 (Hero) | 32px | semibold | -0.02em | `leading-tight` |
| H2 (Sections) | 20px | medium | -0.01em | `leading-snug` |
| H3 (Cards) | 16px | medium | normal | `leading-normal` |
| Body | 14px | normal | normal | Slate-400, `leading-relaxed` |
| Mono/Data | 12px | normal | normal | Monospace, `leading-none` |

### Component Decisions

**Data Tables** — `rounded-none`, 1px solid border (`#1e293b`). Header row dark background, 36px row height for density. Alternating rows: `bg-slate-900/20`. Every row starts with an index column `[01]`, `[02]` in `text-slate-600` for ledger-like precision.

**Code Blocks** — Header bar with mock filepath/command on left (`sharn@evidence-harness: ~`) and execution time on right (`1.24s`) in monospace. No window controls (no macOS dots). 2px vertical emerald accent line on left border. Solid block cursor in emerald.

**Badges** — Strictly rectangular (`rounded-sm`). Solid 1px border matching status color + 10% opacity background. Example: deterministic badge — border `#10b981`, text `#10b981`, bg `rgba(16,185,129,0.1)`.

### Layout (Single Page, 5 Sections)

```
┌────────────────────────────────────────────────────────┐
│ [Header: Brand Logo | Docs | GitHub | Discord]          │
├────────────────────────────────────────────────────────┤
│ 1. Hero — Title, quote box (bordered, left-accent), CTAs│
├────────────────────────────────────────────────────────┤
│ 2. Quick Start + Terminal Smoke Test (2-column grid)    │
│    Left: Quick start commands (uv, pytest)              │
│    Right: Real CLI output + token cost table            │
├────────────────────────────────────────────────────────┤
│ 3. Pipeline Diagram — 17-node workflow visualizer       │
│    Deterministic nodes (Emerald) vs Agent nodes (Amber) │
├────────────────────────────────────────────────────────┤
│ 4. Architecture Boundary + Model Routing (tabbed/grid)  │
│    Left: Deterministic vs LLM table                     │
│    Right: Agent routing + cost-per-token table          │
├────────────────────────────────────────────────────────┤
│ 5. Evidence Tiers Matrix — 3-column comparison grid     │
└────────────────────────────────────────────────────────┘
```

Max width: `max-w-6xl` (1152px) centered with `px-6`. Section spacing: strict `py-16`.

### Visual Differentiators

1. **Container grid guides** — 1px dotted vertical lines on left/right container margins (`#1e293b`), giving a structural blueprint / engineering schematic feel.
2. **Evidence Verified seal** — subtle absolute-positioned cryptographic hash watermark in section backgrounds: `SHA256: 8f4a7c...` rendered in low-opacity monospace.
3. **Interactive trace highlight** — hovering a row in the Architecture Boundary table highlights the corresponding node in the Pipeline Diagram via CSS `transition-colors duration-150`.
