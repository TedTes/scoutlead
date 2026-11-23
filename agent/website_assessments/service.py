from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_attributes.repository import (
    BusinessAttributeRepository,
    BusinessAttributeValue,
)
from db.models import BusinessAttributeModel, BusinessModel
from shared.errors import NotFoundError
from website_assessments.contracts import WebsiteAssessmentModel
from website_assessments.features import extract_website_features
from website_assessments.models import LinearWebsiteAssessmentModel


ASSESSMENT_KEY = "website_upgrade_assessment"
TRAINING_LABEL_KEY = "website_upgrade_training_label"


class WebsiteAssessmentService:
    def __init__(
        self,
        session: Session,
        *,
        model: WebsiteAssessmentModel | None = None,
    ) -> None:
        self.session = session
        self.model = model or _configured_model()

    def assess(self, business_id: str, *, commit: bool = True) -> dict[str, Any]:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        attributes = {
            row.attribute_key: row
            for row in self.session.scalars(
                select(BusinessAttributeModel).where(
                    BusinessAttributeModel.business_id == business_id
                )
            )
        }
        features = extract_website_features(business, attributes)
        prediction = self.model.predict(features)
        observed_at = datetime.now(timezone.utc)
        payload = {
            **prediction.as_dict(),
            "assessed_at": observed_at.isoformat(),
            "features": features.as_dict(),
            "mode": "shadow",
        }
        BusinessAttributeRepository(self.session).upsert(
            business_id,
            BusinessAttributeValue(
                key=ASSESSMENT_KEY,
                value=payload,
                observed_at=observed_at,
                confidence=round(prediction.confidence * 100),
                source_provider="local_website_assessment",
                evidence={"model_version": prediction.model_version},
            ),
            commit=commit,
        )
        return payload

    def save_label(
        self,
        business_id: str,
        *,
        label: str,
        reasons: list[str],
        notes: str | None,
        desktop_screenshot_url: str | None,
        mobile_screenshot_url: str | None,
        labeled_by: str | None,
        commit: bool = True,
    ) -> dict[str, Any]:
        if self.session.get(BusinessModel, business_id) is None:
            raise NotFoundError("business not found", {"business_id": business_id})
        observed_at = datetime.now(timezone.utc)
        payload = {
            "label": label,
            "reasons": list(dict.fromkeys(reason.strip() for reason in reasons if reason.strip())),
            "notes": notes.strip() if notes else None,
            "desktop_screenshot_url": desktop_screenshot_url or None,
            "mobile_screenshot_url": mobile_screenshot_url or None,
            "labeled_by": labeled_by,
            "labeled_at": observed_at.isoformat(),
            "schema_version": 1,
        }
        BusinessAttributeRepository(self.session).upsert(
            business_id,
            BusinessAttributeValue(
                key=TRAINING_LABEL_KEY,
                value=payload,
                observed_at=observed_at,
                confidence=100,
                source_provider="admin_label",
            ),
            commit=commit,
        )
        return payload


def _configured_model() -> WebsiteAssessmentModel:
    model_path = os.getenv("WEBSITE_ASSESSMENT_MODEL_PATH", "").strip()
    if model_path:
        return LinearWebsiteAssessmentModel.from_file(model_path)
    return LinearWebsiteAssessmentModel()
