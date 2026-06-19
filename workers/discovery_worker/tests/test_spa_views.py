"""Tests for SPA virtual view expansion."""

from aqa_discovery.spa_views import expand_spa_views, is_virtual_view_url, virtual_view_url
from aqa_discovery.types import ElementSnapshot, InteractionAction, PageSnapshot, UIStateSnapshot


def test_expand_spa_views_creates_virtual_pages_for_cic_states() -> None:
    baseline = UIStateSnapshot(
        state_key="s_base",
        url="https://example.com/",
        title="App",
        interaction_depth=0,
        elements=[ElementSnapshot(tag_name="button", text_content="Home")],
    )
    manufacturers = UIStateSnapshot(
        state_key="s_mfr",
        parent_state_key="s_base",
        url="https://example.com/",
        title="App",
        interaction_depth=1,
        trigger_interaction=InteractionAction(
            action_type="click",
            interaction_key="mfr",
            text_content="Manufacturers",
        ),
        elements=[ElementSnapshot(tag_name="table", text_content="Rows")],
    )
    snapshot = PageSnapshot(
        url="https://example.com/",
        title="App",
        status=200,
        html_length=1000,
        states=[baseline, manufacturers],
    )

    expanded = expand_spa_views(snapshot)

    assert len(expanded) == 2
    assert expanded[0].url == "https://example.com/"
    assert expanded[1].url == virtual_view_url("https://example.com/", "s_mfr")
    assert expanded[1].title == "Manufacturers — App"
    assert len(expanded[1].elements) == 1
    assert is_virtual_view_url(expanded[1].url)


def test_expand_spa_views_without_states_is_noop() -> None:
    snapshot = PageSnapshot(url="https://example.com/", title="App", status=200, html_length=10)
    assert expand_spa_views(snapshot) == [snapshot]
