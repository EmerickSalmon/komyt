"""Prompt templates for OpenCode interactions."""

from __future__ import annotations

from komyt.core.models import DevEnvironment, DevStep, DevelopmentPlan


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

    if env.test_command:
        parts.append(f"\nRun tests with: `{env.test_command}`")

    if env.lint_command:
        parts.append(f"Run lint with: `{env.lint_command}`")

    if env.agent_instructions:
        parts.append(f"\n### Repository conventions\n{env.agent_instructions}")

    return "\n".join(parts)


def build_retry_prompt(
    step: DevStep,
    plan: DevelopmentPlan,
    env: DevEnvironment,
    errors: list[str],
    attempt: int,
) -> str:
    original = build_step_prompt(step, plan, env)

    error_text = "\n".join(f"- {e}" for e in errors)

    return (
        f"{original}\n\n"
        f"---\n"
        f"## Retry (attempt {attempt}/{step.max_attempts})\n\n"
        f"The previous attempt failed with the following errors:\n{error_text}\n\n"
        f"Please fix these issues. Focus on the errors above and make minimal "
        f"changes to resolve them."
    )


def build_commit_message(step: DevStep, plan: DevelopmentPlan) -> str:
    type_prefix = plan.contract.ticket_type.value
    return f"{type_prefix}: {step.description}\n\nPart of #{plan.ticket.external_id}"


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
        f"Summary, Changes, and Testing."
    )


def build_docs_update_prompt(plan: DevelopmentPlan, doc_files: list[str]) -> str:
    return (
        f"Update the following documentation files to reflect the changes made:\n\n"
        f"Objective: {plan.contract.objective}\n"
        f"Files to update: {', '.join(doc_files)}\n\n"
        f"Keep changes minimal and accurate. Only update sections that are "
        f"affected by the implementation."
    )
