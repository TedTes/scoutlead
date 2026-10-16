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
            for variant_offset in range(3):
                strategy = repository.strategy_for(
                    match,
                    stable_key=f"business:{service.service_key}:{signal.signal_key}",
                    trade_key="painters",
                    variant_offset=variant_offset,
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
                assert strategy.observation in generation.call.observation
                assert generation.call.discovery_question
                assert generation.call.branches
                assert strategy.reply_paths
                assert strategy.claim_ledger
                assert len(generation.message.body) <= 560
                assert len(generation.form.body) <= 900
                assert len(generation.email.body) <= 1200
                rendered += 1

    assert rendered == 105


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


def test_every_response_path_classifies_for_every_channel() -> None:
    repository = PlaybookRepository(load_playbook_catalog())
    service = repository.catalog.services[0]
    signal = service.signals[0]
    evidence = OutreachEvidence(
        signal_key=signal.signal_key,
        label="Website",
        statement="Stored",
        value="not_listed",
    )
    match = repository.resolve(
        service_keys=[service.service_key],
        matched_services=[],
        evidence=[evidence],
    )
    assert match is not None
    strategy = repository.strategy_for(match, stable_key="response-matrix", trade_key="painters")

    for path in strategy.reply_paths:
        for channel in ("message", "call", "form", "email"):
            result = ResponseClassifier().classify(
                response_text=path.keywords[0],
                channel=channel,
                paths=strategy.reply_paths,
            )
            assert result.category == path.key
            assert result.suggested_reply


def test_policy_rejects_unqualified_hypothesis() -> None:
    repository = PlaybookRepository(load_playbook_catalog())
    service = repository.catalog.services[0]
    signal = service.signals[0]
    evidence = OutreachEvidence(
        signal_key=signal.signal_key,
        label="Website",
        statement="Stored",
        value="not_listed",
    )
    match = repository.resolve(
        service_keys=[service.service_key],
        matched_services=[],
        evidence=[evidence],
    )
    assert match is not None
    strategy = repository.strategy_for(match, stable_key="unsafe", trade_key="painters")
    strategy.claim_ledger[1].text = "Customers are leaving the business."
    generation = render_outreach(
        OutreachTemplateContext(business_name="Example", strategy=strategy, signature="Studio")
    )

    with pytest.raises(Exception, match="hypotheses must be expressed as possibilities"):
        OutreachPolicyValidator().validate(strategy=strategy, generation=generation)
import pytest

from outreach_packages.ai import ResponseClassifier
