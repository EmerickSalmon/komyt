"""Analysis engine — orchestrates ticket validation and dev plan generation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from komyt.analysis.clarity import ClarityAssessor
from komyt.analysis.contract import ContractExtractor, LLMClient
from komyt.analysis.planner import DevPlanner
from komyt.core.config import AnalysisConfig
from komyt.core.models import (
    ContractValidation,
    DevelopmentPlan,
    TicketData,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Full result of analyzing a ticket."""

    ticket: TicketData
    validation: ContractValidation
    plan: DevelopmentPlan | None
    feedback_comment: str | None


class AnalysisEngine:
    """Coordinates contract extraction, clarity assessment, and plan generation."""

    def __init__(self, config: AnalysisConfig, llm: LLMClient) -> None:
        self._config = config
        self._extractor = ContractExtractor(llm=llm, config=config)
        self._clarity = ClarityAssessor()
        self._planner = DevPlanner(llm=llm)

    async def analyze(self, ticket: TicketData) -> AnalysisResult:
        logger.info("Analyzing ticket %s: %s", ticket.id, ticket.title)

        validation = await self._extractor.extract(ticket)
        logger.info(
            "Ticket %s scored %d/100 — status: %s",
            ticket.id,
            validation.score,
            validation.status.value,
        )

        feedback = self._clarity.build_feedback(ticket, validation)

        plan: DevelopmentPlan | None = None
        if validation.status == ValidationStatus.READY:
            plan = await self._planner.plan(ticket, validation.extracted_contract)
            logger.info(
                "Generated plan for %s with %d steps", ticket.id, len(plan.steps)
            )

        return AnalysisResult(
            ticket=ticket,
            validation=validation,
            plan=plan,
            feedback_comment=feedback,
        )

    async def validate(self, ticket: TicketData) -> ContractValidation:
        return await self._extractor.extract(ticket)
