from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agents.llm import LLMClient
from outreach_packages.schemas import (
    GeneratedOutreach,
    OutreachGeneration,
    OutreachGenerationInput,
    OutreachClaim,
    OutreachEvidence,
    OutreachProposal,
    OutreachResponseClassification,
    OutreachStrategy,
    ReplyPath,
)
from outreach_packages.templates import (
    DeterministicPhrasingAdapter,
    OutreachTemplateContext,
)
from shared.logger import get_logger


logger = get_logger(__name__)
OUTREACH_GENERATION_PROMPT_VERSION = 1


class StructuredOutreachGenerator:
    def __init__(self, *, llm: LLMClient) -> None:
        self.llm = llm

    def generate(
        self,
        *,
        business: dict,
        sender: dict,
        evidence: list[OutreachEvidence],
        outreach_input: OutreachGenerationInput,
        fallback_proposal: OutreachProposal,
    ) -> GeneratedOutreach:
        generated = self.llm.generate_object(
            task="outreach_channel_generation",
            system=(
                "Create grounded outreach for a local business from the supplied JSON only. "
                "Never invent compliments, projects, reviews, results, contact details, links, prices, "
                "or website findings. Treat lead evidence as an observation, not proof of lost revenue. "
                "Frame the proposal as a potential gain without criticizing the business. Use the optional "
                "personal detail, concept URL, concept features, and direction only when supplied. Return "
                "one shared proposal plus channel-specific drafts. Each written draft should naturally cover "
                "the sender identity, one supported business-specific detail when available, one opportunity "
                "framed as a gain, proof only when a real concept URL exists, and a soft call to action. "
                "Instagram should be conversational; SMS must be concise; email may be fuller; call output "
                "must be an opener, talking points, and a soft close. Omit proof claims when no concept URL "
                "exists. Generate only the channels listed in outreach_input.channels and return null for "
                "every unselected channel."
            ),
            prompt=(
                "Generate a proposal and outreach drafts that preserve the same factual substance across "
                "channels while adapting length and delivery to each channel."
            ),
            response_model=GeneratedOutreach,
            context={
                "prompt_version": OUTREACH_GENERATION_PROMPT_VERSION,
                "business": business,
                "sender": sender,
                "verified_evidence": [item.model_dump() for item in evidence],
                "outreach_input": outreach_input.model_dump(),
                "fallback_proposal": fallback_proposal.model_dump(),
            },
        )
        selected = set(outreach_input.channels)
        channels = generated.channels.model_copy(
            update={
                "instagram": generated.channels.instagram if "instagram" in selected else None,
                "sms": generated.channels.sms if "sms" in selected else None,
                "email": generated.channels.email if "email" in selected else None,
                "call": generated.channels.call if "call" in selected else None,
            }
        )
        return generated.model_copy(
            update={
                "channels": channels,
                "prompt_version": OUTREACH_GENERATION_PROMPT_VERSION,
            }
        )

class PhrasedSections(BaseModel):
    customer_consequence: str = Field(min_length=8, max_length=320)
    seller_positioning: str = Field(min_length=8, max_length=320)
    value_hypothesis: str = Field(min_length=8, max_length=400)
    next_step: str = Field(min_length=8, max_length=240)


class ClassifiedResponse(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)


