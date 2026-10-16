from outreach_packages.playbooks import PlaybookRepository, load_playbook_catalog
from outreach_packages.policy import OutreachPolicyValidator
from outreach_packages.schemas import OutreachEvidence
from outreach_packages.templates import OutreachTemplateContext, render_outreach


def test_every_catalog_signal_renders_every_channel_safely() -> None:
    catalog = load_playbook_catalog()
    repository = PlaybookRepository(catalog)
    validator = OutreachPolicyValidator()
    rendered = 0

    for service in catalog.services:
        for signal in service.signals:
            value = signal.match_values[0] if signal.match_values else 42
            evidence = OutreachEvidence(
                signal_key=signal.signal_key,
                label=signal.signal_key.replace("_", " ").title(),
                statement="Stored evidence statement.",
                value=value,
            )
            match = repository.resolve(
                service_keys=[service.service_key],
                matched_services=[],
                evidence=[evidence],
            )

            assert match is not None
            strategy = repository.strategy_for(
                match,
                stable_key=f"business:{service.service_key}:{signal.signal_key}",
            )
            generation = render_outreach(
                OutreachTemplateContext(
                    business_name="Example Business",
                    strategy=strategy,
                    signature="Example Studio",
                )
            )
            validator.validate(strategy=strategy, generation=generation)

            assert generation.message.body.endswith("?")
            assert strategy.observation in generation.message.body
            assert strategy.observation in generation.form.body
            assert strategy.observation in generation.email.body
            assert strategy.observation == generation.call.observation
            assert generation.call.discovery_question
            assert generation.call.branches
            assert len(generation.message.body) <= 460
            assert len(generation.form.body) <= 900
            assert len(generation.email.body) <= 1200
            rendered += 1

    assert rendered == 35


def test_playbook_variant_is_stable_for_the_same_result() -> None:
    repository = PlaybookRepository()
    evidence = OutreachEvidence(
        signal_key="website_status",
        label="Website status",
        statement="Stored evidence statement.",
        value="not_listed",
    )
    match = repository.resolve(
        service_keys=["website_modernization"],
        matched_services=[],
        evidence=[evidence],
    )

    assert match is not None
    first = repository.strategy_for(match, stable_key="result:one")
    second = repository.strategy_for(match, stable_key="result:one")

    assert first.selected_variant == second.selected_variant
    assert first.permission == second.permission
