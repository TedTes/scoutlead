from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent_runs.repository import AgentRunRepository
from agents.llm import HeuristicLLMClient, LLMClient, MissingLLMClient
from agents.runner import ToolAction
from campaigns.repository import CampaignRepository
from campaigns.schemas import (
    CampaignCreate,
    CampaignPreflightCheck,
    CampaignPreflightRead,
    CampaignRead,
    CampaignRunSummary,
    CampaignStage,
    CampaignStatus,
)
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead
from db.models import CampaignModel
from evaluation.campaign_metrics import calculate_campaign_metrics
from evaluation.schemas import CampaignMetrics
from icp.service import ICPPresetService
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from memory.repository import MemoryRepository
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from products.repository import ProductRepository
from products.schemas import DiscoverySourceType, ProductRead
from shared.errors import ConflictError
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.search import SearchTool
from workflows.discovery import DiscoveryWorkflow
from workflows.contact import ContactWorkflow
from workflows.outreach import OutreachWorkflow
from workflows.qualification import QualificationWorkflow
from workflows.research import ResearchWorkflow
from workflows.signal import SignalWorkflow
from workflows.verify import VerifyWorkflow
from tools.base import ToolSlot


class RecordingBrowserTool:
    def __init__(
        self,
        *,
        browser: DirectHttpBrowserTool,
        agent_runs: AgentRunRepository,
        run_id: str,
        campaign_id: str,
        step_id: str | None,
    ) -> None:
        self.browser = browser
        self.agent_runs = agent_runs
        self.run_id = run_id
        self.campaign_id = campaign_id
        self.step_id = step_id

    def inspect(self, url: str):
        tool_call = self.agent_runs.start_tool_call(
            run_id=self.run_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            tool_name="browser:inspect",
            reason="inspect lead website for public evidence",
            args={"url": url},
        )
        try:
            result = self.browser.inspect(url)
        except Exception as exc:
            self.agent_runs.fail_tool_call(tool_call.id, str(exc))
            raise
        self.agent_runs.complete_tool_call(tool_call.id, CampaignService._json_safe(result))
        return result


class RecordingLLMClient:
    def __init__(
        self,
        *,
        llm: LLMClient,
        agent_runs: AgentRunRepository,
        run_id: str,
        campaign_id: str,
        step_id: str | None,
    ) -> None:
        self.llm = llm
        self.agent_runs = agent_runs
        self.run_id = run_id
        self.campaign_id = campaign_id
        self.step_id = step_id

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
        context: dict[str, Any] | None = None,
        fallback: BaseModel,
    ) -> BaseModel:
        llm_call = self.agent_runs.start_llm_call(
            run_id=self.run_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            task=task,
            reason=system,
            args={
                "task": task,
                "response_model": response_model.__name__,
                "context": CampaignService._json_safe(context or {}),
            },
        )
        try:
            result = self.llm.generate_object(
                task=task,
                system=system,
                prompt=prompt,
                response_model=response_model,
                context=context,
                fallback=fallback,
            )
        except Exception as exc:
            self.agent_runs.fail_tool_call(llm_call.id, str(exc))
            raise
        self.agent_runs.complete_tool_call(llm_call.id, CampaignService._json_safe(result))
        return result


