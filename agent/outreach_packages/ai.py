from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from agents.llm import LLMClient
from outreach_packages.schemas import (
    GeneratedOutreach,
    GeneratedOutreachResponse,
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
from shared.errors import ConfigurationError
from shared.logger import get_logger


logger = get_logger(__name__)
OUTREACH_GENERATION_PROMPT_VERSION = 5

PERSUASION_STYLE_INSTRUCTIONS = {
    "friendly_adviser": (
        "Friendly adviser: begin with one verified positive detail when available, introduce one useful "
        "opportunity gently, offer one practical idea, then ask permission to share or discuss it."
    ),
    "direct_specialist": (
        "Direct specialist: state the verified opportunity early, connect it to one concrete customer "
        "benefit, recommend one practical improvement, then ask for a clear low-effort next step."
    ),
    "curious_consultant": (
        "Curious consultant: mention one verified observation, ask one relevant discovery question, then "
        "briefly explain the idea that could help depending on their answer. Do not turn it into an interview."
    ),
    "visual_demonstrator": (
        "Visual demonstrator: lead with the supplied concept or proof when one exists; otherwise lead with "
        "one concrete visual idea. Connect it to one business benefit and ask for their reaction."
    ),
}


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
        persuasion_instruction = PERSUASION_STYLE_INSTRUCTIONS[
            outreach_input.persuasion_style
        ]
        selected_structure = (
            outreach_input.message_structure.strip()
            if outreach_input.message_structure
            else persuasion_instruction
        )
        example_instruction = (
            "The user supplied an example message. Reproduce only its order, pacing, and rhetorical shape. "
            "Never copy its names, numbers, links, claims, compliments, or business details unless the same "
            "fact is present in the supplied JSON."
            if outreach_input.example_message
            else "No example message was supplied."
        )
        system = (
            "Create grounded outreach for a local business from the supplied JSON only. "
            "Never invent compliments, projects, reviews, results, contact details, links, prices, "
            "or website findings. Treat lead evidence as an observation, not proof of lost revenue. "
            "Frame the proposal as a potential gain without criticizing the business. Use the optional "
            "personal detail, concept URL, and concept features only when supplied. Return one shared "
            "proposal plus channel-specific drafts. Preserve the selected persuasion structure while "
            "adapting its wording to each channel. Proof may appear only when a real concept URL exists. "
            "Instagram should be conversational and no more than 110 words. SMS must fit in 160 characters. "
            "Email may be fuller but must stay under 180 words. A call must take roughly 20 to 30 seconds: "
            "at most 65 words total, no more than two short talking points, and one question. Omit proof claims when no concept URL "
            "exists. Generate only the channels listed in outreach_input.channels and return null for "
            "every unselected channel. Follow every length and structural constraint in the response schema. "
            "Follow the user's message structure in the stated order. Treat it as a format, not as factual "
            "content. Optional sections must be omitted when the supplied evidence does not support them. "
            "Do not fill missing sections with generic claims. "
            f"Selected message structure: {selected_structure}. {example_instruction}"
        )
        prompt = (
            "Generate a proposal and outreach drafts that preserve the same factual substance across "
            "channels while adapting length and delivery to each channel."
        )
        context = {
            "prompt_version": OUTREACH_GENERATION_PROMPT_VERSION,
            "business": business,
            "sender": sender,
            "verified_evidence": [item.model_dump() for item in evidence],
            "outreach_input": outreach_input.model_dump(),
            "persuasion_structure": persuasion_instruction,
            "selected_message_structure": selected_structure,
            "example_message": outreach_input.example_message,
            "fallback_proposal": fallback_proposal.model_dump(),
        }
        try:
            generated = self._request(
                system=system,
                prompt=prompt,
                context=context,
            )
        except PydanticValidationError as exc:
            validation_feedback = exc.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
            try:
                generated = self._request(
                    system=(
                        f"{system} Your previous structured response failed validation. "
                        "Correct only the invalid fields and return the complete object again."
                    ),
                    prompt=f"{prompt}\nValidation errors: {validation_feedback}",
                    context=context,
                )
            except PydanticValidationError as retry_exc:
                raise ConfigurationError(
                    "The LLM returned invalid outreach after one corrective retry.",
                    {
                        "provider": str(getattr(self.llm, "provider", "unknown")),
                        "model": getattr(self.llm, "model", None),
                        "validation_errors": retry_exc.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        ),
                        "user_message": (
                            "The generated outreach did not match the required format. Try generating again."
                        ),
                    },
                ) from retry_exc
        selected = set(outreach_input.channels)
        channels = generated.channels.model_copy(
            update={
                "instagram": generated.channels.instagram if "instagram" in selected else None,
                "sms": generated.channels.sms if "sms" in selected else None,
                "email": generated.channels.email if "email" in selected else None,
                "call": generated.channels.call if "call" in selected else None,
            }
        )
        return GeneratedOutreach.model_validate(
            generated.model_copy(
                update={
                    "channels": channels,
                    "prompt_version": OUTREACH_GENERATION_PROMPT_VERSION,
                }
            ).model_dump()
        )

    def _request(self, *, system: str, prompt: str, context: dict) -> GeneratedOutreachResponse:
        return self.llm.generate_object(
            task="outreach_channel_generation",
            system=system,
            prompt=prompt,
            response_model=GeneratedOutreachResponse,
            context=context,
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
