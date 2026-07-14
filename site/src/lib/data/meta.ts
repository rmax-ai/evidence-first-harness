// Shared data for the Evidence-First Harness landing page.
// Single source of truth — components import from here.
// Pricing updated 2026-07-14 from official provider docs.

export const PROJECT = {
  name: "Evidence-First Harness",
  version: "v0.1.0",
  repo: "https://github.com/rmax-ai/evidence-first-harness",
  license: "MIT",
};

export const PRINCIPLE =
  "No agent-generated change may be accepted unless every material claim introduced by the change is linked to sufficient, reproducible, risk-adjusted evidence.";

// Source links for pricing claims
export const PRICING_SOURCES: Record<string, string> = {
  anthropic: "https://docs.anthropic.com/en/docs/about-claude/pricing",
  anthropic_sonnet5: "https://www.anthropic.com/news/claude-sonnet-5",
  openai: "https://developers.openai.com/api/docs/models/gpt-5.6-terra",
  gemini: "https://ai.google.dev/pricing",
};

export const STACK = [
  "Python 3.12+",
  "Google ADK 2.0",
  "Pydantic v2",
  "Structlog",
  "LiteLLM",
  "Docker sandbox",
];

export const STATUS_LINE = "Alpha-stage prototype · Phase 6 checkpoint · v0.1.0 · MIT License";

export const STATUS_CAVEAT =
  "Repository metrics reflect the current public repository state at the time of publication and may change.";

export const METRICS = [
  { label: "85", desc: "Unit tests", source: `${PROJECT.repo}` },
  { label: "MIT", desc: "License", source: `${PROJECT.repo}/blob/main/LICENSE` },
  { label: "3/6", desc: "LLM agents live", source: `${PROJECT.repo}` },
  { label: "9", desc: "Evidence executors", source: `${PROJECT.repo}` },
  { label: "$0.505", desc: "Recorded run", source: `${PROJECT.repo}#smoke-test` },
  { label: "17", desc: "Workflow nodes", source: `${PROJECT.repo}` },
];

export interface AgentRow {
  agent: string;
  model: string;
  provider: string;
  live: boolean;
  inTokens: number;
  outTokens: number;
}

export const AGENT_ROUTING: AgentRow[] = [
  { agent: "Specification", model: "claude-sonnet-5", provider: "Anthropic", live: true, inTokens: 13570, outTokens: 4096 },
  { agent: "Planner", model: "claude-opus-4-6", provider: "Anthropic", live: true, inTokens: 11871, outTokens: 2015 },
  { agent: "Implementation", model: "gpt-5.6-terra", provider: "OpenAI", live: true, inTokens: 11393, outTokens: 3007 },
  { agent: "Independent Test", model: "claude-haiku-4-5", provider: "Anthropic", live: false, inTokens: 0, outTokens: 0 },
  { agent: "Adversarial Review", model: "gemini-3.5-flash", provider: "Google", live: false, inTokens: 0, outTokens: 0 },
  { agent: "Explanation", model: "gemini-3.5-flash", provider: "Google", live: false, inTokens: 0, outTokens: 0 },
];

export const AGENT_FOOTNOTE = "Recorded in run_c6ec67e305e0. Implementation proposals use strict JSON Schema Structured Outputs; the harness validates and applies the returned unified diff.";

export interface PricingRow {
  model: string;
  inputPrice: number;
  outputPrice: number;
  note: string;
  source?: string;
}

// Pricing as of 2026-07-14. Sources: provider API pricing pages.
export const PRICING: PricingRow[] = [
  {
    model: "claude-opus-4-6",
    inputPrice: 15.00,
    outputPrice: 75.00,
    note: "",
    source: PRICING_SOURCES.anthropic,
  },
  {
    model: "claude-sonnet-5",
    inputPrice: 3.00,
    outputPrice: 15.00,
    note: "",
    source: PRICING_SOURCES.anthropic_sonnet5,
  },
  {
    model: "claude-haiku-4-5",
    inputPrice: 0.80,
    outputPrice: 4.00,
    note: "",
    source: PRICING_SOURCES.anthropic,
  },
  {
    model: "gpt-5.6-terra",
    inputPrice: 2.50,
    outputPrice: 15.00,
    note: "Balanced GPT-5.6 model. Structured Outputs enabled for implementation proposals.",
    source: PRICING_SOURCES.openai,
  },
  {
    model: "gemini-3.5-flash",
    inputPrice: 1.50,
    outputPrice: 9.00,
    note: "Standard tier visible pricing. Actual cost may differ by tier/region.",
    source: PRICING_SOURCES.gemini,
  },
];

