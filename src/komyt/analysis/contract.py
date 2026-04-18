"""Ticket contract extraction and validation."""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from komyt.core.config import AnalysisConfig
from komyt.core.models import (
    Complexity,
    ContractValidation,
    Priority,
    Scope,
    TicketContract,
    TicketData,
    TicketType,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("objective", "ticket_type", "success_criteria")
IMPORTANT_FIELDS = ("expected_behavior", "scope")
OPTIONAL_FIELDS = (
    "affected_files",
    "technical_constraints",
    "dependencies",
    "examples",
    "references",
    "reproduction_steps",
)

EXTRACTION_PROMPT = """\
You are an expert at analyzing software tickets. Extract a structured contract \
from the following ticket.

Title: {title}
Description:
{description}

Comments:
{comments}

Respond with ONLY a JSON object (no markdown fences) matching this schema:
{{
  "objective": "string — what needs to be done",
  "ticket_type": "feature|bugfix|refactor|docs|chore",
  "success_criteria": ["list of measurable acceptance criteria"],
  "expected_behavior": "string or null",
  "scope_included": ["what is in scope"],
  "scope_excluded": ["what is out of scope"],
  "reproduction_steps": ["steps to reproduce (bugs only)"] or null,
  "affected_files": ["file paths if mentioned"],
  "technical_constraints": ["constraints"],
  "dependencies": ["dependencies"],
  "references": ["links or references"],
  "priority": "low|medium|high|critical",
  "estimated_complexity": "trivial|simple|moderate|complex"
}}
"""


class LLMClient(Protocol):
    """Minimal protocol for LLM calls used by analysis modules."""

    async def complete(self, prompt: str) -> str: ...


class ContractExtractor:
    """Extracts and validates a TicketContract from free-form ticket text."""

    def __init__(self, llm: LLMClient, config: AnalysisConfig) -> None:
        self._llm = llm
        self._config = config

    async def extract(self, ticket: TicketData) -> ContractValidation:
        comments_text = "\n".join(
            f"[{c.author}]: {c.body}" for c in ticket.comments
        ) or "(none)"

        prompt = EXTRACTION_PROMPT.format(
            title=ticket.title,
            description=ticket.description,
            comments=comments_text,
        )

        raw = await self._llm.complete(prompt)
        data = _parse_json(raw)
        contract = _build_contract(data)

        filled = _get_filled_fields(contract)
        missing = _get_missing_fields(contract)
        score = _compute_score(filled, missing)
        status = _score_to_status(score, self._config.clarity_threshold)

        ambiguities: list[str] = []
        if not contract.success_criteria:
            ambiguities.append("No measurable success criteria defined")
        if contract.ticket_type == TicketType.BUGFIX and not contract.reproduction_steps:
            ambiguities.append("Bug report without reproduction steps")

        questions: list[str] = []
        if status == ValidationStatus.NEEDS_CLARIFICATION:
            questions = _generate_questions(missing, ambiguities)

        return ContractValidation(
            score=score,
            status=status,
            extracted_contract=contract,
            filled_fields=filled,
            missing_fields=missing,
            ambiguities=ambiguities,
            questions=questions,
            confidence=score / 100.0,
        )


def _parse_json(raw: str) -> dict:  # type: ignore[type-arg]
    cleaned = raw.strip()
    # Strip <think>...</think> blocks (Qwen, DeepSeek, etc.)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    decoder = json.JSONDecoder(strict=False)

    # 1. Try parsing as-is with lenient decoder
    try:
        return decoder.decode(cleaned)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # 2. Extract just the JSON object and strip control characters inside strings
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        fragment = match.group()
        try:
            return decoder.decode(fragment)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass
        # Aggressively replace control chars except \n and \t
        fragment = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", fragment)
        # Escape unescaped newlines inside JSON strings
        fragment = _escape_newlines_in_strings(fragment)
        try:
            return json.loads(fragment)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No valid JSON found in LLM response", raw[:200], 0)


def _escape_newlines_in_strings(text: str) -> str:
    """Replace literal newlines/tabs inside JSON string values with \\n/\\t."""
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == "\\":
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
        result.append(ch)
    return "".join(result)


def _build_contract(data: dict) -> TicketContract:  # type: ignore[type-arg]
    scope_inc = data.get("scope_included", [])
    scope_exc = data.get("scope_excluded", [])
    scope = Scope(included=scope_inc, excluded=scope_exc) if scope_inc or scope_exc else None

    ticket_type_raw = data.get("ticket_type", "feature")
    try:
        ticket_type = TicketType(ticket_type_raw)
    except ValueError:
        ticket_type = TicketType.FEATURE

    priority_raw = data.get("priority", "medium")
    try:
        priority = Priority(priority_raw)
    except ValueError:
        priority = Priority.MEDIUM

    complexity_raw = data.get("estimated_complexity", "moderate")
    try:
        complexity = Complexity(complexity_raw)
    except ValueError:
        complexity = Complexity.MODERATE

    return TicketContract(
        objective=data.get("objective", ""),
        ticket_type=ticket_type,
        success_criteria=data.get("success_criteria", []),
        expected_behavior=data.get("expected_behavior"),
        scope=scope,
        reproduction_steps=data.get("reproduction_steps"),
        affected_files=data.get("affected_files", []),
        technical_constraints=data.get("technical_constraints", []),
        dependencies=data.get("dependencies", []),
        references=data.get("references", []),
        priority=priority,
        estimated_complexity=complexity,
    )


def _get_filled_fields(contract: TicketContract) -> list[str]:
    filled: list[str] = []
    if contract.objective:
        filled.append("objective")
    if contract.success_criteria:
        filled.append("success_criteria")
    filled.append("ticket_type")
    if contract.expected_behavior:
        filled.append("expected_behavior")
    if contract.scope:
        filled.append("scope")
    if contract.reproduction_steps:
        filled.append("reproduction_steps")
    if contract.affected_files:
        filled.append("affected_files")
    if contract.technical_constraints:
        filled.append("technical_constraints")
    if contract.dependencies:
        filled.append("dependencies")
    if contract.examples:
        filled.append("examples")
    if contract.references:
        filled.append("references")
    return filled


def _get_missing_fields(contract: TicketContract) -> list[str]:
    missing: list[str] = []
    if not contract.objective:
        missing.append("objective")
    if not contract.success_criteria:
        missing.append("success_criteria")
    if not contract.expected_behavior:
        missing.append("expected_behavior")
    if not contract.scope:
        missing.append("scope")
    return missing


def _compute_score(filled: list[str], missing: list[str]) -> int:
    weights = {
        "objective": 25,
        "success_criteria": 25,
        "ticket_type": 5,
        "expected_behavior": 15,
        "scope": 10,
        "reproduction_steps": 5,
        "affected_files": 5,
        "technical_constraints": 3,
        "dependencies": 3,
        "examples": 2,
        "references": 2,
    }
    score = sum(weights.get(f, 0) for f in filled)
    return min(score, 100)


def _score_to_status(score: int, threshold: int) -> ValidationStatus:
    if score >= 80:
        return ValidationStatus.READY
    if score >= threshold // 2:
        return ValidationStatus.NEEDS_CLARIFICATION
    return ValidationStatus.REJECTED


def _generate_questions(missing: list[str], ambiguities: list[str]) -> list[str]:
    field_questions = {
        "objective": "What is the main objective of this change?",
        "success_criteria": "What are the measurable acceptance criteria?",
        "expected_behavior": "What is the expected behavior after implementation?",
        "scope": "What is in scope and out of scope for this change?",
    }
    questions = [field_questions[f] for f in missing if f in field_questions]
    questions.extend(ambiguities)
    return questions
