from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import create_database
from outreach_packages.ai import OpenAIPhrasingAdapter, PhrasedSections, ResponseClassifier
from outreach_packages.playbooks import PlaybookRepository, ServicePlaybook, load_playbook_catalog
from outreach_packages.policy import OutreachPolicyValidator
from outreach_packages.repository import OutreachPlaybookRepository
from outreach_packages.schemas import OutreachEvidence
from outreach_packages.templates import OutreachTemplateContext, render_outreach


class StubLLM:
    def __init__(self, value: BaseModel | Exception) -> None:
        self.value = value

    def generate_object(self, **_kwargs):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def _strategy():
    repository = PlaybookRepository(load_playbook_catalog())
    evidence = OutreachEvidence(
        signal_key="website_status",
        label="Website",
        statement="Stored",
        value="not_listed",
    )
    match = repository.resolve(
        service_keys=["website_modernization"],
        matched_services=[],
        evidence=[evidence],
    )
    assert match is not None
    return repository.strategy_for(match, stable_key="ai-test", trade_key="painters")


def test_openai_phrasing_keeps_verified_observation_immutable() -> None:
    strategy = _strategy()
    adapter = OpenAIPhrasingAdapter(
        StubLLM(
            PhrasedSections(
                customer_consequence="That may make estimate requests harder to complete.",
                seller_positioning="I help painting businesses simplify estimate requests online.",
                value_hypothesis="A focused update could make the request path clearer.",
                next_step="Would it be useful if I sent one example?",
            )
        )
    )
    generation = render_outreach(
        OutreachTemplateContext(
            business_name="Example Painting",
            strategy=strategy,
            signature="Studio",
        ),
        phrasing=adapter,
    )

    assert adapter.last_strategy is not None
    assert adapter.last_strategy.observation == strategy.observation
    assert strategy.observation in generation.message.body
    OutreachPolicyValidator().validate(strategy=adapter.last_strategy, generation=generation)


def test_openai_failure_falls_back_to_deterministic_generation() -> None:
    strategy = _strategy()
    adapter = OpenAIPhrasingAdapter(StubLLM(RuntimeError("provider unavailable")))
    context = OutreachTemplateContext(
        business_name="Example Painting",
        strategy=strategy,
        signature="Studio",
    )

    assert render_outreach(context, phrasing=adapter) == render_outreach(context)
    assert adapter.last_strategy is None


def test_invalid_ai_classification_falls_back_to_keyword_rules() -> None:
    strategy = _strategy()
    classifier = ResponseClassifier(
        llm=StubLLM(type("Classification", (BaseModel,), {})()),
        use_ai=True,
    )
    result = classifier.classify(
        response_text="That quote was too expensive.",
        channel="email",
        paths=strategy.reply_paths,
    )

    assert result.category == "considered_expensive"
    assert result.source == "deterministic"


def test_database_playbook_override_replaces_only_matching_service() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        repository = OutreachPlaybookRepository(session)
        original = next(
            service
            for service in load_playbook_catalog().services
            if service.service_key == "website_modernization"
        )
        definition = original.model_copy(
            update={"goal": "Managed override goal."}
        ).model_dump()
        row = repository.save(
            service_key="website_modernization",
            definition=definition,
        )
        row.status = "active"
        session.commit()

        catalog = repository.catalog()
        overridden = next(
            service
            for service in catalog.services
            if service.service_key == "website_modernization"
        )
        assert isinstance(overridden, ServicePlaybook)
        assert overridden.goal == "Managed override goal."
        assert len(catalog.services) == len(load_playbook_catalog().services)
