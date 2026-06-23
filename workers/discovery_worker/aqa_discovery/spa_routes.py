"""SPA route capture during crawl (DISCOVERY-AGENT-VISION-SPEC §8.8)."""

from __future__ import annotations

from typing import Any

from aqa_discovery.types import SpaRouteEvent

_SPA_LISTENER_SCRIPT = """
(() => {
  if (window.__aqa_spa_listener_installed) return;
  window.__aqa_spa_listener_installed = true;
  window.__aqa_spa_routes__ = window.__aqa_spa_routes__ || [];
  const record = (fromUrl, toUrl, method) => {
    window.__aqa_spa_routes__.push({
      from_url: fromUrl || '',
      to_url: toUrl || '',
      title: document.title || '',
      timestamp_ms: Date.now(),
      discovery_method: method,
    });
  };
  const wrapHistory = (original, method) => function(...args) {
    const fromUrl = location.href;
    const result = original.apply(this, args);
    record(fromUrl, location.href, method);
    return result;
  };
  if (history.pushState) {
    history.pushState = wrapHistory(history.pushState.bind(history), 'pushstate_listener');
  }
  if (history.replaceState) {
    history.replaceState = wrapHistory(history.replaceState.bind(history), 'replacestate_listener');
  }
  window.addEventListener('popstate', () => {
    record('', location.href, 'popstate_listener');
  });
  window.addEventListener('hashchange', () => {
    record('', location.href, 'hash_route');
  });
})();
"""


def install_spa_route_listener(page) -> None:
    """Inject pushState/popstate/hash listeners before navigation side-effects."""
    page.add_init_script(_SPA_LISTENER_SCRIPT)


def collect_spa_route_events(page, *, source_page_url: str) -> list[SpaRouteEvent]:
    """Read captured SPA navigations from the page context."""
    raw: list[dict[str, Any]] = page.evaluate(
        """() => (window.__aqa_spa_routes__ || []).slice()"""
    )
    events: list[SpaRouteEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        to_url = str(item.get("to_url") or "").strip()
        if not to_url:
            continue
        method = str(item.get("discovery_method") or "pushstate_listener")
        from_url = str(item.get("from_url") or "").strip()
        key = (from_url, to_url, method)
        if key in seen:
            continue
        seen.add(key)
        events.append(
            SpaRouteEvent(
                from_url=from_url,
                to_url=to_url,
                title=str(item.get("title") or ""),
                timestamp_ms=float(item.get("timestamp_ms") or 0),
                discovery_method=method,
                source_page_url=source_page_url,
            )
        )
    return events


def aggregate_spa_route_events(pages) -> list[SpaRouteEvent]:
    """Merge per-page SPA events from a crawl result."""
    merged: list[SpaRouteEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for page in pages:
        for event in getattr(page, "spa_route_events", []) or []:
            key = (event.from_url, event.to_url, event.discovery_method)
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    return merged
