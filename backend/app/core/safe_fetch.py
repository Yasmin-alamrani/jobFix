"""Refuse to reach anything that lives on a private network.

A pasted job URL is attacker-influenced input: the user is often pasting a link
someone else gave them. Without this, `http://169.254.169.254/` reaches cloud
metadata and `http://127.0.0.1:8000/` reaches our own API, and the response
comes back through the job-intake path as if it were a posting.

The check runs in two places on purpose, because neither alone is sufficient:

  1. `assert_public_literal` -- offline, no DNS. Catches an address written
     directly into the URL, which is the whole of the obvious attack. Cheap
     enough to sit inside `Policy.check` without making a gate do network I/O.
  2. `safe_get` -- resolves at fetch time and checks every redirect hop. Catches
     a *hostname* that points somewhere private (`localtest.me` resolves to
     127.0.0.1), which no amount of URL inspection can see.

Checking only at (1) would miss hostnames. Checking only at (2) would let a
literal through every code path that does not use `safe_get`.

Known limitation, stated rather than papered over: a name that resolves to a
public address for our check and a private one for the connection that follows
(DNS rebinding) is not closed here. Closing it means pinning the resolved
address and connecting to it directly with a `Host` header, which httpx does not
expose cleanly. Every address a name resolves to is checked, which raises the
cost of that attack without eliminating it.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

# Names that mean "this machine" or "this network" without ever being an IP
# literal, so the offline gate would otherwise have to let them through and
# wait for the resolver. They are worth naming because they are what someone
# actually types: `http://localhost:8000/` is the obvious probe.
BLOCKED_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
# Suffixes reserved for private networks and service discovery (RFC 6762,
# RFC 8375, and the convention cloud providers use for internal endpoints).
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan")
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = httpx.Timeout(20.0)


class BlockedAddress(RuntimeError):
    """The URL points somewhere we refuse to reach."""


def _unwrap(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Reduce an IPv4-mapped IPv6 address to the IPv4 address it carries.

    `::ffff:127.0.0.1` is loopback, but `IPv6Address.is_loopback` only answers
    for `::1`, so the mapped form would otherwise pass every check.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    return mapped if mapped is not None else ip


def is_public(ip: ipaddress._BaseAddress) -> bool:
    """True only for addresses on the public internet.

    `is_private` already covers loopback and the RFC1918 ranges, but the others
    are listed explicitly: link-local is where cloud metadata lives, and it is
    the single most important address to refuse.
    """
    ip = _unwrap(ip)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def as_literal(host: str) -> ipaddress._BaseAddress | None:
    """Parse a host as an IP address, or return None if it is a name.

    Handles the bracketed IPv6 form from a URL, and the integer and octal
    spellings of IPv4 (`2130706433`, `0177.0.0.1`) that `ip_address` rejects
    but every resolver accepts.
    """
    host = host.strip().strip("[]")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    # Integer and octal forms: let the resolver's own parser decide, but only
    # when the host cannot be a real name.
    if host.replace(".", "").isdigit():
        try:
            return ipaddress.ip_address(socket.gethostbyname(host))
        except (OSError, ValueError):
            return None
    return None


def _host_and_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise BlockedAddress(f"Only http(s) URLs may be fetched: {url!r}")
    host = parsed.hostname
    if not host:
        raise BlockedAddress(f"Not a usable URL: {url!r}")
    return host, parsed.port or (443 if parsed.scheme.lower() == "https" else 80)


def assert_public_literal(url: str) -> None:
    """Offline gate: refuse an address written directly into the URL.

    Does no DNS, so it is safe to call from anywhere -- including a policy gate
    that unit tests exercise without a network.
    """
    host, _ = _host_and_port(url)
    name = host.lower().rstrip(".")
    if name in BLOCKED_NAMES or name.endswith(BLOCKED_SUFFIXES):
        raise BlockedAddress(
            f"{host} is a local or internal name. Paste a public job URL."
        )
    ip = as_literal(host)
    if ip is not None and not is_public(ip):
        raise BlockedAddress(
            f"{host} is a private or reserved address. Paste a public job URL."
        )


def resolved_addresses(host: str, port: int) -> list[ipaddress._BaseAddress]:
    try:
        info = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedAddress(f"{host} does not resolve: {exc}") from exc
    return [ipaddress.ip_address(entry[4][0]) for entry in info]


def assert_public_url(url: str) -> None:
    """Full gate: the literal check, then every address the name resolves to.

    Blocks when *any* resolved address is private. A name that answers with both
    a public and a private address is a rebinding setup, not a coincidence.
    """
    assert_public_literal(url)
    host, port = _host_and_port(url)
    if as_literal(host) is not None:
        return  # already checked, and getaddrinfo would just echo it back
    for ip in resolved_addresses(host, port):
        if not is_public(ip):
            raise BlockedAddress(
                f"{host} resolves to {ip}, which is a private or reserved "
                "address. Paste a public job URL."
            )


def safe_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    max_redirects: int = MAX_REDIRECTS,
) -> httpx.Response | None:
    """GET a URL, checking the destination before every hop.

    Redirects are followed by hand rather than by httpx, because httpx checks
    nothing between hops: a public URL that 302s to 169.254.169.254 would
    otherwise be fetched with no gate in front of it.

    Returns None on a transport failure, matching what the intake path already
    expects from a failed fetch. A blocked address raises instead -- that is a
    refusal, not a failure, and the caller must be able to tell them apart.
    """
    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            assert_public_url(current)
            try:
                response = client.get(current, headers=headers or {})
            except httpx.HTTPError as exc:
                log.info("fetch failed for %s: %s", current, exc)
                return None

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return response
                current = str(httpx.URL(current).join(location))
                continue
            return response

    raise BlockedAddress(f"Too many redirects from {url!r}.")
