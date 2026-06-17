"""Rule-based flow structuring from crawled pages (Day 20, SPEC §17.1)."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse


def _module_key(url: str) -> str:
    """Extract the first path segment after index.php (OrangeHRM/PHP apps) or first segment."""
    path = urlparse(url).path
    parts = [part for part in path.split("/") if part]
    if "index.php" in parts:
        index = parts.index("index.php")
        if index + 1 < len(parts):
            return parts[index + 1].lower()
    if len(parts) >= 2:
        return parts[-2].lower()
    if parts:
        return parts[-1].lower()
    return "root"


def _flow_name(module: str) -> str:
    label = module.replace("-", " ").replace("_", " ").strip() or "root"
    return f"{label.title()} flow"


def build_flows_from_pages(pages: list[dict]) -> list[dict]:
    """Group pages by URL module segment and emit flow dicts for persistence."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        url = page.get("url") or ""
        grouped[_module_key(url)].append(page)

    flows: list[dict] = []
    for module in sorted(grouped.keys()):
        module_pages = sorted(grouped[module], key=lambda item: item.get("url") or "")
        steps = [
            {
                "action": "navigate",
                "page_id": page.get("page_id"),
                "url": page.get("url"),
                "title": page.get("title"),
            }
            for page in module_pages
        ]
        flows.append(
            {
                "name": _flow_name(module),
                "description": f"Rule-based flow for /{module}/ pages ({len(steps)} steps)",
                "steps": steps,
                "source": "crawler",
                "module": module,
            }
        )
    return flows
