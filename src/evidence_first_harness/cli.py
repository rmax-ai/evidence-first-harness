"""CLI entry point for the Evidence-First Harness.

Section 21 of the spec. Provides the `efh` command with subcommands
for initialization, inspection, execution, evidence review, and export.
"""

from __future__ import annotations

import click

from evidence_first_harness import __version__


@click.group()
@click.version_option(version=__version__, prog_name="efh")
def main() -> None:
    """Evidence-First Harness — deterministic assurance for AI-generated code.

    Treats generated code as untrusted proposals. Produces validated
    Evidence Bundles governed by explicit, version-controlled policy.
    """
    pass


@main.command()
@click.option("--repo", default=".", help="Path to the repository")
def init(repo: str) -> None:
    """Initialize EFH configuration in a repository."""
    click.echo(f"Initializing EFH in {repo}...")
    click.echo("(Phase 1 — not yet implemented)")


@main.command()
@click.option("--repo", default=".", help="Path to the repository")
def inspect(repo: str) -> None:
    """Inspect a repository and summarize its structure."""
    click.echo(f"Inspecting repository at {repo}...")
    click.echo("(Phase 1 — not yet implemented)")


@main.command()
@click.option("--repo", default=".", help="Path to the repository")
@click.option("--patch", "patch_path", default=None, help="Path to a patch file to evaluate")
@click.option("--spec", default=None, help="Path to a YAML task specification")
def run(repo: str, patch_path: str | None, spec: str | None) -> None:
    """Run the evidence-first workflow on a repository."""
    import asyncio

    from evidence_first_harness.workflows.session import SessionManager

    click.echo(f"Evidence-First Harness — running on {repo}")
    if patch_path:
        click.echo(f"Evaluating patch: {patch_path}")
    if spec:
        click.echo(f"Using specification: {spec}")

    manager = SessionManager(repo_path=repo)
    result = asyncio.run(
        manager.run(
            task_description=spec or "Evaluate existing patch",
            patch_path=patch_path,
        )
    )

    click.echo(f"\nRun ID: {result['run_id']}")
    click.echo(f"Decision: {result['decision']}")
    click.echo(f"Repository: {result['repository']}")
    click.echo(f"Base commit: {result.get('base_commit', 'unknown')[:8]}")

    if result.get("bundle_path"):
        click.echo(f"\nEvidence bundle: {result['bundle_path']}")
    if result.get("errors"):
        click.echo(f"\nErrors: {len(result['errors'])}")
        for err in result["errors"][:5]:
            click.echo(f"  - {err}")


@main.command()
@click.option("--run-id", required=True, help="Run ID to check status of")
def status(run_id: str) -> None:
    """Show the status of a run."""
    from pathlib import Path

    artifact_dir = Path(".artifacts") / run_id
    bundle_path = artifact_dir / "evidence-bundle.json"

    if bundle_path.exists():
        import json

        data = json.loads(bundle_path.read_text())
        decision = data.get("decision", {}).get("decision", "unknown")
        evidence_count = len(data.get("evidence", []))
        click.echo(f"Run: {run_id}")
        click.echo(f"Decision: {decision}")
        click.echo(f"Evidence records: {evidence_count}")
        click.echo(f"Bundle: {bundle_path}")
    else:
        click.echo(f"No evidence bundle found for run {run_id}")


@main.command()
@click.option("--run-id", required=True, help="Run ID to resume")
def resume(run_id: str) -> None:
    """Resume an interrupted run."""
    click.echo(f"Resuming run {run_id}...")
    click.echo("(Phase 2 — not yet implemented)")


@main.group()
def evidence() -> None:
    """View and verify evidence bundles."""
    pass


@evidence.command("show")
@click.option("--run-id", required=True, help="Run ID to show evidence for")
def evidence_show(run_id: str) -> None:
    """Show evidence for a completed run."""
    click.echo(f"Evidence for run {run_id}:")
    click.echo("(Phase 1 — not yet implemented)")


@evidence.command("verify")
@click.option("--bundle", required=True, help="Path to evidence bundle JSON")
def evidence_verify(bundle: str) -> None:
    """Verify the integrity of an evidence bundle."""
    click.echo(f"Verifying bundle: {bundle}")
    click.echo("(Phase 1 — not yet implemented)")


