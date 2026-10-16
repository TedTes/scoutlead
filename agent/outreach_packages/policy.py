from __future__ import annotations

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
        if strategy.observation.casefold() not in rendered:
            raise ValidationError("Outreach draft does not include its grounded observation.")
        prohibited = [
            claim for claim in strategy.prohibited_claims if claim.casefold() in rendered
        ]
        if prohibited:
            raise ValidationError(
                "Outreach draft contains a prohibited claim.",
                {"claims": prohibited},
            )
        if not generation.message.body.rstrip().endswith("?"):
            raise ValidationError("Text outreach must end with one clear next-step question.")
