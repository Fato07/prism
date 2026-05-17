"""Second-stage evidence extraction tests."""

import socket

import pytest

from sentinel.evidence_extraction import (
    EvidencePageExtractRequest,
    EvidencePageExtractResult,
    _extract_tool_arguments,
    clean_extracted_text,
    map_extraction_result,
    sanitize_source_url,
    source_url_is_public_http,
)


def test_source_url_safety_blocks_private_and_secret_urls() -> None:
    assert source_url_is_public_http("https://example.com/report") is True
    assert source_url_is_public_http("https://user:secret@example.com/report") is False
    assert source_url_is_public_http("http://127.0.0.1/report") is False
    assert source_url_is_public_http("http://169.254.169.254/latest/meta-data") is False
    assert source_url_is_public_http("file:///tmp/report") is False


def test_source_url_safety_blocks_hostnames_resolving_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*_: object, **__: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert source_url_is_public_http("https://attacker.example/report") is False


def test_extracted_excerpt_redacts_secret_like_values() -> None:
    result = EvidencePageExtractResult(
        url="https://example.com/report",
        text=(
            "Current evidence. api_key=supersecretvalue123 "
            "token: abcdefghijklmnop sk-testsecret12345 "
            "Authorization: Bearer ghp_secretvalue123456"
        ),
        provider="static_extractor",
    )

    excerpt = result.excerpt()

    assert "supersecretvalue123" not in excerpt
    assert "abcdefghijklmnop" not in excerpt
    assert "sk-testsecret12345" not in excerpt
    assert "ghp_secretvalue123456" not in excerpt
    assert "api_key=[redacted]" in excerpt
    assert "Authorization: Bearer [redacted]" in excerpt


def test_sanitize_source_url_removes_secret_parts() -> None:
    assert sanitize_source_url("https://user:secret@example.com/path?api_key=secret#frag") == (
        "https://example.com/path"
    )


def test_exa_web_fetch_mapper_uses_hosted_mcp_schema() -> None:
    request = EvidencePageExtractRequest(
        url="https://example.com/report",
        objective="Verify source evidence.",
        max_chars=900,
    )

    assert _extract_tool_arguments("exa_web_fetch", request) == {
        "urls": ["https://example.com/report"],
        "maxCharacters": 900,
    }

    result = map_extraction_result(
        "exa_extract",
        "# Example Domain\n\nCurrent Fed rates data supports the evidence check.",
        request,
    )

    assert result is not None
    assert result.provider == "exa_contents"
    assert result.tool_name == "web_fetch_exa"
    assert result.text.startswith("# Example Domain")



def test_generic_extraction_mapper_normalizes_markdown() -> None:
    request = EvidencePageExtractRequest(
        url="https://example.com/report",
        objective="Verify source evidence.",
    )
    result = map_extraction_result(
        "generic_extract",
        {
            "title": "Report",
            "url": "https://example.com/report?token=secret",
            "markdown": "# Report\n\nCurrent Fed rates data supports the July 2026 evidence check.",
        },
        request,
    )

    assert result is not None
    assert result.sanitized_url() == "https://example.com/report"
    assert len(result.content_hash()) == 64
    assert clean_extracted_text(result.text).startswith("# Report Current Fed")
