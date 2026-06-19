"""Synthetic page URLs for same-URL SPA views discovered via CIC."""

from __future__ import annotations

from aqa_discovery.types import PageSnapshot, UIStateSnapshot

VIRTUAL_VIEW_MARKER = "#__aqa_view__"


def is_virtual_view_url(url: str) -> bool:
    return VIRTUAL_VIEW_MARKER in (url or "")


def virtual_view_url(base_url: str, state_key: str) -> str:
    return f"{base_url.rstrip('/')}{VIRTUAL_VIEW_MARKER}/{state_key}"


def _view_label(state: UIStateSnapshot) -> str:
    trigger = state.trigger_interaction
    if trigger and trigger.text_content and trigger.text_content.strip():
        return trigger.text_content.strip()
    if state.title and state.title.strip():
        return state.title.strip()
    return state.state_key


def expand_spa_views(snapshot: PageSnapshot) -> list[PageSnapshot]:
    """Emit virtual page snapshots for CIC states beyond the baseline (same URL SPAs)."""
    if not snapshot.states:
        return [snapshot]

    baseline_keys = {state.state_key for state in snapshot.states if state.interaction_depth == 0}
    if not baseline_keys:
        return [snapshot]

    expanded: list[PageSnapshot] = [snapshot]
    seen: set[str] = set()

    for state in sorted(snapshot.states, key=lambda item: (item.interaction_depth, item.state_key)):
        if state.interaction_depth < 1:
            continue
        if state.state_key in seen:
            continue
        seen.add(state.state_key)

        label = _view_label(state)
        base_title = snapshot.title or snapshot.url
        expanded.append(
            PageSnapshot(
                url=virtual_view_url(snapshot.url, state.state_key),
                title=f"{label} — {base_title}"[:512],
                status=snapshot.status,
                html_length=state.html_length or snapshot.html_length,
                depth=snapshot.depth + 1,
                elements=list(state.elements),
                screenshot_path=state.screenshot_path or snapshot.screenshot_path,
                states=[state],
                transitions=[],
                discovered_urls=[],
            )
        )

    return expanded
