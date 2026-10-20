from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from outreach_packages.schemas import (
    CallDraft,
    EmailDraft,
    OutreachGeneration,
    OutreachStrategy,
    WrittenDraft,
)


@dataclass(frozen=True, slots=True)
class OutreachTemplateContext:
    business_name: str
    strategy: OutreachStrategy
    signature: str


class PhrasingAdapter(Protocol):
    provider: str

    def render(self, context: OutreachTemplateContext) -> OutreachGeneration: ...


class TextRenderer:
    def render(self, context: OutreachTemplateContext) -> WrittenDraft:
        strategy = context.strategy
        relevance = " ".join(
            value
            for value in [
                strategy.customer_consequence,
                strategy.uncertainty_clause,
            ]
            if value
        )
        close = f"{strategy.seller_positioning} {strategy.next_step}"
        return WrittenDraft(
            body=_sentence_limit(
                "\n\n".join(
                    [f"Hi {context.business_name},", strategy.observation, relevance, close]
                ),
                560,
            )
        )


class CallRenderer:
    def render(self, context: OutreachTemplateContext) -> CallDraft:
        strategy = context.strategy
        return CallDraft(
            opener=_sentence_limit(
                f"Hi, is this the owner or manager at {context.business_name}?",
                240,
            ),
            permission=_sentence_limit(strategy.permission, 240),
            observation=_sentence_limit(
                " ".join(
                    value
                    for value in [strategy.observation, strategy.uncertainty_clause]
                    if value
                ),
                320,
            ),
            discovery_question=_sentence_limit(strategy.discovery_question, 320),
            ask=_sentence_limit(strategy.next_step, 240),
            branches=strategy.call_branches,
        )


class FormRenderer:
    def render(self, context: OutreachTemplateContext) -> WrittenDraft:
        strategy = context.strategy
        return WrittenDraft(
            body=_sentence_limit(
                "\n\n".join(
                    value
                    for value in [
                        f"Hello {context.business_name} team,",
                        strategy.observation,
                        strategy.customer_consequence,
                        strategy.uncertainty_clause,
                        strategy.seller_positioning,
                        strategy.next_step,
                        f"Thanks,\n{context.signature}",
                    ]
                    if value
                ),
                900,
            )
        )


class EmailRenderer:
    def render(self, context: OutreachTemplateContext) -> EmailDraft:
        return EmailDraft(
            subject=_sentence_limit(_email_subject(context.strategy), 120),
            body=_long_body(context, limit=1200),
        )


class DeterministicPhrasingAdapter:
    provider = "deterministic"

    def render(self, context: OutreachTemplateContext) -> OutreachGeneration:
        return OutreachGeneration(
            message=TextRenderer().render(context),
            call=CallRenderer().render(context),
            form=FormRenderer().render(context),
            email=EmailRenderer().render(context),
        )


def render_outreach(
    context: OutreachTemplateContext,
    *,
    phrasing: PhrasingAdapter | None = None,
) -> OutreachGeneration:
    return (phrasing or DeterministicPhrasingAdapter()).render(context)


def _email_subject(strategy: OutreachStrategy) -> str:
    key = strategy.primary_signal_key
    if key in {"google_rating", "google_review_count", "reviews_under_15"}:
        return "Quick question about your online reputation"
    if strategy.service_key == "booking_payments":
        return "Quick question about your quote process"
    if strategy.service_key == "lead_capture":
        return "Quick question about website inquiries"
    if strategy.service_key == "performance_accessibility":
        return "Quick question about your website experience"
    if strategy.service_key == "local_visibility":
        return "Quick question about local search"
    if strategy.service_key == "multilingual_localization":
        return "Quick question about website languages"
    return "Quick question about your website"


def _long_body(context: OutreachTemplateContext, *, limit: int) -> str:
    strategy = context.strategy
    return _sentence_limit(
        "\n\n".join(
            value
            for value in [
                f"Hi {context.business_name} team,",
                strategy.observation,
                strategy.customer_consequence,
                strategy.uncertainty_clause,
                strategy.value_hypothesis,
                strategy.seller_positioning,
                strategy.next_step,
                f"Thanks,\n{context.signature}",
            ]
            if value
        ),
        limit,
    )


def _sentence_limit(value: str, length: int) -> str:
    compact = _clean_lines(value)
    if len(compact) <= length:
        return compact
    candidate = compact[: length + 1]
    boundaries = [match.end() for match in re.finditer(r"[.!?](?=\s|$)", candidate)]
    if boundaries and boundaries[-1] >= max(20, int(length * 0.55)):
        return candidate[: boundaries[-1]].rstrip()
    return f"{compact[: length - 3].rstrip()}..."


def _clean_lines(value: str) -> str:
    return "\n".join(" ".join(line.split()) for line in value.strip().splitlines())
