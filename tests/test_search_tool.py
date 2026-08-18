from tools.search import SearchResult, SearchTool


def test_search_filter_excludes_content_pages_and_keeps_business_sites() -> None:
    rows = [
        SearchResult(
            title="Why Customers Stop Responding After You Send a Quote",
            url="https://www.youtube.com/watch?v=abc",
            snippet="Video",
        ),
        SearchResult(
            title="Configure Quotes Faster: 6 Strategies",
            url="https://www.cincom.com/blog/cpq/configure-quotes-faster",
            snippet="Blog",
        ),
        SearchResult(
            title="Fernwood Painting",
            url="https://fernwoodpainting.example",
            snippet="Residential painting company",
        ),
    ]

    filtered = SearchTool._filter_business_results(rows, 10)

    assert [row.title for row in filtered] == ["Fernwood Painting"]
