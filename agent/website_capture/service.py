from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_attributes.repository import (
    BusinessAttributeRepository,
    BusinessAttributeValue,
)
from db.models import BusinessAttributeModel, BusinessModel
from shared.errors import NotFoundError, ValidationError
from website_assessments.service import WebsiteAssessmentService
from website_capture.contracts import (
    ArtifactStore,
    BrowserCaptureProvider,
    WebsiteVisionModel,
    capture_without_screenshots,
)
from website_capture.vision import NoopWebsiteVisionModel


CAPTURE_ATTRIBUTE_KEY = "website_visual_capture"


class WebsiteCaptureService:
    def __init__(
        self,
        session: Session,
        *,
        browser: BrowserCaptureProvider,
        artifacts: ArtifactStore,
        vision: WebsiteVisionModel | None = None,
        freshness_days: int = 7,
    ) -> None:
        self.session = session
        self.browser = browser
        self.artifacts = artifacts
        self.vision = vision or NoopWebsiteVisionModel()
        self.freshness_days = max(0, freshness_days)

    def capture(
        self,
        business_id: str,
        *,
        force: bool = False,
        commit: bool = True,
    ) -> dict[str, Any]:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        website_url = str(business.website_url or "").strip()
        if not website_url:
            raise ValidationError(
                "business has no website URL to capture",
                {"business_id": business_id},
            )

        existing_capture = self._current_capture(business_id)
        if not force and _capture_is_fresh(
            existing_capture,
            website_url=website_url,
            freshness_days=self.freshness_days,
        ):
            assessment = WebsiteAssessmentService(self.session).assess(
                business_id,
                commit=commit,
            )
            return {
                "capture": existing_capture,
                "assessment": assessment,
                "cached": True,
            }

        result = self.browser.capture(website_url)
        artifact_uris: dict[str, str] = {}
        artifact_details: dict[str, dict[str, Any]] = {}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for viewport in result.viewports:
            stored = self.artifacts.put(
                business_id=business_id,
                name=f"{stamp}-{viewport.name}.png",
                content=viewport.screenshot,
                content_type="image/png",
            )
            artifact_uris[viewport.name] = stored.uri
            artifact_details[viewport.name] = {
                "uri": stored.uri,
                "content_type": stored.content_type,
                "size_bytes": stored.size_bytes,
            }

        vision = self.vision.assess(capture=result, artifact_uris=artifact_uris)
        observed_at = datetime.now(timezone.utc)
        payload = {
            **capture_without_screenshots(result),
            "capture_provider": self.browser.key,
            "artifact_store": self.artifacts.key,
            "artifacts": artifact_details,
            "vision": vision,
            "vision_model": {
                "key": self.vision.key,
                "version": self.vision.version,
            },
            "schema_version": 1,
        }
        BusinessAttributeRepository(self.session).upsert(
            business_id,
            BusinessAttributeValue(
                key=CAPTURE_ATTRIBUTE_KEY,
                value=payload,
                observed_at=observed_at,
                confidence=100,
                source_provider=f"browser:{self.browser.key}",
                source_url=result.final_url,
                evidence={
                    "artifact_store": self.artifacts.key,
                    "capture_provider": self.browser.key,
                },
            ),
            commit=False,
        )
        assessment = WebsiteAssessmentService(self.session).assess(
            business_id,
            commit=False,
        )
        if commit:
            self.session.commit()
        return {"capture": payload, "assessment": assessment, "cached": False}

    def _current_capture(self, business_id: str) -> dict[str, Any] | None:
        row = self.session.scalar(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == business_id,
                BusinessAttributeModel.attribute_key == CAPTURE_ATTRIBUTE_KEY,
            )
        )
        if row is None or row.value_type != "json" or not isinstance(row.value_json, dict):
            return None
        return row.value_json


def _capture_is_fresh(
    capture: dict[str, Any] | None,
    *,
    website_url: str,
    freshness_days: int,
) -> bool:
    if capture is None or freshness_days <= 0:
        return False
    requested_url = str(capture.get("requested_url") or "").rstrip("/")
    if requested_url != website_url.rstrip("/"):
        return False
    captured_at = capture.get("captured_at")
    if not isinstance(captured_at, str):
        return False
    try:
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= datetime.now(timezone.utc) - timedelta(days=freshness_days)
