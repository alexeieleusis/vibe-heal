"""Fetch documentation from URLs found in external rule issue messages."""

import ipaddress
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https?://\S+")
_TRAILING_PUNCTUATION = frozenset(".,);:'\"")
_MAX_DOC_BYTES = 50_000

_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _is_safe_url(url: str) -> bool:
    """Return False if the URL targets a private or loopback address."""
    try:
        host = urlparse(url).hostname or ""
        if host in _LOOPBACK_HOSTNAMES:
            return False
        addr = ipaddress.ip_address(host)
        return not any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return True  # hostname (not a bare IP) — allow through


_BLOB_PREFIX = "https://github.com/jpablo/vibe-types/blob/main/"
_RAW_PREFIXES = (
    "https://raw.githubusercontent.com/jpablo/vibe-types/refs/heads/main/",
    "https://raw.githubusercontent.com/jpablo/vibe-types/main/",
)


def _vibe_types_local_path(url: str) -> Path | None:
    """Map a vibe-types GitHub URL to its local submodule path, or None if not a vibe-types URL."""
    rel: str | None = None
    if url.startswith(_BLOB_PREFIX):
        rel = url[len(_BLOB_PREFIX) :]
    else:
        for prefix in _RAW_PREFIXES:
            if url.startswith(prefix):
                rel = url[len(prefix) :]
                break
    if rel is None:
        return None
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent / "vendor" / "vibe-types" / rel
    return None


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from a string, stripping trailing punctuation."""
    return [url.rstrip("".join(_TRAILING_PUNCTUATION)) for url in _URL_PATTERN.findall(text)]


async def _stream_capped(url: str, client: httpx.AsyncClient) -> str | None:
    """Fetch up to _MAX_DOC_BYTES from url using an existing client."""
    logger.debug("Fetching external rule doc from %s", url)
    chunks: list[bytes] = []
    try:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = 0
            async for chunk in response.aiter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= _MAX_DOC_BYTES:
                    break
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None
    return b"".join(chunks)[:_MAX_DOC_BYTES].decode("utf-8", errors="replace")


async def fetch_url_content(url: str) -> str | None:
    """Fetch the text content of a URL, returning None on any error or SSRF-blocked host."""
    local = _vibe_types_local_path(url)
    if local is not None:
        if local.exists():
            logger.debug("Reading vibe-types doc locally from %s", local)
            return local.read_text()
        logger.debug("Local vibe-types path not found: %s (submodule not initialized?)", local)
        # blob URLs return HTML over HTTP — convert to raw for the fallback
        if url.startswith(_BLOB_PREFIX):
            url = _RAW_PREFIXES[0] + url[len(_BLOB_PREFIX) :]
    if not _is_safe_url(url):
        logger.debug("Blocked SSRF-risk URL: %s", url)
        return None
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        return await _stream_capped(url, client)


async def fetch_external_rule_docs(message: str) -> list[str]:
    """Extract URLs from an issue message and return fetched content for each."""
    urls = [u for u in extract_urls(message) if _is_safe_url(u)]
    if not urls:
        return []
    docs = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for url in urls:
            content = await _stream_capped(url, client)
            if content is not None:
                docs.append(content)
    return docs
