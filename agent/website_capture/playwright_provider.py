from __future__ import annotations

import ipaddress
import socket
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from website_capture.contracts import ViewportCapture, WebsiteCaptureResult


VIEWPORTS = (
    ("desktop", 1440, 1000),
    ("mobile", 390, 844),
)


class PlaywrightBrowserCapture:
    key = "playwright"

    def __init__(
        self,
        *,
        timeout_seconds: float = 25.0,
        max_screenshot_height: int = 8000,
    ) -> None:
        self.timeout_ms = max(1, round(timeout_seconds * 1000))
        self.max_screenshot_height = max(844, max_screenshot_height)

    def capture(self, url: str) -> WebsiteCaptureResult:
        _require_public_http_url(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Website capture requires the optional Playwright dependency. "
                "Install with `pip install -e '.[website-capture]'` and run "
                "`playwright install chromium`."
            ) from exc

        captures: list[ViewportCapture] = []
        final_url = url
        title: str | None = None
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for name, width, height in VIEWPORTS:
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=1,
                        ignore_https_errors=True,
                        java_script_enabled=True,
                    )
                    try:
                        context.route("**/*", _safe_route)
                        page = context.new_page()
                        response = page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=self.timeout_ms,
                        )
                        try:
                            page.wait_for_load_state("networkidle", timeout=min(5000, self.timeout_ms))
                        except Exception:
                            pass
                        final_url = page.url
                        _require_public_http_url(final_url)
                        title = title or page.title().strip() or None
                        metrics = _page_metrics(page)
                        metrics["status_code"] = response.status if response else None
                        screenshot = page.screenshot(
                            full_page=bool(metrics["document_height"] <= self.max_screenshot_height),
                            type="png",
                        )
                        captures.append(
                            ViewportCapture(
                                name=name,
                                width=width,
                                height=height,
                                screenshot=screenshot,
                                metrics=metrics,
                            )
                        )
                    finally:
                        context.close()
            finally:
                browser.close()
        return WebsiteCaptureResult(
            requested_url=url,
            final_url=final_url,
            captured_at=datetime.now(timezone.utc).isoformat(),
            title=title,
            viewports=captures,
            page_metrics=_aggregate_metrics(captures),
        )


def _page_metrics(page) -> dict[str, float | int | bool | str | None]:
    return dict(
        page.evaluate(
            """
            () => {
              const root = document.documentElement;
              const body = document.body;
              const interactive = Array.from(document.querySelectorAll(
                'a[href], button, input, select, textarea, [role="button"]'
              ));
              const visible = interactive.filter((element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.visibility !== 'hidden' && style.display !== 'none' &&
                  rect.width > 0 && rect.height > 0;
              });
              const smallTargets = visible.filter((element) => {
                const rect = element.getBoundingClientRect();
                return rect.width < 44 || rect.height < 44;
              });
              const images = Array.from(document.images);
              const brokenImages = images.filter((image) => image.complete && image.naturalWidth === 0);
              const text = (body?.innerText || '').replace(/\\s+/g, ' ').trim();
              const documentWidth = Math.max(root?.scrollWidth || 0, body?.scrollWidth || 0);
              const documentHeight = Math.max(root?.scrollHeight || 0, body?.scrollHeight || 0);
              return {
                document_width: documentWidth,
                document_height: documentHeight,
                horizontal_overflow_px: Math.max(0, documentWidth - window.innerWidth),
                word_count: text ? text.split(' ').length : 0,
                heading_count: document.querySelectorAll('h1, h2, h3').length,
                h1_count: document.querySelectorAll('h1').length,
                nav_count: document.querySelectorAll('nav').length,
                interactive_count: visible.length,
                small_tap_target_ratio: visible.length ? smallTargets.length / visible.length : 0,
                image_count: images.length,
                broken_image_count: brokenImages.length,
                has_viewport_meta: Boolean(document.querySelector('meta[name="viewport"]')),
                has_title: Boolean(document.title?.trim()),
                has_meta_description: Boolean(document.querySelector('meta[name="description"]')),
              };
            }
            """
        )
    )


def _aggregate_metrics(
    captures: list[ViewportCapture],
) -> dict[str, float | int | bool | str | None]:
    by_name = {capture.name: capture.metrics for capture in captures}
    mobile = by_name.get("mobile", {})
    desktop = by_name.get("desktop", {})
    return {
        "desktop_status_code": desktop.get("status_code"),
        "mobile_status_code": mobile.get("status_code"),
        "mobile_horizontal_overflow_px": mobile.get("horizontal_overflow_px"),
        "mobile_small_tap_target_ratio": mobile.get("small_tap_target_ratio"),
        "mobile_viewport_present": mobile.get("has_viewport_meta"),
        "heading_count": desktop.get("heading_count"),
        "word_count": desktop.get("word_count"),
        "broken_image_count": desktop.get("broken_image_count"),
    }


def _safe_route(route, request) -> None:
    try:
        _require_public_http_url(request.url)
    except ValueError:
        route.abort("blockedbyclient")
        return
    route.continue_()


def _require_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("website capture only supports public HTTP(S) URLs")
    if parsed.username or parsed.password:
        raise ValueError("website capture does not allow URL credentials")
    addresses = _resolved_addresses(parsed.hostname)
    if not addresses:
        raise ValueError("website hostname could not be resolved")
    if any(not address.is_global for address in addresses):
        raise ValueError("website capture blocks local and private network addresses")


@lru_cache(maxsize=1024)
def _resolved_addresses(hostname: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return ()
    values = {
        ipaddress.ip_address(record[4][0].split("%", 1)[0])
        for record in records
    }
    return tuple(sorted(values, key=str))
