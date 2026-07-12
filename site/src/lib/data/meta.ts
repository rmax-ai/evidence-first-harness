// Shared data for the Evidence-First Harness landing page.
// Single source of truth — components import from here.

export const PROJECT = {
  name: "Evidence-First Harness",
  version: "v0.1.0",
  repo: "https://github.com/rmax-ai/evidence-first-harness",
  license: "MIT",
};

export const PRINCIPLE =
  "No agent-generated change may be accepted unless every material claim introduced by the change is linked to sufficient, reproducible, risk-adjusted evidence.";

export const STACK = [
  "Python 3.12+",
  "Google ADK 2.0",
  "Pydantic v2",
  "Structlog",
  "LiteLLM",
  "Docker sandbox",
];

export const METRICS = [
  { label: "73", desc: "Unit tests" },
  { label: "18", desc: "Commits" },
  { label: "3/6", desc: "LLM agents live" },
  { label: "9", desc: "Evidence executors" },
  { label: "$0.32", desc: "Cost per run" },
  { label: "17", desc: "Workflow nodes" },
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
  { agent: "Specification", model: "claude-opus-4-6", provider: "Anthropic", live: true, inTokens: 294, outTokens: 4096 },
  { agent: "Planner", model: "claude-sonnet-5", provider: "Anthropic", live: true, inTokens: 430, outTokens: 770 },
  { agent: "Implementation", model: "deepseek-chat", provider: "DeepSeek", live: true, inTokens: 276, outTokens: 34 },
  { agent: "Independent Test", model: "claude-haiku-4-5", provider: "Anthropic", live: false, inTokens: 0, outTokens: 0 },
  { agent: "Adversarial Review", model: "gemini-3.5-flash", provider: "Google", live: false, inTokens: 0, outTokens: 0 },
  { agent: "Explanation", model: "gemini-3.5-flash", provider: "Google", live: false, inTokens: 0, outTokens: 0 },
];

export interface PricingRow {
  model: string;
  inputPrice: number;
  outputPrice: number;
}

export const PRICING: PricingRow[] = [
  { model: "claude-opus-4-6", inputPrice: 15.00, outputPrice: 75.00 },
  { model: "claude-sonnet-5", inputPrice: 3.00, outputPrice: 15.00 },
  { model: "claude-haiku-4-5", inputPrice: 0.80, outputPrice: 4.00 },
  { model: "deepseek-chat", inputPrice: 0.27, outputPrice: 1.10 },
  { model: "gemini-3.5-flash", inputPrice: 0.075, outputPrice: 0.30 },
];

export interface BoundaryRow {
  component: string;
  type: "deterministic" | "llm";
  controls: string;
}

export const BOUNDARY: BoundaryRow[] = [
  { component: "Specification agent", type: "llm", controls: "Interprets tasks, derives requirements" },
  { component: "Planner agent", type: "llm", controls: "Proposes implementation plan" },
  { component: "Implementation agent", type: "llm", controls: "Generates code in sandbox" },
  { component: "Independent test agent", type: "llm", controls: "Generates additional tests" },
  { component: "Adversarial review agent", type: "llm", controls: "Identifies unsupported claims" },
  { component: "Explanation agent", type: "llm", controls: "Converts evidence to report" },
  { component: "Policy engine", type: "deterministic", controls: "Required evidence, thresholds, approval roles" },
  { component: "Decision engine", type: "deterministic", controls: "Accept / reject / repair decision" },
  { component: "Sandbox manager", type: "deterministic", controls: "Isolation, permissions, timeouts" },
  { component: "Evidence executors", type: "deterministic", controls: "Run checks, produce EvidenceRecords" },
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
  { cmd: "uv run pytest tests/ -q", desc: "Run 73 tests in ~4 seconds" },
  { cmd: "uv run efh run --repo .", desc: "Full E2E smoke test (~90s)" },
];

export const SMOKE_OUTPUT = `$ efh run --repo .

workflow_started    run_id=run_3da28c6662d9
worktree_created    base_commit=9007ebb1

specification_agent_call   opus-4-6   in=294   out=4096   \$0.311610
planner_agent_call         sonnet-5   in=430   out=770    \$0.012840
implementation_agent_call  deepseek   in=276   out=34     \$0.000112

evidence_executed  formatting  ruff     fail
evidence_executed  lint        ruff     fail
evidence_executed  type_check  pyright  fail
evidence_executed  secret_scan secrets  pass
evidence_executed  tests       pytest   fail

decision_rendered  decision=repair_required
  mandatory_failed=4  passed=1  tier=3

│ Agent              Model                  In    Out  Cost (USD) │
├──────────────────┼──────────────────┼──────┼──────┼──────────┤
│ specification      claude-opus-4-6       294   4096  \$0.311610 │
│ planner            claude-sonnet-5       430    770  \$0.012840 │
│ implementation     deepseek-chat         276     34  \$0.000112 │
├──────────────────┼──────────────────┼──────┼──────┼──────────┤
│ TOTAL                                   1000   4900  \$0.324562 │`;
