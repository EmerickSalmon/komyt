"""Prompt templates for OpenCode interactions."""

from __future__ import annotations

from komyt.core.models import DevelopmentPlan, DevEnvironment, DevStep


def build_step_prompt(
    step: DevStep,
    plan: DevelopmentPlan,
    env: DevEnvironment,
) -> str:
    parts = [
        f"## Task: {step.description}\n",
        f"You are working on: {plan.contract.objective}\n",
        f"Branch: {plan.branch_name}",
        f"Language: {env.language}",
    ]

    if env.framework:
        parts.append(f"Framework: {env.framework}")

    if step.files_involved:
        parts.append(f"\nFiles to work on: {', '.join(step.files_involved)}")

    if step.prompt:
        parts.append(f"\n### Instructions\n{step.prompt}")

    if plan.contract.success_criteria:
        criteria = "\n".join(f"- {c}" for c in plan.contract.success_criteria)
        parts.append(f"\n### Success criteria\n{criteria}")

    parts.append(_build_definition_of_done(env))

    verification_block = _build_verification_block(env)
    if verification_block:
        parts.append(verification_block)

    if env.agent_instructions:
        parts.append(f"\n### Repository conventions\n{env.agent_instructions}")

    return "\n".join(parts)


_COVERAGE_THRESHOLD = 80


def _build_definition_of_done(env: DevEnvironment) -> str:
    """Explicit 3-part contract the agent must satisfy before finishing."""
    python = env.language == "python"
    lint_tools = "flake8, black --check, ruff, mypy" if python else "the project's linters"
    test_runner = "pytest --cov" if python else (env.test_command or "the project's test runner")

    return (
        "\n### Definition of done — do all three, in this order\n"
        "1. **Implement** the feature described above. Write real code in the "
        "repository, not placeholders.\n"
        f"2. **Write unit tests** so that overall coverage is strictly greater "
        f"than {_COVERAGE_THRESHOLD}% (run `{test_runner}` and check the "
        f"coverage summary).\n"
        f"3. **Run verification** ({lint_tools}). Fix every issue until all "
        "commands exit 0."
    )


def _build_verification_block(env: DevEnvironment) -> str:
    commands: list[tuple[str, str]] = []
    if env.test_command:
        commands.append(("tests", env.test_command))
    if env.lint_command:
        commands.append(("lint", env.lint_command))
    if env.build_command:
        commands.append(("build", env.build_command))

    if not commands:
        return ""

    lines = [
        "\n### Verification — run these yourself before finishing",
        "Use your shell tool inside the container to run each command below. "
        "If any of them fail, read the output, fix the root cause, then re-run "
        "them. Iterate until every command exits 0. Only stop when everything "
        "is green.",
    ]
    for label, cmd in commands:
        lines.append(f"- {label}: `{cmd}`")
    return "\n".join(lines)


def build_retry_prompt(
    step: DevStep,
    plan: DevelopmentPlan,
    env: DevEnvironment,
    errors: list[str],
    attempt: int,
) -> str:
    original = build_step_prompt(step, plan, env)

    error_blocks = "\n\n".join(
        f"### Failure {i}\n```\n{e}\n```" for i, e in enumerate(errors, 1)
    )

    return (
        f"{original}\n\n"
        f"---\n"
        f"## Retry (attempt {attempt}/{step.max_attempts})\n\n"
        f"Our post-step verification ran the commands listed above and some of "
        f"them failed. The verbatim output is below — read the tracebacks and "
        f"error messages carefully, they name the exact files, lines and "
        f"reasons.\n\n"
        f"{error_blocks}\n\n"
        f"Fix the root cause, then **re-run the verification commands yourself "
        f"inside the container and keep iterating until they all exit 0**. Do "
        f"not report back until your own run of tests, lint and build is "
        f"green. If a file you previously wrote contains non-source content "
        f"(markdown separators like `---`, prose, code fences), rewrite it as "
        f"valid `{env.language}` source."
    )


def build_commit_message(step: DevStep, plan: DevelopmentPlan) -> str:
    type_prefix = plan.contract.ticket_type.value
    return f"{type_prefix}: {step.description}\n\nPart of #{plan.ticket.external_id}"


def build_failed_commit_message(
    step: DevStep,
    plan: DevelopmentPlan,
    last_error: str = "",
) -> str:
    type_prefix = plan.contract.ticket_type.value
    body_lines = [
        f"WIP: verification still failing after {step.attempt_count} attempt(s).",
        "A human reviewer should take over this step.",
        f"Part of #{plan.ticket.external_id}",
    ]
    if last_error:
        snippet = last_error.strip().splitlines()[0][:200]
        body_lines.append(f"\nLast error: {snippet}")
    body = "\n".join(body_lines)
    return f"{type_prefix}(wip): {step.description}\n\n{body}"


def build_pr_description_prompt(plan: DevelopmentPlan) -> str:
    steps_text = "\n".join(
        f"- {s.description}" for s in plan.steps
    )

    return (
        f"Generate a pull request description for the following changes:\n\n"
        f"## Objective\n{plan.contract.objective}\n\n"
        f"## Steps completed\n{steps_text}\n\n"
        f"## Success criteria\n"
        + "\n".join(f"- {c}" for c in plan.contract.success_criteria)
        + "\n\nWrite a concise PR description in markdown with sections: "
        "Summary, Changes, and Testing."
    )


def build_docs_update_prompt(plan: DevelopmentPlan, doc_files: list[str]) -> str:
    return (
        f"Update the following documentation files to reflect the changes made:\n\n"
        f"Objective: {plan.contract.objective}\n"
        f"Files to update: {', '.join(doc_files)}\n\n"
        f"Keep changes minimal and accurate. Only update sections that are "
        f"affected by the implementation."
    )
