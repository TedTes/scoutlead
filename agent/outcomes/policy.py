from datetime import datetime, timedelta

from outcomes.schemas import LeadOutcome


POSITIVE_OUTCOMES = {
    LeadOutcome.REPLIED_POSITIVE,
    LeadOutcome.MEETING_BOOKED,
    LeadOutcome.WON,
}

CONTACT_ATTEMPT_OUTCOMES = {
    LeadOutcome.CONTACTED,
    LeadOutcome.NO_ANSWER,
    LeadOutcome.VOICEMAIL,
    LeadOutcome.MESSAGE_SENT,
    LeadOutcome.REACHED,
}

DATA_QUALITY_OUTCOMES = {
    LeadOutcome.BOUNCED,
    LeadOutcome.WRONG_CONTACT,
    LeadOutcome.BUSINESS_CLOSED,
}


def is_positive_outcome(outcome: LeadOutcome | str) -> bool:
    return LeadOutcome(outcome) in POSITIVE_OUTCOMES


def no_response_due(
    *,
    contacted_at: datetime,
    latest_outcome: LeadOutcome | str,
    now: datetime,
    days: int,
) -> bool:
    return (
        LeadOutcome(latest_outcome) == LeadOutcome.CONTACTED
        and contacted_at + timedelta(days=days) <= now
    )
