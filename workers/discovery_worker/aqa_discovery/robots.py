"""robots.txt fetch and disallow checks (SPEC §15.6, Day 17)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "AutonomousQABot"


def _robots_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


class RobotsChecker:
    """Cached robots.txt rules for a crawl origin."""

    def __init__(
        self,
        base_url: str,
        *,
        enabled: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.enabled = enabled
        self.user_agent = user_agent
        self._parser: RobotFileParser | None = None
        if enabled:
            self._parser = self._fetch_parser(base_url)

    def _fetch_parser(self, base_url: str) -> RobotFileParser | None:
        robots_url = _robots_url(base_url)
        try:
            import httpx

            response = httpx.get(robots_url, timeout=10.0, follow_redirects=True)
            if response.status_code >= 400:
                logger.info(
                    "DiscoveryWorker robots.txt unavailable",
                    extra={"robotsUrl": robots_url, "status": response.status_code},
                )
                return None
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            logger.info("DiscoveryWorker robots.txt loaded", extra={"robotsUrl": robots_url})
            return parser
        except Exception as exc:
            logger.warning(
                "DiscoveryWorker robots.txt fetch failed",
                extra={"robotsUrl": robots_url, "error": str(exc)},
            )
            return None

    def is_allowed(self, url: str) -> bool:
        if not self.enabled:
            return True
        if self._parser is None:
            return True
        return self._parser.can_fetch(self.user_agent, url)
