from datetime import timedelta
from secrets import token_urlsafe
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm import LLMClient
from audience_runs.schemas import AudienceRunState
from db.models import AudienceResultModel, AudienceRunModel, BusinessModel, DemoSiteModel
from demo_sites.schemas import DemoGeneration, DemoSiteContent, DemoSiteRead, DemoSiteUpdate
from shared.errors import NotFoundError, ValidationError
from shared.utils import new_id, utcnow


class DemoSiteService:
    def __init__(self, session: Session, *, llm: LLMClient, workspace_id: str | None, provider: str, model: str | None) -> None:
        self.session, self.llm, self.workspace_id = session, llm, workspace_id
        self.provider, self.model = provider, model

    def generate(self, result_id: str) -> DemoSiteRead:
        result = self.session.get(AudienceResultModel, result_id)
        run = self.session.get(AudienceRunModel, result.run_id) if result else None
        if result is None or run is None or run.workspace_id != self.workspace_id:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        if run.state not in {AudienceRunState.READY.value, AudienceRunState.PARTIAL.value}:
            raise ValidationError("A completed audience result is required")
        existing = self.session.scalar(
            select(DemoSiteModel).where(
                DemoSiteModel.workspace_id == self.workspace_id,
                DemoSiteModel.audience_result_id == result.id,
                DemoSiteModel.prompt_version == 1,
            )
        )
        if existing is not None:
            return self._read(existing)
        business = self.session.get(BusinessModel, result.business_id)
        snapshot = result.match_snapshot or {}
        facts = {k: snapshot.get(k) for k in ("title", "geography", "snippet", "url", "phone") if snapshot.get(k)}
        facts["opportunity_evidence"] = ((snapshot.get("raw") or {}).get("profile_match") or {}).get("matched_signals", [])
        generated = self.llm.generate_object(
            task="demo_site_draft_v1",
            system="Create a concise local-business website concept using only supplied facts. Never invent awards, years, testimonials, prices, guarantees, credentials, or services. Return the required structure.",
            prompt="Draft an unofficial conversion-focused website concept and a short, respectful outreach note. Explicitly frame the note as a concept, not an existing client website.",
            response_model=DemoGeneration,
            context={"verified_business_facts": facts},
        )
        generated.site.business_name = str(snapshot.get("title") or business.display_name)
        row = DemoSiteModel(id=new_id("demo"), workspace_id=self.workspace_id, audience_result_id=result.id,
                            business_id=result.business_id, share_token=token_urlsafe(32), status="draft",
                            content={}, outreach_message="", provider=self.provider, model=self.model,
                            usage={}, prompt_version=1)
        self.session.add(row)
        row.content = generated.site.model_dump()
        row.outreach_message = generated.outreach_message
        row.provider, row.model = self.provider, self.model
        row.usage = dict(getattr(self.llm, "last_usage", {}) or {})
        row.status, row.published_at, row.expires_at = "draft", None, None
        self.session.commit(); self.session.refresh(row)
        return self._read(row)

    def get(self, demo_id: str) -> DemoSiteRead:
        return self._read(self._owned(demo_id))

    def update(self, demo_id: str, data: DemoSiteUpdate) -> DemoSiteRead:
        row = self._owned(demo_id)
        if data.content is not None: row.content = data.content.model_dump()
        if data.outreach_message is not None: row.outreach_message = data.outreach_message
        self.session.commit(); self.session.refresh(row)
        return self._read(row)

    def publish(self, demo_id: str) -> DemoSiteRead:
        row = self._owned(demo_id); now = utcnow()
        row.status, row.published_at, row.expires_at = "published", now, now + timedelta(days=30)
        self.session.commit(); self.session.refresh(row)
        return self._read(row)

    def public(self, token: str) -> DemoSiteRead:
        row = self.session.scalar(select(DemoSiteModel).where(DemoSiteModel.share_token == token, DemoSiteModel.status == "published"))
        if row is None or not row.expires_at or row.expires_at <= utcnow():
            raise NotFoundError("demo site not found")
        row.view_count += 1
        row.last_viewed_at = utcnow()
        self.session.commit(); self.session.refresh(row)
        return self._read(row)

    def _owned(self, demo_id: str) -> DemoSiteModel:
        row = self.session.get(DemoSiteModel, demo_id)
        if row is None or row.workspace_id != self.workspace_id: raise NotFoundError("demo site not found")
        return row

    @staticmethod
    def _read(row: DemoSiteModel) -> DemoSiteRead:
        return DemoSiteRead(id=row.id, status=row.status, share_token=row.share_token,
                            content=DemoSiteContent.model_validate(row.content), outreach_message=row.outreach_message,
                            usage=row.usage or {}, view_count=row.view_count,
                            last_viewed_at=row.last_viewed_at, published_at=row.published_at,
                            expires_at=row.expires_at)
