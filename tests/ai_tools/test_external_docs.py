"""Tests for external_docs URL extraction and fetching."""

import httpx
import pytest
import respx

from vibe_heal.ai_tools.external_docs import (
    _MAX_DOC_BYTES,
    _is_safe_url,
    extract_urls,
    fetch_external_rule_docs,
    fetch_url_content,
)


class TestIsSafeUrl:
    def test_localhost_blocked(self) -> None:
        assert not _is_safe_url("http://localhost/evil")

    def test_loopback_ip_blocked(self) -> None:
        assert not _is_safe_url("http://127.0.0.1/evil")

    def test_ipv6_loopback_blocked(self) -> None:
        assert not _is_safe_url("http://[::1]/evil")

    def test_private_class_a_blocked(self) -> None:
        assert not _is_safe_url("http://10.0.0.1/evil")

    def test_private_class_b_blocked(self) -> None:
        assert not _is_safe_url("http://172.16.0.1/evil")

    def test_private_class_c_blocked(self) -> None:
        assert not _is_safe_url("http://192.168.1.1/evil")

    def test_public_hostname_allowed(self) -> None:
        assert _is_safe_url("https://next.sonarqube.com/sonarqube/coding_rules")

    def test_public_ip_allowed(self) -> None:
        assert _is_safe_url("https://1.1.1.1/doc")


class TestExtractUrls:
    def test_single_url(self) -> None:
        urls = extract_urls("See https://example.com/rule for details.")
        assert urls == ["https://example.com/rule"]

    def test_multiple_urls(self) -> None:
        urls = extract_urls("See https://example.com/a and https://example.com/b.")
        assert urls == ["https://example.com/a", "https://example.com/b"]

    def test_no_urls(self) -> None:
        assert extract_urls("No links here at all.") == []

    def test_http_and_https(self) -> None:
        urls = extract_urls("http://old.example.com and https://new.example.com")
        assert len(urls) == 2

    def test_empty_string(self) -> None:
        assert extract_urls("") == []


class TestFetchUrlContent:
    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_fetch(self) -> None:
        respx.get("https://example.com/doc.md").mock(return_value=httpx.Response(200, text="# Rule\nDo not do X."))
        content = await fetch_url_content("https://example.com/doc.md")
        assert content == "# Rule\nDo not do X."

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_returns_none(self) -> None:
        respx.get("https://example.com/missing.md").mock(return_value=httpx.Response(404))
        content = await fetch_url_content("https://example.com/missing.md")
        assert content is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_error_returns_none(self) -> None:
        respx.get("https://example.com/error.md").mock(side_effect=httpx.ConnectError("refused"))
        content = await fetch_url_content("https://example.com/error.md")
        assert content is None

    @pytest.mark.asyncio
    async def test_ssrf_localhost_returns_none(self) -> None:
        content = await fetch_url_content("http://localhost/secret")
        assert content is None

    @pytest.mark.asyncio
    async def test_ssrf_private_ip_returns_none(self) -> None:
        content = await fetch_url_content("http://192.168.1.1/secret")
        assert content is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_large_response_is_truncated(self) -> None:
        large_content = "x" * (_MAX_DOC_BYTES + 1000)
        respx.get("https://example.com/large.md").mock(return_value=httpx.Response(200, text=large_content))
        content = await fetch_url_content("https://example.com/large.md")
        assert content is not None
        assert len(content.encode("utf-8")) <= _MAX_DOC_BYTES


class TestFetchExternalRuleDocs:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_url_in_message(self) -> None:
        respx.get("https://example.com/rule.md").mock(return_value=httpx.Response(200, text="# Rule doc"))
        docs = await fetch_external_rule_docs("Fix this. See https://example.com/rule.md")
        assert docs == ["# Rule doc"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_skips_failed_url(self) -> None:
        respx.get("https://example.com/ok.md").mock(return_value=httpx.Response(200, text="good"))
        respx.get("https://example.com/bad.md").mock(return_value=httpx.Response(500))
        docs = await fetch_external_rule_docs("See https://example.com/ok.md and https://example.com/bad.md")
        assert docs == ["good"]

    @pytest.mark.asyncio
    async def test_no_urls_returns_empty(self) -> None:
        docs = await fetch_external_rule_docs("No links in this message.")
        assert docs == []

    @pytest.mark.asyncio
    async def test_ssrf_url_in_message_is_skipped(self) -> None:
        docs = await fetch_external_rule_docs("See http://192.168.1.1/rule for details.")
        assert docs == []