@main.command()
@click.option("--run-id", required=True, help="Run ID to approve")
@click.option(
    "--decision", required=True, type=click.Choice(["approve", "reject", "request_changes"])
)
def approve(run_id: str, decision: str) -> None:
    """Submit a human approval decision for a run."""
    click.echo(f"Submitting {decision} for run {run_id}...")
    click.echo("(Phase 2 — not yet implemented)")


@main.command()
@click.option("--run-id", required=True, help="Run ID to export")
@click.option("--format", "output_format", default="html", type=click.Choice(["html", "json"]))
def export(run_id: str, output_format: str) -> None:
    """Export an evidence bundle to HTML or JSON."""
    click.echo(f"Exporting run {run_id} as {output_format}...")
    click.echo("(Phase 1 — not yet implemented)")


@main.group()
def benchmark() -> None:
    """Run research benchmarks."""
    pass


@benchmark.command("run")
@click.argument("config_path", type=click.Path(exists=True))
def benchmark_run(config_path: str) -> None:
    """Run a benchmark experiment."""
    click.echo(f"Running benchmark: {config_path}")
    click.echo("(Phase 4 — not yet implemented)")


@main.group()
def github() -> None:
    """GitHub integration — check runs, PR comments, artifacts."""
    pass


@github.command("check-run")
@click.option("--owner", required=True, help="GitHub repository owner")
@click.option("--repo", required=True, help="GitHub repository name")
@click.option("--sha", "head_sha", required=True, help="Commit SHA to attach check to")
@click.option("--run-id", required=True, help="EFH run ID to publish")
@click.option("--conclusion", default="neutral",
              type=click.Choice(["success", "failure", "neutral", "cancelled", "timed_out", "action_required"]))
@click.option("--token", default=None, help="GitHub token (or use GITHUB_TOKEN env)")
def github_check_run(
    owner: str,
    repo: str,
    head_sha: str,
    run_id: str,
    conclusion: str,
    token: str | None,
) -> None:
    """Publish an evidence bundle as a GitHub Check Run."""
    from pathlib import Path

    from evidence_first_harness.integrations.github import GitHubIntegration

    bundle_path = Path(".artifacts") / run_id / "evidence-bundle.json"
    if not bundle_path.exists():
        click.echo(f"Error: No evidence bundle found for run {run_id}", err=True)
        return

    import json

    evidence_data = json.loads(bundle_path.read_text())

    integration = GitHubIntegration(owner=owner, repo=repo, token=token)
    result = integration.create_check_run(
        name="Evidence-First Harness",
        head_sha=head_sha,
        evidence_summary=evidence_data,
        conclusion=conclusion,
        external_id=run_id,
    )

    if result.error:
        click.echo(f"Error: {result.error}", err=True)
        return

    click.echo(f"Check run created: {result.html_url}")
    click.echo(f"  ID: {result.check_run_id}")
    click.echo(f"  Conclusion: {result.conclusion}")
    click.echo(f"  Annotations: {result.annotations_count}")


@github.command("pr-comment")
@click.option("--owner", required=True, help="GitHub repository owner")
@click.option("--repo", required=True, help="GitHub repository name")
@click.option("--pr", "pr_number", required=True, type=int, help="Pull request number")
@click.option("--run-id", required=True, help="EFH run ID to summarize")
@click.option("--token", default=None, help="GitHub token (or use GITHUB_TOKEN env)")
def github_pr_comment(
    owner: str,
    repo: str,
    pr_number: int,
    run_id: str,
    token: str | None,
) -> None:
    """Post an evidence summary as a PR comment."""
    from pathlib import Path

    from evidence_first_harness.integrations.github import GitHubIntegration

    bundle_path = Path(".artifacts") / run_id / "evidence-bundle.json"
    if not bundle_path.exists():
        click.echo(f"Error: No evidence bundle found for run {run_id}", err=True)
        return

    import json

    evidence_data = json.loads(bundle_path.read_text())

    integration = GitHubIntegration(owner=owner, repo=repo, token=token)
    result = integration.create_pr_comment(pr_number=pr_number, evidence_summary=evidence_data)

    if result.get("error"):
        click.echo(f"Error: {result['error']}", err=True)
        return

    comment_url = result.get("html_url", "unknown")
    click.echo(f"PR comment posted: {comment_url}")


if __name__ == "__main__":
    main()
