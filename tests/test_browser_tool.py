from tools.browser import DirectHttpBrowserTool


def test_direct_http_browser_merges_same_domain_evidence_pages(monkeypatch) -> None:
    pages = {
        "https://paint.example/": """
            <html>
              <head><title>Paint Example</title></head>
              <body>
                <p>Residential painting in Toronto.</p>
                <a href="/contact">Contact</a>
                <a href="/free-estimate">Free estimate</a>
                <a href="https://directory.example/contact">Directory contact</a>
              </body>
            </html>
        """,
        "https://paint.example/contact": """
            <html>
              <head><title>Contact Paint Example</title></head>
              <body>Email owner@paint.example for booking.</body>
            </html>
        """,
        "https://paint.example/free-estimate": """
            <html>
              <head><title>Request an Estimate</title></head>
              <body>Request a quote form for house painting projects.</body>
            </html>
        """,
    }
    calls: list[str] = []

    class Response:
        def __init__(self, url: str, text: str) -> None:
            self.url = url
            self.text = text

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **kwargs) -> Response:
        calls.append(url)
        return Response(url, pages[url])

    monkeypatch.setattr("tools.browser.httpx.get", fake_get)

    result = DirectHttpBrowserTool(timeout_seconds=0.1).inspect("https://paint.example/")

    assert calls == [
        "https://paint.example/",
        "https://paint.example/contact",
        "https://paint.example/free-estimate",
    ]
    assert result.emails == ["owner@paint.example"]
    assert "Residential painting in Toronto" in result.text
    assert "Request a quote form" in result.text
    assert "https://directory.example/contact" not in calls
