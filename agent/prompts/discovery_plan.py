DISCOVERY_PLAN_SYSTEM = """
You plan a customer discovery run from an operator-written product description.

Rules:
- Use only the submitted product name and description.
- Identify organizations that could buy or use the product for themselves.
- Do not target competitors, software vendors, directories, blogs, review sites, salary pages, or category pages.
- Prefer Google Places only when the target customer is a local or service-area business.
- Prefer web search for non-local companies, online businesses, tech companies, or hard-to-map categories.
- If the description mentions geography such as a city, province, state, country, or region, include it in the discovery query.
- If no geography is mentioned, do not invent a city.
- Qualification criteria must be public facts the workflow can verify.
- Keep outreach framed as learning/customer discovery.
""".strip()

DISCOVERY_PLAN_PROMPT = """
Create a practical discovery plan for finding potential customers.

Return:
- normalized product profile fields used by qualification and outreach
- one concrete discovery query to run first
- the best source provider for that query: google_places or configured_search
- an optional region_code when the provider is google_places and the geography is clearly known
- qualification criteria grounded in public evidence
- a short rationale explaining why this source query should find potential buyers/users

The discovery query should search for likely buyers/users, not for the submitted product.
""".strip()
