"""Fetch documentation from URLs found in external rule issue messages."""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://\S+")


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from a string."""
    return _URL_PATTERN.findall(text)


async def fetch_url_content(url: str) -> str | None:
    """Fetch the text content of a URL, returning None on any error."""
    logger.debug("Fetching external rule doc from %s", url)
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


async def fetch_external_rule_docs(message: str) -> list[str]:
    """Extract URLs from an issue message and return fetched content for each."""
    urls = extract_urls(message)
    docs = []
    for url in urls:
        content = await fetch_url_content(url)
        if content is not None:
            docs.append(content)
    return docs
