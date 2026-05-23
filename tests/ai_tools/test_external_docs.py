"""Tests for external_docs URL extraction and fetching."""

import httpx
import pytest
import respx

from vibe_heal.ai_tools.external_docs import extract_urls, fetch_external_rule_docs, fetch_url_content


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
