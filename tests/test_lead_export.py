import csv
from datetime import UTC, datetime
from io import StringIO

from leads.export import EXPORT_COLUMNS, leads_csv
from leads.schemas import LeadRead, LeadStatus


def test_contact_export_contains_only_contact_fields() -> None:
    now = datetime.now(UTC)
    lead = LeadRead(
        id="lead_test",
        campaign_id="campaign_test",
        product_id="product_test",
        company_name="Example Painting",
        website_url="https://example.test",
        contact_email="owner@example.test",
        geography="Toronto, ON",
        source="google_places",
        raw_sources=[
            {
                "formattedAddress": "10 King St, Toronto, ON",
                "nationalPhoneNumber": "(416) 555-0100",
            }
        ],
        status=LeadStatus.RESEARCHED,
        created_at=now,
        updated_at=now,
    )

    rows = list(csv.DictReader(StringIO(leads_csv([lead], scoutlead_path="/ignored"))))

    assert list(rows[0]) == EXPORT_COLUMNS
    assert rows[0] == {
        "business": "Example Painting",
        "contact_name": "",
        "email": "owner@example.test",
        "phone": "(416) 555-0100",
        "address": "10 King St, Toronto, ON",
        "website": "https://example.test",
    }
