from __future__ import annotations

from typing import Any

from campaign_sources.schemas import CampaignSourceCreate, CampaignSourceSlot
from campaigns.schemas import CampaignCreate
from products.schemas import DiscoverySourceType, ProductRead
from source_presets.repository import SourcePresetRepository
from source_presets.schemas import SourcePreset


class SourcePresetService:
    def __init__(self, repository: SourcePresetRepository | None = None) -> None:
        self.repository = repository or SourcePresetRepository()

    def list(self) -> list[SourcePreset]:
        return self.repository.list()

    def get(self, preset_id: str | None) -> SourcePreset:
        return self.repository.get(preset_id)

    def expand_for_campaign(
        self,
        *,
        campaign_id: str,
        campaign: CampaignCreate,
        product: ProductRead,
    ) -> list[CampaignSourceCreate]:
        preset = self.get(campaign.source_preset_id)
        discovery_inputs = self._discovery_inputs(campaign=campaign, product=product)
        rows: list[CampaignSourceCreate] = []
        for template in preset.sources:
            if template.slot == CampaignSourceSlot.DISCOVERY:
                for index, source_input in enumerate(discovery_inputs):
                    provider_id = (
                        "seed"
                        if source_input.get("source_type") == DiscoverySourceType.SEED.value
                        else template.provider_id
                    )
                    rows.append(
                        CampaignSourceCreate(
                            campaign_id=campaign_id,
                            slot=template.slot,
                            provider_id=provider_id,
                            mode=template.mode,
                            input=self._render_payload(template.input, source_input),
                            config=self._render_payload(template.config, source_input),
                            priority=template.priority + index,
                            enabled=template.enabled,
                            budget_limit=template.budget_limit,
                        )
                    )
                continue

            rows.append(
                CampaignSourceCreate(
                    campaign_id=campaign_id,
                    slot=template.slot,
                    provider_id=template.provider_id,
                    mode=template.mode,
                    input=self._render_payload(template.input, campaign.source_inputs),
                    config=self._render_payload(template.config, campaign.source_inputs),
                    priority=template.priority,
                    enabled=template.enabled,
                    budget_limit=template.budget_limit,
                )
            )
        return rows

    @staticmethod
    def _discovery_inputs(*, campaign: CampaignCreate, product: ProductRead) -> list[dict[str, Any]]:
        explicit_query = (campaign.source_input or "").strip()
        if explicit_query:
            return [
                {
                    "query": explicit_query,
                    "source_type": DiscoverySourceType.WEB_SEARCH.value,
                    "limit": campaign.max_leads,
                    "geography": product.target_geography,
                }
            ]

        inputs = []
        for source in product.preferred_discovery_sources:
            inputs.append(
                {
                    "query": source.value,
                    "source_type": source.type.value,
                    "limit": source.limit or campaign.max_leads,
                    "geography": product.target_geography,
                    "notes": source.notes,
                }
            )
        return inputs

    @staticmethod
    def _render_payload(template: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        rendered: dict[str, Any] = {}
        for key, value in template.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                rendered[key] = values.get(value[2:-2].strip())
            else:
                rendered[key] = value
        return rendered
