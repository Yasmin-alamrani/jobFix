"""The SSRF boundary.

Every vector here was verified *reachable* before the guard existed -- these are
regressions, not hypotheticals. `Policy.for_pasted_url` builds its allowlist
from the pasted URL itself, so the host gate structurally cannot refuse an
address the user typed; something ahead of it has to.

No test here touches the network. The offline gate is offline by design, which
is what lets it sit inside `Policy.check`.
"""
from __future__ import annotations

import ipaddress

import httpx
import pytest

from app.agents.scout.policy import Policy, PolicyViolation
from app.core import safe_fetch
from app.core.safe_fetch import (
    BlockedAddress,
    as_literal,
    assert_public_literal,
    assert_public_url,
    is_public,
    safe_get,
)

# Each of these was ALLOWED before the guard. The comment is why it matters.
BLOCKED = [
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata, the big one
    "http://127.0.0.1:8000/api/health",           # our own API
    "http://localhost/admin",
    "http://localhost:8000/",
    "http://[::1]:8000/",
    "http://192.168.1.1/",                        # home router
    "http://10.0.0.1/",
    "http://172.16.5.4/",
    "http://0.0.0.0/",
    "http://2130706433/",                         # 127.0.0.1 as an integer
    "http://printer.local/",
    "http://vault.internal/",
    "http://foo.home.arpa/",
]

PUBLIC = [
    "https://boards.greenhouse.io/tamara/jobs/4321",
    "https://www.linkedin.com/jobs/view/123456789",
    "https://jobs.ashbyhq.com/rain/abc-def",
    "http://93.184.216.34/a-job",                 # a public literal is fine
]


@pytest.mark.parametrize("url", BLOCKED)
def test_private_destinations_are_refused_offline(url):
    with pytest.raises(BlockedAddress):
        assert_public_literal(url)


@pytest.mark.parametrize("url", PUBLIC)
def test_public_job_urls_still_pass(url):
    assert_public_literal(url)


@pytest.mark.parametrize("url", BLOCKED)
def test_the_policy_gate_refuses_them_too(url):
    """The guard has to bite through `Policy.check`, not just on its own.

    This is the path a pasted URL actually takes, and the one that was open.
    """
    with pytest.raises(PolicyViolation):
        Policy.for_pasted_url(url).check(url)


def test_ipv4_mapped_ipv6_does_not_slip_through():
    """`::ffff:127.0.0.1` is loopback, but IPv6Address.is_loopback says no."""
    assert not is_public(ipaddress.ip_address("::ffff:127.0.0.1"))
    assert not is_public(ipaddress.ip_address("::ffff:169.254.169.254"))


def test_a_hostname_is_not_mistaken_for_a_literal():
    assert as_literal("boards.greenhouse.io") is None
    assert as_literal("127.0.0.1") == ipaddress.ip_address("127.0.0.1")
    assert as_literal("[::1]") == ipaddress.ip_address("::1")


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "gopher://x/"])
def test_only_http_schemes_are_fetchable(url):
    with pytest.raises(BlockedAddress):
        assert_public_literal(url)


def test_a_name_resolving_to_a_private_address_is_refused(monkeypatch):
    """The case the offline gate cannot see, so `safe_get` must.

    `localtest.me` and friends are real public names that answer 127.0.0.1.
    """
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("127.0.0.1")],
    )
    with pytest.raises(BlockedAddress, match="resolves to"):
        assert_public_url("https://localtest.me/job/1")


def test_a_name_resolving_publicly_is_allowed(monkeypatch):
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )
    assert_public_url("https://example.com/job/1")


def test_any_private_answer_blocks_a_multi_homed_name(monkeypatch):
    """A name answering with both a public and a private address is a setup."""
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("169.254.169.254"),
        ],
    )
    with pytest.raises(BlockedAddress):
        assert_public_url("https://dual.example.com/job/1")


def _transport(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client",
        lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(handler)}),
    )


def test_a_redirect_into_the_private_network_is_refused(monkeypatch):
    """The reason redirects are followed by hand.

    httpx checks nothing between hops, so a public URL that 302s to the metadata
    endpoint would be fetched with no gate in front of it.
    """
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        return httpx.Response(200, text="secrets")

    _transport(monkeypatch, handler)
    with pytest.raises(BlockedAddress):
        safe_get("https://example.com/job/1")


def test_a_normal_redirect_is_followed(monkeypatch):
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://example.com/new"})
        return httpx.Response(200, text="the job")

    _transport(monkeypatch, handler)
    response = safe_get("https://example.com/old")
    assert response is not None and response.text == "the job"


def test_a_redirect_loop_stops(monkeypatch):
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )
    _transport(
        monkeypatch,
        lambda request: httpx.Response(302, headers={"location": "https://example.com/loop"}),
    )
    with pytest.raises(BlockedAddress, match="redirects"):
        safe_get("https://example.com/loop")


def test_a_transport_failure_is_not_a_refusal(monkeypatch):
    """The caller must be able to tell "could not reach" from "will not reach"."""
    monkeypatch.setattr(
        safe_fetch, "resolved_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )

    def handler(request):
        raise httpx.ConnectError("down")

    _transport(monkeypatch, handler)
    assert safe_get("https://example.com/job") is None


def test_an_unresolvable_host_is_refused_rather_than_fetched():
    with pytest.raises(BlockedAddress, match="does not resolve"):
        assert_public_url("https://no-such-host.invalid/job")


def test_legitimate_hard_blocks_still_report_as_hard_blocks():
    """The new gate must not shadow the existing ones.

    A Bayt listing URL is public, so it passes the address gate and must still
    be refused by the robots/hard-block gate with its own message.
    """
    with pytest.raises(PolicyViolation, match="hard-blocked"):
        Policy.for_pasted_url("https://www.bayt.com/en/jobs/").check(
            "https://www.bayt.com/en/jobs/"
        )
