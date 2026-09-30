import csv
from io import StringIO

from leads.schemas import LeadRead


EXPORT_COLUMNS = [
    "business",
    "contact_name",
    "email",
    "phone",
    "address",
    "website",
]


def leads_csv(leads: list[LeadRead], *, scoutlead_path: str) -> str:
    del scoutlead_path  # Kept in the public signature for existing export routes.
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for lead in leads:
        writer.writerow(_row(lead))
    return output.getvalue()


def _row(lead: LeadRead) -> dict[str, object]:
    return {
        "business": lead.company_name,
        "contact_name": lead.research.contact_name if lead.research else "",
        "email": _export_email(lead.contact_email),
        "phone": _raw_value(
            lead,
            {"phone", "contact_phone", "telephone", "phonenumber", "nationalphonenumber"},
        )
        or "",
        "address": _raw_value(lead, {"address", "formatted_address", "formattedaddress", "street_address"})
        or lead.geography
        or "",
        "website": lead.website_url or "",
    }


def _raw_value(lead: LeadRead, keys: set[str]) -> str | None:
    stack: list[object] = list(lead.raw_sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() in keys and isinstance(item, str) and item.strip():
                    return item.strip()
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return None


def _export_email(value: str | None) -> str:
    email = (value or "").strip()
    if "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1].casefold()
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return ""
    return email
