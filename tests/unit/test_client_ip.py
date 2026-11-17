from types import SimpleNamespace

from raahat.api.deps import client_ip


def _request(peer: str, forwarded: str | None = None):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def _settings(trust: bool = True, proxies: tuple[str, ...] = ()):
    return SimpleNamespace(trust_forwarded_headers=trust, trusted_proxies=proxies)


def test_forwarded_address_ignored_unless_enabled() -> None:
    assert client_ip(_request("127.0.0.1", "203.0.113.9"), _settings(trust=False)) == "127.0.0.1"


def test_tunnel_on_loopback_gives_the_appended_address() -> None:
    assert client_ip(_request("127.0.0.1", "203.0.113.9"), _settings()) == "203.0.113.9"


def test_client_cannot_choose_its_address() -> None:
    spoofed = "1.2.3.4, 203.0.113.9"
    assert client_ip(_request("127.0.0.1", spoofed), _settings()) == "203.0.113.9"


def test_docker_gateway_trusted_only_when_listed() -> None:
    assert client_ip(_request("172.18.0.1", "203.0.113.9"), _settings()) == "172.18.0.1"
    assert client_ip(_request("172.18.0.1", "203.0.113.9"), _settings(proxies=("172.16.0.0/12",))) == "203.0.113.9"


def test_untrusted_peer_header_is_ignored() -> None:
    assert client_ip(_request("198.51.100.7", "203.0.113.9"), _settings(proxies=("172.16.0.0/12",))) == "198.51.100.7"
