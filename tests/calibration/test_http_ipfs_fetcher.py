"""HttpIpfsFetcher refactored behavior: client reuse and deterministic close."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from prism_calibration.harvest import HttpIpfsFetcher


class TestHttpIpfsFetcherClientReuse:
    """Verify HttpIpfsFetcher reuses a single httpx.Client across fetches."""

    @patch("httpx.Client")
    def test_fetcher_creates_client_once_at_init(self, mock_client_cls: MagicMock) -> None:
        """The httpx.Client is constructed once in __init__, not per fetch."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()

        # Client constructed once at init
        assert mock_client_cls.call_count == 1
        assert fetcher._client is mock_client

    @patch("httpx.Client")
    def test_fetch_json_uses_pre_created_client(self, mock_client_cls: MagicMock) -> None:
        """fetch_json uses the pre-created client instance, not a new one."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()
        result = fetcher.fetch_json("QmTestCid")

        # No new Client created during fetch_json
        assert mock_client_cls.call_count == 1
        # The pre-created client was used
        mock_client.get.assert_called_once()
        assert result == {"key": "value"}

    @patch("httpx.Client")
    def test_multiple_fetches_reuse_same_client(self, mock_client_cls: MagicMock) -> None:
        """Multiple fetch_json calls reuse the same httpx.Client instance."""
        mock_client = MagicMock()
        mock_response_a = MagicMock()
        mock_response_a.json.return_value = {"cid": "a"}
        mock_response_a.raise_for_status = MagicMock()
        mock_response_b = MagicMock()
        mock_response_b.json.return_value = {"cid": "b"}
        mock_response_b.raise_for_status = MagicMock()
        mock_client.get.side_effect = [mock_response_a, mock_response_b]
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()
        result_a = fetcher.fetch_json("QmCidA")
        result_b = fetcher.fetch_json("QmCidB")

        # Still only one Client instance created
        assert mock_client_cls.call_count == 1
        assert mock_client.get.call_count == 2
        assert result_a == {"cid": "a"}
        assert result_b == {"cid": "b"}

    @patch("httpx.Client")
    def test_close_closes_underlying_client(self, mock_client_cls: MagicMock) -> None:
        """close() deterministically closes the httpx.Client."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()
        fetcher.close()

        mock_client.close.assert_called_once()

    @patch("httpx.Client")
    def test_context_manager_closes_on_exit(self, mock_client_cls: MagicMock) -> None:
        """Using HttpIpfsFetcher as a context manager closes the client on exit."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        with HttpIpfsFetcher() as fetcher:
            _ = fetcher  # use inside context

        mock_client.close.assert_called_once()

    @patch("httpx.Client")
    def test_fetch_after_close_still_uses_client(self, mock_client_cls: MagicMock) -> None:
        """After close(), further fetches still use the (closed) client — behavior preserved."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"closed": True}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()
        fetcher.close()
        # Calling fetch_json after close delegates to the underlying client
        # which may raise its own error; this preserves the existing behavior
        # of not silently swallowing the close.
        fetcher.fetch_json("QmPostClose")

        # The same client instance was used (not a new one)
        assert mock_client_cls.call_count == 1
        mock_client.get.assert_called_once()

    @patch("httpx.Client")
    def test_context_manager_protocol(self, mock_client_cls: MagicMock) -> None:
        """HttpIpfsFetcher supports __enter__/__exit__ protocol."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        fetcher = HttpIpfsFetcher()
        assert fetcher.__enter__() is fetcher
        fetcher.__exit__(None, None, None)
        mock_client.close.assert_called_once()