class CampaignService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        search_tool: SearchTool,
        browser: DirectHttpBrowserTool,
        email: EmailTool | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.search_tool = search_tool
        self.browser = browser
        self.email = email or EmailTool()
        self.products = ProductRepository(session)
        self.campaigns = CampaignRepository(session)
        self.agent_runs = AgentRunRepository(session)
        self.icp_presets = ICPPresetService()
        self.leads = LeadRepository(session)
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)
        self.memory = MemoryRepository(session)

    def create(self, campaign: CampaignCreate) -> CampaignModel:
        self.products.get(campaign.product_id)
        return self.campaigns.create(campaign)

    def list(self) -> list[CampaignModel]:
        return self.campaigns.list()

    def get(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.get(campaign_id)

    def delete(self, campaign_id: str) -> None:
        self.campaigns.delete(campaign_id)

    def preflight(self, campaign_id: str) -> CampaignPreflightRead:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        checks = self._preflight_checks(campaign, product)
        return CampaignPreflightRead(
            campaign_id=campaign_id,
            ready=all(check.status != "failed" for check in checks if check.required),
            checks=checks,
        )

    def pause(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.update_status(campaign_id, CampaignStatus.PAUSED)

    def resume(self, campaign_id: str) -> CampaignModel:
        campaign = self.campaigns.get(campaign_id)
        stage_to_status = {
            CampaignStage.DISCOVERY.value: CampaignStatus.DISCOVERING,
            CampaignStage.RESEARCH.value: CampaignStatus.RESEARCHING,
            CampaignStage.QUALIFICATION.value: CampaignStatus.QUALIFYING,
            CampaignStage.OUTREACH.value: CampaignStatus.AWAITING_APPROVAL,
            CampaignStage.RESPONSE.value: CampaignStatus.TRACKING,
            CampaignStage.COMPLETE.value: CampaignStatus.COMPLETED,
        }
        return self.campaigns.update_status(
            campaign_id, stage_to_status.get(campaign.stage, CampaignStatus.TRACKING)
        )

    def run_campaign(self, campaign_id: str, *, agent_run_id: str | None = None) -> CampaignRunSummary:
        campaign = self.campaigns.get(campaign_id)
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        campaign_read = CampaignRead.model_validate(campaign)
        preset = self.icp_presets.get(campaign_read.icp_preset_id)

        try:
            self._assert_runnable_campaign(campaign_read)
            self._assert_preflight_ready(campaign_read, product)
            if agent_run_id:
                self.agent_runs.start(agent_run_id)

            discovered = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.DISCOVERY.value,
                sequence=1,
                objective="Discover potential customers that match the product ICP.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda step_id: DiscoveryWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    search_tool=self.search_tool,
                    **self._tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            researched = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.RESEARCH.value,
                sequence=2,
                objective="Research discovered leads with available public information.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: ResearchWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    browser=self._browser_for_step(agent_run_id, campaign_id, _step_id),
                    llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            contacted = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.CONTACT.value,
                sequence=3,
                objective="Find the first good reachable contact point for each researched lead.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: ContactWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.CONTACT),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            verified = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.VERIFY.value,
                sequence=4,
                objective="Verify contact points before qualification and outreach drafting.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: VerifyWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.VERIFY),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            signaled = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.SIGNAL.value,
                sequence=5,
                objective="Accumulate public signals used by qualification and campaign insights.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: SignalWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.SIGNAL),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            qualified = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.QUALIFICATION.value,
                sequence=6,
                objective="Score researched leads against the product qualification criteria.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: QualificationWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            drafts = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.OUTREACH.value,
                sequence=7,
                objective="Draft personalized outreach and queue messages for human approval.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: OutreachWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    messages=self.messages,
                    memory=self.memory,
                    llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                ).run(product, campaign_read),
            )

            summary = CampaignRunSummary(
                campaign=CampaignRead.model_validate(self.campaigns.get(campaign_id)),
                discovered_lead_count=len(discovered),
                researched_lead_count=len(researched),
                contacted_lead_count=len(contacted),
                verified_lead_count=len(verified),
                signaled_lead_count=len(signaled),
                qualified_lead_count=sum(
                    1
                    for lead in qualified
                    if lead.qualification and lead.qualification.qualified
                ),
                drafted_message_count=len(drafts),
            )
            if agent_run_id:
                self.agent_runs.complete(agent_run_id, summary.model_dump(mode="json"))
            return summary
        except Exception as exc:
            if agent_run_id:
                self.agent_runs.fail(agent_run_id, str(exc))
            raise

    def metrics(self, campaign_id: str) -> CampaignMetrics:
        leads = [
            LeadRead.model_validate(model)
            for model in self.leads.list_by_campaign(campaign_id)
        ]
        messages = [
            MessageRead.model_validate(model)
            for model in self.messages.list_by_campaign(campaign_id)
        ]
        conversations = [
            ConversationRead.model_validate(model)
            for model in self.conversations.list_by_campaign(campaign_id)
        ]
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        return calculate_campaign_metrics(
            leads=leads,
            messages=messages,
            conversations=conversations,
            goal_type=campaign.goal_type,
        )

    def _assert_preflight_ready(self, campaign: CampaignRead, product: ProductRead) -> None:
        preflight = CampaignPreflightRead(
            campaign_id=campaign.id,
            ready=True,
            checks=self._preflight_checks(campaign, product),
        )
        failures = [check for check in preflight.checks if check.required and check.status == "failed"]
        if failures:
            raise ConflictError(
                "campaign cannot run until required integrations are configured",
                {"failures": [failure.model_dump(mode="json") for failure in failures]},
            )

    def _preflight_checks(
        self, campaign: CampaignRead, product: ProductRead
    ) -> list[CampaignPreflightCheck]:
        sources = product.preferred_discovery_sources
        has_seed_source = any(source.type == DiscoverySourceType.SEED for source in sources)
        has_live_source = any(source.type != DiscoverySourceType.SEED for source in sources)
        checks = [
            CampaignPreflightCheck(
                name="Campaign status",
                status="ok" if campaign.status in {CampaignStatus.DRAFT, CampaignStatus.PAUSED} else "failed",
                detail=f"Campaign is {campaign.status.value}.",
            )
        ]

        if has_live_source:
            missing_search_is_required = self.search_tool.require_config
            checks.append(
                CampaignPreflightCheck(
                    name="Search provider",
                    status=(
                        "ok"
                        if self.search_tool.is_configured
                        else "failed"
                        if missing_search_is_required
                        else "warning"
                    ),
                    detail=(
                        f"{self.search_tool.provider} search configured"
                        if self.search_tool.is_configured
                        else "Configure SEARCH_PROVIDER plus SEARCH_API_KEY or SEARCH_API_ENDPOINT."
                    ),
                    required=missing_search_is_required,
                )
            )
        else:
            checks.append(
                CampaignPreflightCheck(
                    name="Search provider",
                    status="warning" if has_seed_source else "failed",
                    detail=(
                        "Using seed discovery only; no live search will run."
                        if has_seed_source
                        else "No discovery sources configured."
                    ),
                    required=not has_seed_source,
                )
            )

        if isinstance(self.llm, MissingLLMClient):
            llm_status = "failed"
            llm_detail = "Configure OPENAI_API_KEY or LLM_JSON_ENDPOINT."
        elif isinstance(self.llm, HeuristicLLMClient):
            llm_status = "warning"
            llm_detail = "Using heuristic fallback; configure a real LLM for production-quality reasoning."
        else:
            llm_status = "ok"
            llm_detail = self.llm.__class__.__name__
        checks.append(CampaignPreflightCheck(name="LLM provider", status=llm_status, detail=llm_detail))

        checks.append(
            CampaignPreflightCheck(
                name="Email provider",
                status="ok" if self.messages_can_send_real_email() else "failed",
                detail=(
                    f"{self.email.provider} email provider ready"
                    if self.messages_can_send_real_email()
                    else "Configure EMAIL_PROVIDER=resend with RESEND_API_KEY and EMAIL_FROM_ADDRESS."
                ),
            )
        )

        checks.append(
            CampaignPreflightCheck(
                name="Website inspection",
                status="ok",
                detail="Direct HTTP website inspection is enabled.",
                required=False,
            )
        )
        return checks

    def messages_can_send_real_email(self) -> bool:
        return self.email.is_configured

    @staticmethod
    def _assert_runnable_campaign(campaign: CampaignRead) -> None:
        if campaign.status not in {CampaignStatus.DRAFT, CampaignStatus.PAUSED}:
            raise ConflictError(
                "campaign can only be run from draft or paused status",
                {"campaign_id": campaign.id, "status": campaign.status.value},
            )

    def _run_agent_step(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        phase: str,
        sequence: int,
        objective: str,
        input_snapshot: dict[str, Any],
        action: Callable[[str | None], Any],
    ) -> Any:
        if not agent_run_id:
            return action(None)

        step = self.agent_runs.start_step(
            run_id=agent_run_id,
            campaign_id=campaign_id,
            phase=phase,
            sequence=sequence,
            objective=objective,
            input_snapshot=input_snapshot,
        )
        try:
            result = action(step.id)
        except Exception as exc:
            self.agent_runs.fail_step(step.id, str(exc))
            raise

        output_snapshot = self._result_snapshot(result)
        self.agent_runs.complete_step(
            step.id,
            output_snapshot=output_snapshot,
            observation={
                "phase": phase,
                "completed": True,
                **output_snapshot,
            },
        )
        return result

    @staticmethod
    def _campaign_step_input(product: ProductRead, campaign: CampaignRead) -> dict[str, Any]:
        return {
            "product_id": product.id,
            "product_name": product.product_name,
            "campaign_id": campaign.id,
            "campaign_status": campaign.status.value,
            "campaign_stage": campaign.stage.value,
            "goal_type": campaign.goal_type.value,
            "icp_preset_id": campaign.icp_preset_id,
            "max_leads": campaign.max_leads,
        }

    @staticmethod
    def _result_snapshot(result: Any) -> dict[str, Any]:
        if isinstance(result, list):
            ids = [getattr(row, "id", None) for row in result]
            return {
                "count": len(result),
                "ids": [row_id for row_id in ids if row_id is not None][:50],
            }
        return {"result": CampaignService._json_safe(result)}

    def _tool_call_callbacks(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> dict[str, Callable[..., Any] | None]:
        if agent_run_id is None:
            return {
                "on_tool_start": None,
                "on_tool_success": None,
                "on_tool_error": None,
            }

        def on_tool_start(action: ToolAction, iteration: int) -> str:
            tool_call = self.agent_runs.start_tool_call(
                run_id=agent_run_id,
                campaign_id=campaign_id,
                step_id=step_id,
                tool_name=action.tool_name,
                reason=action.reason,
                args={"iteration": iteration, **self._json_safe(action.args)},
            )
            return tool_call.id

        def on_tool_success(tool_call_id: str, observation: Any) -> None:
            self.agent_runs.complete_tool_call(tool_call_id, self._json_safe(observation))

        def on_tool_error(tool_call_id: str, error: Exception) -> None:
            self.agent_runs.fail_tool_call(tool_call_id, str(error))

        return {
            "on_tool_start": on_tool_start,
            "on_tool_success": on_tool_success,
            "on_tool_error": on_tool_error,
        }

    def _slot_tool_call_callbacks(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> dict[str, Callable[..., Any] | None]:
        if agent_run_id is None:
            return {
                "on_tool_start": None,
                "on_tool_success": None,
                "on_tool_error": None,
            }

        def on_tool_start(tool_name: str, args: dict[str, Any], reason: str) -> str:
            tool_call = self.agent_runs.start_tool_call(
                run_id=agent_run_id,
                campaign_id=campaign_id,
                step_id=step_id,
                tool_name=tool_name,
                reason=reason,
                args=self._json_safe(args),
            )
            return tool_call.id

        def on_tool_success(tool_call_id: str, observation: Any) -> None:
            self.agent_runs.complete_tool_call(tool_call_id, self._json_safe(observation))

        def on_tool_error(tool_call_id: str, error: Exception) -> None:
            self.agent_runs.fail_tool_call(tool_call_id, str(error))

        return {
            "on_tool_start": on_tool_start,
            "on_tool_success": on_tool_success,
            "on_tool_error": on_tool_error,
        }

    def _llm_for_step(
        self,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> LLMClient:
        if agent_run_id is None:
            return self.llm
        return RecordingLLMClient(
            llm=self.llm,
            agent_runs=self.agent_runs,
            run_id=agent_run_id,
            campaign_id=campaign_id,
            step_id=step_id,
        )

    def _browser_for_step(
        self,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> DirectHttpBrowserTool:
        if agent_run_id is None:
            return self.browser
        return RecordingBrowserTool(
            browser=self.browser,
            agent_runs=self.agent_runs,
            run_id=agent_run_id,
            campaign_id=campaign_id,
            step_id=step_id,
        )

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [CampaignService._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [CampaignService._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): CampaignService._json_safe(item) for key, item in value.items()}
        if value is None or isinstance(value, str | int | float | bool):
            return value
        return str(value)
