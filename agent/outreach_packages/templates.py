from __future__ import annotations

from dataclasses import dataclass
import re

from outreach_packages.schemas import (
    CallDraft,
    EmailDraft,
    OutreachEvidence,
    OutreachGeneration,
    WrittenDraft,
)


@dataclass(frozen=True, slots=True)
class OutreachTemplateContext:
    business_name: str
    evidence: OutreachEvidence
    offer: str
    call_to_action: str | None
    signature: str
    demo_path: str | None = None


def render_outreach(context: OutreachTemplateContext) -> OutreachGeneration:
    observation = _conversational_observation(context.evidence)
    offer = _offer_sentence(context.offer, context.evidence)
    ask = _call_to_action(context.call_to_action, context.evidence)
    demo = f" Here is a short example: {context.demo_path}." if context.demo_path else ""

    message = _limit(
        "\n\n".join(
            [
                f"Hi {context.business_name},",
                observation,
                f"{offer}{demo} {ask}",
            ]
        ),
        900,
    )
    form = _limit(
        "\n\n".join(
            [
                f"Hi {context.business_name} team,",
                observation,
                f"{offer}{demo}",
                ask,
                f"Thanks,\n{context.signature}",
            ]
        ),
        900,
    )
    email = _limit(
        "\n\n".join(
            [
                f"Hi {context.business_name} team,",
                observation,
                f"{offer}{demo}",
                ask,
                f"Thanks,\n{context.signature}",
            ]
        ),
        1200,
    )
    return OutreachGeneration(
        message=WrittenDraft(body=message),
        call=CallDraft(
            opener=_limit(
                f"Hi, is this the owner or manager at {context.business_name}?",
                240,
            ),
            observation=_limit(observation, 320),
            ask=_limit(ask, 240),
        ),
        form=WrittenDraft(body=form),
        email=EmailDraft(
            subject=_limit(_email_subject(context.evidence), 120),
            body=email,
        ),
    )


def _conversational_observation(evidence: OutreachEvidence) -> str:
    key = evidence.signal_key
    value = evidence.value
    observations = {
        "website_unavailable": "Your website was unavailable during the latest check.",
        "no_quote_flow": "Your website does not currently show a quote or booking option.",
        "no_contact_form": "The latest website check did not find a contact form.",
        "mobile_viewport_missing": "The latest website check did not find a mobile viewport declaration.",
        "uses_http": "The latest website check found that the site is not using HTTPS.",
    }
    if key == "website_status" and value == "not_listed":
        return "I noticed your business listing doesn't include a website."
    if key == "reviews_under_15":
        return f"Your business has {int(value or 0)} public reviews in the latest record."
    return observations.get(key, _sentence(evidence.statement))


def _offer_sentence(offer: str, evidence: OutreachEvidence) -> str:
    if evidence.signal_key == "website_status" and evidence.value == "not_listed":
        return "I help local service businesses launch modern websites that generate more quote requests."
    compact_offer = _compact(offer).rstrip(".!?")[:320]
    if re.match(r"^(i|we)\b", compact_offer, flags=re.IGNORECASE):
        return _sentence(compact_offer)
    first_word = compact_offer.split(" ", 1)[0]
    sentence_offer = compact_offer if first_word.isupper() else compact_offer[0].lower() + compact_offer[1:]
    return _sentence(f"I offer {sentence_offer}")


def _call_to_action(value: str | None, evidence: OutreachEvidence) -> str:
    if evidence.signal_key == "website_status" and evidence.value == "not_listed":
        return "Would you be open to seeing a quick example?"
    if not value:
        return "Would a short example be useful?"
    text = _compact(value).rstrip(".!?")
    lowered = text.lower()
    if lowered.startswith("ask whether "):
        proposition = text[12:]
        match = re.fullmatch(r"(.+?) would (.+)", proposition, flags=re.IGNORECASE)
        if match:
            return _question(f"Would {match.group(1)} {match.group(2)}")
        return _question(proposition)
    if lowered.startswith("ask for "):
        return _question(f"Would you be open to {text[8:]}")
    if lowered.startswith("start "):
        return "Would you be open to a quick conversation?"
    if re.match(r"^(would|could|can|is|are|do|does|may|should)\b", lowered):
        return _question(text)
    return _question(f"Would you be open to {text[0].lower() + text[1:]}")


def _email_subject(evidence: OutreachEvidence) -> str:
    if evidence.signal_key == "reviews_under_15":
        return "Quick question about your online reviews"
    if evidence.signal_key.startswith("website") or evidence.signal_key in {
        "no_quote_flow",
        "no_contact_form",
        "mobile_viewport_missing",
        "uses_http",
    }:
        return "Quick question about your website"
    return "Quick question about your business"


def _sentence(value: str) -> str:
    text = _compact(value)
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _question(value: str) -> str:
    return f"{_compact(value).rstrip('.!?')}?"


def _compact(value: str) -> str:
    return " ".join(value.split())


def _limit(value: str, length: int) -> str:
    if len(value) <= length:
        return value
    return f"{value[: length - 3].rstrip()}..."
