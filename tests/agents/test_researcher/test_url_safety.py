from unittest.mock import patch

from agents.researcher.source_collector import SourceCollector


def test_http_public_allowed() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 80))]):
        assert SourceCollector._is_allowed_url("http://example.com")


def test_https_public_allowed() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]):
        assert SourceCollector._is_allowed_url("https://example.com")


def test_file_rejected() -> None:
    assert not SourceCollector._is_allowed_url("file:///etc/passwd")


def test_localhost_rejected() -> None:
    assert not SourceCollector._is_allowed_url("http://localhost:8080")


def test_loopback_rejected() -> None:
    assert not SourceCollector._is_allowed_url("http://127.0.0.1")


def test_private_ranges_rejected() -> None:
    assert not SourceCollector._is_allowed_url("http://10.0.0.1")
    assert not SourceCollector._is_allowed_url("http://172.16.0.10")
    assert not SourceCollector._is_allowed_url("http://192.168.1.1")


def test_link_local_rejected() -> None:
    assert not SourceCollector._is_allowed_url("http://169.254.1.10")


def test_dns_resolves_private_ip_rejected() -> None:
    with patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("10.1.2.3", 443))]):
        assert not SourceCollector._is_allowed_url("https://safe.example")
