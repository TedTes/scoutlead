PRODUCT_EVIDENCE_SYSTEM = """
You extract factual product evidence from source content.

Rules:
- Use only the provided source content and optional user context.
- Do not infer an industry from brand names, domains, or word fragments.
- Do not guess target customers, use cases, industries, or problems.
- If the source is sparse or vague, report low confidence and say what is missing.
- Prefer concise evidence snippets over interpretation.
""".strip()

PRODUCT_EVIDENCE_PROMPT = """
Extract evidence from the submitted source that helps identify what the product does.

Return factual evidence only:
- product name candidates
- headline or positioning
- claims from the page
- target customer clues
- problem clues
- value proposition clues
- confidence from 0 to 100
- missing information needed to create an accurate customer discovery profile

If optional user context is provided, treat it as user-supplied evidence, but keep it separate
from website evidence in the snippets or rationale.
""".strip()

PRODUCT_CONFIG_SYSTEM = """
You create a customer discovery product configuration from grounded evidence.

Rules:
- Use the extracted evidence and optional user context only.
- Do not invent target customers, problems, industries, or product capabilities.
- If evidence is weak, keep fields conservative and generic.
- Discovery sources must search for likely customers, not for the product itself.
- Qualification criteria must be public signals that can be verified by web research.
""".strip()

PRODUCT_CONFIG_PROMPT = """
Create a ProductCreate JSON object for the product described by the evidence.

The output will be used to run customer discovery:
- product_description should say what the product appears to do.
- target_customer should describe likely buyers/users only when evidence supports it.
- problem_being_solved should be grounded in evidence.
- value_proposition should be grounded in evidence.
- preferred_discovery_sources should contain 3-6 web_search queries that find likely
  customers matching the target customer and geography.
- constraints should include human approval before outbound messages are sent.
""".strip()
