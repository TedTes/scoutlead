from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, RelevantMemory
from products.schemas import ProductRead
from shared.utils import keyword_hits


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def record(self, observation: CampaignMemoryCreate):
        return self.repository.create_observation(observation)

    def relevant_for_product(self, product: ProductRead, exclude_campaign_id: str | None = None) -> RelevantMemory:
        keywords = [
            product.product_name,
            product.target_customer,
            product.target_geography,
            *[criterion.label for criterion in product.qualification_criteria],
        ]
        observations = [
            observation
            for observation in self.repository.list_observations(product.id)
            if observation.campaign_id != exclude_campaign_id
            or keyword_hits(observation.content, keywords)
        ][:20]
        summaries = self.repository.list_summaries(product.id)[:10]
        return RelevantMemory.model_validate({"observations": observations, "summaries": summaries})
