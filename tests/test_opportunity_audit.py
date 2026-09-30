from canonical.website_enrichment import EnrichmentSummary
from territories.opportunity_audit import BusinessOpportunityAuditor


def test_campaign_opportunity_audit_refreshes_existing_evidence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class EmptySession:
        def scalars(self, statement):
            return []

    def fake_enrich(session, **kwargs):
        captured.update(kwargs)
        return EnrichmentSummary(dry_run=False)

    monkeypatch.setattr("territories.opportunity_audit.enrich_business_pool", fake_enrich)
    auditor = BusinessOpportunityAuditor(
        session=EmptySession(),
        verifier=None,
        timeout_seconds=1,
    )

    auditor.audit_campaign("campaign_test", category="painting", market="Toronto")

    assert captured["refresh"] is True
