from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from business_attributes.repository import (
    BusinessAttributeRepository,
    BusinessAttributeValue,
    attribute_value,
)
from db.models import BusinessAttributeModel, BusinessModel
from db.session import create_database
from shared.utils import new_id, utcnow
from website_assessments.contracts import WebsiteAssessmentFeatures
from website_assessments.models import LinearWebsiteAssessmentModel
from website_assessments.service import (
    ASSESSMENT_KEY,
    TRAINING_LABEL_KEY,
    WebsiteAssessmentService,
)
from website_assessments.training import TrainingExample, train_logistic_baseline
from website_capture.contracts import ViewportCapture, WebsiteCaptureResult
from website_capture.service import CAPTURE_ATTRIBUTE_KEY, WebsiteCaptureService
from website_capture.storage import LocalArtifactStore, S3ArtifactStore


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session, *, website_url="https://example.test"):
    now = utcnow()
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example Business",
        normalized_name="example business",
        geography="Toronto",
        market_key="toronto",
        category_key="home_service_painting",
        website_url=website_url,
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(business)
    session.commit()
    return business


def _attribute(session, business, key, value):
    return BusinessAttributeRepository(session).upsert(
        business.id,
        BusinessAttributeValue(
            key=key,
            value=value,
            observed_at=utcnow(),
            confidence=95,
            source_provider="test",
        ),
        commit=True,
    )


def test_business_attribute_repository_round_trips_json_values() -> None:
    with _session_factory()() as session:
        business = _business(session)
        row = _attribute(session, business, "website_upgrade_assessment", {"score": 0.72})
        assert row.value_type == "json"
        assert attribute_value(row) == {"score": 0.72}
        assert row.value_text is None


def test_baseline_marks_missing_website_as_high_priority() -> None:
    features = WebsiteAssessmentFeatures(
        business_id="business_1",
        website_url=None,
        values={"website_missing": 1.0},
        evidence={"website_missing": {"confidence": 100, "fresh": True}},
    )
    result = LinearWebsiteAssessmentModel().predict(features)
    assert result.upgrade_probability >= 0.98
    assert result.label.value == "broken"
    assert "No business website was found" in result.reasons


def test_service_persists_shadow_assessment_and_human_label() -> None:
    with _session_factory()() as session:
        business = _business(session, website_url=None)
        _attribute(session, business, "website_status", "missing")
        service = WebsiteAssessmentService(session)
        assessment = service.assess(business.id)
        assert assessment["mode"] == "shadow"
        assert assessment["upgrade_probability"] >= 0.98

        label = service.save_label(
            business.id,
            label="upgrade_candidate",
            reasons=["Visual design looks dated"],
            notes="Human review",
            desktop_screenshot_url="https://assets.example/desktop.png",
            mobile_screenshot_url=None,
            labeled_by="admin@example.com",
        )
        assert label["label"] == "upgrade_candidate"
        rows = {
            row.attribute_key: row
            for row in session.scalars(
                select(BusinessAttributeModel).where(
                    BusinessAttributeModel.business_id == business.id,
                    BusinessAttributeModel.attribute_key.in_(
                        [ASSESSMENT_KEY, TRAINING_LABEL_KEY]
                    ),
                )
            )
        }
        assert attribute_value(rows[ASSESSMENT_KEY])["mode"] == "shadow"
        assert attribute_value(rows[TRAINING_LABEL_KEY])["labeled_by"] == "admin@example.com"


def test_local_trainer_learns_upgrade_direction_without_sklearn() -> None:
    examples = [
        TrainingExample(
            WebsiteAssessmentFeatures("good", "https://good.test", {"performance_gap": 0.05}),
            "strong",
        ),
        TrainingExample(
            WebsiteAssessmentFeatures("bad", "https://bad.test", {"performance_gap": 0.95}),
            "upgrade_candidate",
        ),
    ]
    _, coefficients = train_logistic_baseline(examples, epochs=1200)
    assert coefficients["performance_gap"] > 0


