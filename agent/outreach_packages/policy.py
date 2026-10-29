from __future__ import annotations

import re

from outreach_packages.schemas import OutreachGeneration, OutreachStrategy
from shared.errors import ValidationError


class OutreachPolicyValidator:
    def validate(
        self,
        *,
        strategy: OutreachStrategy,
        generation: OutreachGeneration,
    ) -> None:
        rendered = "\n".join(
            [
                generation.message.body,
                generation.call.opener,
                generation.call.permission or "",
                generation.call.observation,
                generation.call.discovery_question or "",
                generation.call.ask,
                generation.form.body,
                generation.email.subject,
                generation.email.body,
            ]
        ).casefold()
        channel_bodies = {
            "message": generation.message.body,
            "call": " ".join(
                filter(
                    None,
                    [generation.call.observation, generation.call.discovery_question, generation.call.ask],
                )
            ),
            "form": generation.form.body,
            "email": generation.email.body,
        }
        missing_observation = [
            channel
            for channel, body in channel_bodies.items()
            if strategy.observation.casefold() not in body.casefold()
        ]
        if missing_observation:
            raise ValidationError(
                "Every outreach channel must include its grounded observation.",
                {"channels": missing_observation},
            )
        prohibited = [
            claim for claim in strategy.prohibited_claims if claim.casefold() in rendered
        ]
        if prohibited:
            raise ValidationError(
                "Outreach draft contains a prohibited claim.",
                {"claims": prohibited},
            )
        unsafe_patterns = {
            "guaranteed outcome": r"\b(?:guarantee|guaranteed|will increase|will generate)\b",
            "unsupported loss claim": r"\b(?:losing customers|losing leads|missing out on customers)\b",
            "unsupported price claim": r"(?:[$£€]\s?\d|\b\d[\d,]*\s*(?:dollars|usd|cad)\b)",
        }
        unsafe = [label for label, pattern in unsafe_patterns.items() if re.search(pattern, rendered, re.I)]
        if unsafe:
            raise ValidationError(
                "Outreach draft contains an unsupported sales claim.",
                {"claims": unsafe},
            )
        if strategy.primary_signal_key == "website_status" and strategy.primary_signal_value in {
            "not_listed",
            "missing",
        }:
            unsupported_no_site = re.search(
                r"\b(?:you|your business)\s+(?:do not|don't|does not|doesn't|has no)\s+(?:have\s+)?(?:a\s+)?website\b",
                rendered,
            )
            if unsupported_no_site:
                raise ValidationError(
                    "A missing listing link cannot be presented as proof that no website exists."
                )
        hypotheses = [claim for claim in strategy.claim_ledger if claim.kind == "hypothesis"]
        unqualified = [
            claim.text
            for claim in hypotheses
            if not re.search(r"\b(?:may|might|could|potential|possible)\b", claim.text, re.I)
        ]
        if unqualified:
            raise ValidationError(
                "Outreach hypotheses must be expressed as possibilities, not facts.",
                {"claims": unqualified},
            )
        evidence_claims = [claim for claim in strategy.claim_ledger if claim.kind == "evidence"]
        if not evidence_claims or any(
            strategy.primary_signal_key not in claim.evidence_keys for claim in evidence_claims
        ):
            raise ValidationError("Every factual outreach claim must reference stored evidence.")
        validate_text_message(generation.message.body)


def validate_text_message(body: str) -> None:
    if not body.rstrip().endswith("?"):
        raise ValidationError("Text outreach must end with one clear next-step question.")
    if len(body) > 160:
        raise ValidationError("Text outreach must fit in one 160-character SMS segment.")
    if re.search(
        r"\b(?:send|show|share|prepare|make|create)\b.{0,30}\b(?:example|preview|mockup)\b",
        body,
        re.I,
    ):
        raise ValidationError(
            "Text outreach cannot promise an example or preview that was not generated."
        )
