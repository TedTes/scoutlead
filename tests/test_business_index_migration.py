from types import SimpleNamespace

from scripts.migrate_business_index import IdentityIndex, _is_corrupt_identity_cluster


def business(**overrides):
    values = {
        "id": "business_source",
        "display_name": "Example Painting",
        "website_url": "https://examplepainting.ca",
        "domain": "examplepainting.ca",
        "phone": "416-555-0100",
        "market_key": "toronto",
    }
    values.update(overrides)
    return values


def record(**overrides):
    values = {
        "business": business(),
        "observations": [
            {
                "source": "google_places_seed",
                "external_id": "place-1",
            }
        ],
    }
    values.update(overrides)
    return values


def test_identity_index_matches_external_identity():
    index = IdentityIndex()
    index.add_business("business_target", business(), record()["observations"])

    assert index.resolve(record()) == ("matched", "business_target")


def test_identity_index_rejects_conflicting_strong_identifiers():
    index = IdentityIndex()
    index.add_business(
        "business_by_phone",
        business(domain=None, website_url=None),
        [],
    )
    index.add_business(
        "business_by_external",
        business(phone=None, domain="other.ca", website_url="https://other.ca"),
        record()["observations"],
    )

    assert index.resolve(record()) == ("conflict", None)


def test_identity_index_ignores_shared_social_domains():
    index = IdentityIndex()
    index.add_business(
        "first",
        business(
            display_name="First Electric",
            domain="facebook.com",
            website_url="https://facebook.com/first",
            phone=None,
        ),
        [],
    )

    disposition, target = index.resolve(
        record(
            business=business(
                display_name="Second Electric",
                domain="facebook.com",
                website_url="https://facebook.com/second",
                phone=None,
            ),
            observations=[],
        )
    )

    assert disposition == "new"
    assert target is None


def test_excessive_provider_identities_are_rejected_as_corrupt_cluster():
    observations = [
        SimpleNamespace(source="google_places_seed", external_id=f"place-{index}")
        for index in range(11)
    ]

    assert _is_corrupt_identity_cluster(observations) is True
    assert _is_corrupt_identity_cluster(observations[:10]) is False