class _FakeBrowserCapture:
    key = "fake_browser"

    def __init__(self) -> None:
        self.calls = 0

    def capture(self, url: str) -> WebsiteCaptureResult:
        self.calls += 1
        return WebsiteCaptureResult(
            requested_url=url,
            final_url=url,
            captured_at=utcnow().isoformat(),
            title="Example Business",
            viewports=[
                ViewportCapture(
                    name="desktop",
                    width=1440,
                    height=1000,
                    screenshot=b"desktop-png",
                    metrics={"heading_count": 4, "word_count": 300},
                ),
                ViewportCapture(
                    name="mobile",
                    width=390,
                    height=844,
                    screenshot=b"mobile-png",
                    metrics={
                        "horizontal_overflow_px": 120,
                        "small_tap_target_ratio": 0.5,
                    },
                ),
            ],
            page_metrics={
                "mobile_horizontal_overflow_px": 120,
                "mobile_small_tap_target_ratio": 0.5,
                "heading_count": 4,
                "word_count": 300,
                "broken_image_count": 0,
            },
        )


def test_capture_service_stores_local_artifacts_and_updates_assessment(tmp_path) -> None:
    with _session_factory()() as session:
        business = _business(session)
        result = WebsiteCaptureService(
            session,
            browser=_FakeBrowserCapture(),
            artifacts=LocalArtifactStore(tmp_path),
        ).capture(business.id)

        capture_row = session.scalar(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == business.id,
                BusinessAttributeModel.attribute_key == CAPTURE_ATTRIBUTE_KEY,
            )
        )
        capture = attribute_value(capture_row)
        assert capture["capture_provider"] == "fake_browser"
        assert capture["artifacts"]["desktop"]["uri"].startswith("file:")
        assert "screenshot" not in capture["viewports"][0]
        assert result["assessment"]["features"]["values"]["mobile_overflow_gap"] == 1.0


def test_capture_service_reuses_fresh_capture_unless_forced(tmp_path) -> None:
    with _session_factory()() as session:
        business = _business(session)
        browser = _FakeBrowserCapture()
        service = WebsiteCaptureService(
            session,
            browser=browser,
            artifacts=LocalArtifactStore(tmp_path),
            freshness_days=7,
        )

        first = service.capture(business.id)
        cached = service.capture(business.id)
        forced = service.capture(business.id, force=True)

        assert first["cached"] is False
        assert cached["cached"] is True
        assert forced["cached"] is False
        assert browser.calls == 2


class _FakeS3Client:
    def __init__(self) -> None:
        self.requests = []

    def put_object(self, **request) -> None:
        self.requests.append(request)


def test_s3_artifact_store_uploads_private_object_and_returns_stable_uri() -> None:
    client = _FakeS3Client()
    store = S3ArtifactStore(
        bucket="capture-bucket",
        prefix="scoutlead/captures/",
        client=client,
    )

    stored = store.put(
        business_id="business/123",
        name="desktop capture.png",
        content=b"png-bytes",
        content_type="image/png",
    )

    assert stored.uri == (
        "s3://capture-bucket/scoutlead/captures/business-123/desktop-capture.png"
    )
    assert stored.size_bytes == 9
    assert client.requests == [
        {
            "Bucket": "capture-bucket",
            "Key": "scoutlead/captures/business-123/desktop-capture.png",
            "Body": b"png-bytes",
            "ContentType": "image/png",
        }
    ]


def test_capture_service_persists_s3_references_in_attributes() -> None:
    with _session_factory()() as session:
        business = _business(session)
        client = _FakeS3Client()
        result = WebsiteCaptureService(
            session,
            browser=_FakeBrowserCapture(),
            artifacts=S3ArtifactStore(
                bucket="capture-bucket",
                prefix="website-captures",
                client=client,
            ),
        ).capture(business.id)

        capture_row = session.scalar(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == business.id,
                BusinessAttributeModel.attribute_key == CAPTURE_ATTRIBUTE_KEY,
            )
        )
        capture = attribute_value(capture_row)

        assert result["cached"] is False
        assert capture["artifact_store"] == "s3"
        assert capture["artifacts"]["desktop"]["uri"].startswith(
            f"s3://capture-bucket/website-captures/{business.id}/"
        )
        assert capture["artifacts"]["mobile"]["uri"].startswith(
            f"s3://capture-bucket/website-captures/{business.id}/"
        )
        assert "screenshot" not in capture["viewports"][0]
        assert len(client.requests) == 2