class OpenAIPhrasingAdapter:
    provider = "openai"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.last_strategy: OutreachStrategy | None = None

    def render(self, context: OutreachTemplateContext) -> OutreachGeneration:
        strategy = context.strategy
        try:
            phrased = self.llm.generate_object(
                task="outreach_phrasing",
                system=(
                    "Refine approved outreach sections without introducing facts. The final pitch uses "
                    "this order: one-line sender positioning, one verified business detail, one opportunity "
                    "framed as a gain, optional proof only when supplied, and one soft call to action. "
                    "Keep hypotheses qualified with may, might, or could. Make seller_positioning one concise "
                    "sentence and next_step an easy, low-pressure question. Do not invent compliments, proof, "
                    "concept links, videos, outcomes, prices, customer losses, or that a website is absent."
                ),
                prompt=(
                    "Improve clarity and natural sales phrasing. Frame the opportunity positively rather "
                    "than criticizing the business. The verified observation is immutable and is not "
                    "included in the output schema."
                ),
                response_model=PhrasedSections,
                context={
                    "trade": strategy.trade_key,
                    "customer_actions": strategy.customer_actions,
                    "verified_observation": strategy.observation,
                    "customer_consequence": strategy.customer_consequence,
                    "seller_positioning": strategy.seller_positioning,
                    "value_hypothesis": strategy.value_hypothesis,
                    "next_step": strategy.next_step,
                    "prohibited_claims": strategy.prohibited_claims,
                },
            )
            refined = strategy.model_copy(
                update={
                    **phrased.model_dump(),
                    "phrasing_provider": "openai",
                    "claim_ledger": [
                        OutreachClaim(
                            text=strategy.observation,
                            kind="evidence",
                            evidence_keys=[strategy.primary_signal_key],
                        ),
                        OutreachClaim(
                            text=phrased.customer_consequence,
                            kind="hypothesis",
                            evidence_keys=[strategy.primary_signal_key],
                        ),
                        OutreachClaim(text=phrased.seller_positioning, kind="seller"),
                        OutreachClaim(text=phrased.next_step, kind="cta"),
                    ],
                }
            )
            self.last_strategy = refined
            return DeterministicPhrasingAdapter().render(
                OutreachTemplateContext(
                    business_name=context.business_name,
                    strategy=refined,
                    signature=context.signature,
                )
            )
        except Exception as exc:
            logger.warning("outreach_phrasing_fallback error=%s", exc.__class__.__name__)
            self.last_strategy = None
            return DeterministicPhrasingAdapter().render(context)


class ResponseClassifier:
    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        use_ai: bool = False,
    ) -> None:
        self.llm = llm
        self.use_ai = use_ai and llm is not None

    def classify(
        self,
        *,
        response_text: str,
        channel: Literal["message", "call", "form", "email"],
        paths: list[ReplyPath],
    ) -> OutreachResponseClassification:
        if self.use_ai:
            result = self._classify_with_ai(response_text, paths)
            if result is not None:
                provider = str(getattr(self.llm, "provider", "llm"))
                source = provider if provider in {"anthropic", "openai", "remote"} else "llm"
                return _classification(result.category, result.confidence, source, channel, paths)
        category, confidence = _deterministic_category(response_text, paths)
        source = "deterministic" if confidence > 0 else "fallback"
        return _classification(category, max(confidence, 0.25), source, channel, paths)

    def _classify_with_ai(
        self,
        response_text: str,
        paths: list[ReplyPath],
    ) -> ClassifiedResponse | None:
        assert self.llm is not None
        try:
            result = self.llm.generate_object(
                task="outreach_response_classification",
                system=(
                    "Classify the prospect response into exactly one supplied category. Do not invent "
                    "a category. Confidence must reflect ambiguity."
                ),
                prompt="Choose the closest response category.",
                response_model=ClassifiedResponse,
                context={
                    "response": response_text,
                    "categories": [
                        {"key": path.key, "label": path.label, "keywords": path.keywords}
                        for path in paths
                    ],
                },
            )
            return result if any(path.key == result.category for path in paths) else None
        except Exception as exc:
            logger.warning("outreach_classification_fallback error=%s", exc.__class__.__name__)
            return None


def _deterministic_category(response_text: str, paths: list[ReplyPath]) -> tuple[str, float]:
    normalized = response_text.casefold()
    scored = [
        (
            sum(1 for keyword in path.keywords if keyword.casefold() in normalized),
            path.key,
        )
        for path in paths
    ]
    scored.sort(reverse=True)
    if scored and scored[0][0] > 0:
        matches = scored[0][0]
        return scored[0][1], min(0.95, 0.55 + matches * 0.15)
    fallback = next((path.key for path in paths if path.key == "not_considered"), paths[0].key if paths else "unknown")
    return fallback, 0.0


def _classification(
    category: str,
    confidence: float,
    source: Literal["deterministic", "anthropic", "openai", "remote", "llm", "fallback"],
    channel: Literal["message", "call", "form", "email"],
    paths: list[ReplyPath],
) -> OutreachResponseClassification:
    path = next((item for item in paths if item.key == category), None)
    return OutreachResponseClassification(
        category=category,
        label=path.label if path else "Needs review",
        confidence=confidence,
        source=source,
        suggested_reply=path.channel_replies.get(channel) if path else None,
        path=path,
    )
