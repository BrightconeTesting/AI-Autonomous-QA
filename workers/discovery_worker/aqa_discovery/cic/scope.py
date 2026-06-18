"""CIC interaction scope — main page or same-origin iframe (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class CicScope:
    page: object
    frame: object | None = None
    frame_name: str | None = None

    @property
    def is_main(self) -> bool:
        return self.frame is None

    def locator(self, selector: str):
        if self.frame is not None:
            return self.frame.locator(selector)
        return self.page.locator(selector)

    def get_by_role(self, role: str, **kwargs):
        if self.frame is not None:
            return self.frame.get_by_role(role, **kwargs)
        return self.page.get_by_role(role, **kwargs)

    def get_by_text(self, text: str, **kwargs):
        if self.frame is not None:
            return self.frame.get_by_text(text, **kwargs)
        return self.page.get_by_text(text, **kwargs)

    def get_by_label(self, label: str, **kwargs):
        if self.frame is not None:
            return self.frame.get_by_label(label, **kwargs)
        return self.page.get_by_label(label, **kwargs)

    def eval_on_selector_all(self, selector: str, expression: str):
        if self.frame is not None:
            return self.frame.eval_on_selector_all(selector, expression)
        return self.page.eval_on_selector_all(selector, expression)


def _same_origin(page_url: str, frame_url: str) -> bool:
    if not frame_url or frame_url in ("about:blank", "about:srcdoc"):
        return False
    page = urlparse(page_url)
    frame = urlparse(frame_url)
    if page.scheme == "file" and frame.scheme == "file":
        return True
    return bool(page.netloc and frame.netloc and page.netloc == frame.netloc)


def iter_cic_scopes(page, *, include_iframes: bool):
    """Yield main page scope then same-origin child frames."""
    yield CicScope(page=page, frame=None, frame_name="main")
    if not include_iframes:
        return
    for index, frame in enumerate(page.frames):
        if frame == page.main_frame:
            continue
        try:
            frame_url = frame.url
        except Exception:
            continue
        if not _same_origin(page.url, frame_url):
            continue
        name = frame.name or f"frame-{index}"
        yield CicScope(page=page, frame=frame, frame_name=name)