export interface BoundaryRow {
  component: string;
  type: "deterministic" | "llm";
  controls: string;
}

export const BOUNDARY: BoundaryRow[] = [
  { component: "Specification agent", type: "llm", controls: "Interprets tasks, derives requirements" },
  { component: "Planner agent", type: "llm", controls: "Proposes implementation plan" },
  { component: "Implementation agent", type: "llm", controls: "Proposes a structured patch; harness validates and applies it" },
  { component: "Independent test agent", type: "llm", controls: "Generates additional tests (stubbed in alpha)" },
  { component: "Adversarial review agent", type: "llm", controls: "Identifies unsupported claims (stubbed in alpha)" },
  { component: "Explanation agent", type: "llm", controls: "Converts evidence to report (stubbed in alpha)" },
  { component: "Policy engine", type: "deterministic", controls: "Required evidence, thresholds, approval roles" },
  { component: "Decision engine", type: "deterministic", controls: "Accept / reject / repair decision" },
  { component: "Sandbox manager", type: "deterministic", controls: "Isolation, permissions, timeouts" },
  { component: "Evidence executors", type: "deterministic", controls: "Run checks, record EvidenceRecords" },
  { component: "AST analyzer", type: "deterministic", controls: "Impact analysis, test selection" },
  { component: "Provenance recorder", type: "deterministic", controls: "Hash-chained event stream" },
];

export interface TierRow {
  tier: number;
  checks: string;
  approval: string;
  color: string;
}

export const TIERS: TierRow[] = [
  { tier: 3, checks: "formatting, lint, type check, targeted tests, secret scan", approval: "Automated", color: "emerald" },
  { tier: 2, checks: "+ integration tests, security scan, mutation testing", approval: "Code owner", color: "amber" },
  { tier: 1, checks: "+ contract tests, dependency scan, performance, rollback", approval: "Code owner + security owner", color: "red" },
];

export const QUICK_START = [
  { cmd: "git clone https://github.com/rmax-ai/evidence-first-harness.git", desc: "Clone the repository" },
  { cmd: "cd evidence-first-harness && uv sync --extra dev", desc: "Install dependencies" },
  { cmd: "uv run pytest tests/ -q", desc: "Run 85 tests in ~7 seconds" },
  {
    cmd: 'uv run efh run --repo . --task "Add a focused test for the policy engine."',
    desc: "Full E2E smoke test (~2 min)",
  },
];

// Cost explanation shown below smoke output
export const SMOKE_CAVEAT =
  "This is the recorded output from run_c6ec67e305e0 against commit 233ebbac. " +
  "It shows LLM agents producing implementation artifacts while deterministic checks and policy " +
  "make the final decision. Runtime, token counts, and cost vary with provider behavior and repository state.";

export const COST_BREAKDOWN =
  "Recorded cost: $0.504927 (36,834 input and 9,118 output tokens). " +
  "Sonnet 5 compiled the specification, Opus 4.6 planned the implementation, and GPT-5.6 Terra generated the patch.";

export const SMOKE_OUTPUT = `$ efh run --repo . --task "Add a focused test for the policy engine."

workflow_started    run_id=run_c6ec67e305e0
worktree_created    base_commit=233ebbac

specification_agent_call   sonnet-5       in=13570  out=4096
planner_agent_call         opus-4-6       in=11871  out=2015
implementation_agent_call  gpt-5.6-terra  in=11393  out=3007

evidence_executed  formatting  ruff     fail
evidence_executed  lint        ruff     fail
evidence_executed  type_check  pyright  fail
evidence_executed  secret_scan secrets  fail
evidence_executed  tests       pytest   pass

decision_rendered  decision=repair_required
  mandatory_failed=4  passed=1  tier=3

│ Agent              Model                  In    Out │
├──────────────────┼──────────────────┼──────┼──────┤
│ specification      claude-sonnet-5     13570   4096 │
│ planner            claude-opus-4-6     11871   2015 │
│ implementation     gpt-5.6-terra       11393   3007 │
├──────────────────┼──────────────────┼──────┼──────┤
│ TOTAL                                  36834   9118 │`;
