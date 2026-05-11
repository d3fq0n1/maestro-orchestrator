"""
Smoke tests for maestro/security/pinned_transport.py.

Item 7 step 2. Uses an httpx.MockTransport as the inner
transport and an injected peer_cert_extractor (Q-7.5 = a) so
the PinnedTransport verification flow is exercised end-to-end
without a real TLS server.
"""

import asyncio
import datetime

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from maestro.security.cert_pinning import (
    Pin,
    PinStore,
    PinVerificationError,
    compute_spki_sha256,
)
from maestro.security.pinned_transport import (
    PinnedTransport,
    _default_peer_cert_extractor,
)


# ---- shared cert fixtures ----


def _gen_cert(common_name: str = "api.test"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


# Generate one cert at module load so individual tests don't pay
# the keygen cost. PinStore + extractor decisions vary per test.
_CERT_PEM = _gen_cert("api.test")
_CERT_SPKI = compute_spki_sha256(_CERT_PEM)


# ---- helpers ----


def _mock_transport(status: int = 200, content: bytes = b"ok") -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(status, content=content))


def _store_with(hostname: str, spki: str) -> PinStore:
    s = PinStore()
    s.add_pin(Pin(hostname=hostname, spki_sha256=spki))
    return s


def _make_pinned(
    store: PinStore,
    *,
    extractor=None,
    inner=None,
    require_pin: bool = True,
) -> PinnedTransport:
    return PinnedTransport(
        store=store,
        inner_transport=inner or _mock_transport(),
        peer_cert_extractor=extractor or (lambda r: _CERT_PEM),
        require_pin=require_pin,
    )


def _run(coro):
    return asyncio.run(coro)


async def _request(client: httpx.AsyncClient) -> httpx.Response:
    return await client.get("https://api.test/")


# ---- ABC compliance ----


def test_pinned_transport_is_async_base_transport():
    t = _make_pinned(_store_with("api.test", _CERT_SPKI))
    assert isinstance(t, httpx.AsyncBaseTransport)


# ---- happy path ----


def test_response_returned_when_pin_matches():
    """Match: SPKI of presented cert is in the pin store; the
    inner transport's response passes through.
    """
    transport = _make_pinned(_store_with("api.test", _CERT_SPKI))

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await _request(client)

    response = _run(go())
    assert response.status_code == 200
    assert response.content == b"ok"


def test_inner_response_body_preserved():
    """Body bytes returned by the inner transport are preserved
    verbatim by PinnedTransport on success.
    """
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"distinctive payload"),
    )
    transport = _make_pinned(
        _store_with("api.test", _CERT_SPKI),
        inner=inner,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await _request(client)

    response = _run(go())
    assert response.content == b"distinctive payload"


# ---- mismatch ----


def test_pin_mismatch_raises_pin_verification_error():
    """Pin in store doesn't match the presented cert; raises."""
    transport = _make_pinned(
        _store_with("api.test", "sha256:" + "f" * 64),  # wrong pin
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)

    with pytest.raises(PinVerificationError) as exc_info:
        _run(go())
    assert exc_info.value.hostname == "api.test"
    assert exc_info.value.presented_spki == _CERT_SPKI


def test_unknown_pinned_hostname_raises_under_require_pin_true():
    """The store has pins, but not for the hostname being
    requested. fail-closed mode (require_pin=True default)
    raises.
    """
    store = PinStore()
    store.add_pin(Pin("other.test", _CERT_SPKI))   # pinned different host

    transport = _make_pinned(store, require_pin=True)

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)

    with pytest.raises(PinVerificationError):
        _run(go())


def test_unknown_pinned_hostname_passes_under_require_pin_false():
    """fail-open mode for gradual rollout: hostnames absent from
    the store pass through.
    """
    store = PinStore()  # empty
    transport = _make_pinned(store, require_pin=False)

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await _request(client)

    response = _run(go())
    assert response.status_code == 200


# ---- extractor returns None (no TLS / extraction failed) ----


def test_extractor_returns_none_with_pinned_host_raises():
    """Hostname is pinned but the extractor couldn't get a cert
    (no SSL info on the response). fail-closed: raise.
    """
    transport = _make_pinned(
        _store_with("api.test", _CERT_SPKI),
        extractor=lambda r: None,
        require_pin=True,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)

    with pytest.raises(PinVerificationError) as exc_info:
        _run(go())
    assert "<no-cert>" in exc_info.value.presented_spki


def test_extractor_returns_none_unpinned_host_passes():
    """Extractor returns None and the hostname isn't pinned. The
    PinnedTransport doesn't have anything to verify against, so
    the response passes through (regardless of require_pin).
    """
    transport = _make_pinned(
        PinStore(),  # nothing pinned
        extractor=lambda r: None,
        require_pin=True,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            return await _request(client)

    response = _run(go())
    assert response.status_code == 200


# ---- extractor crashes ----


def test_extractor_exception_with_pinned_host_raises_pin_verification_error():
    """Extractor itself crashed; for a pinned host this is
    treated as a verification failure.
    """
    def crash(response):
        raise RuntimeError("extractor exploded")

    transport = _make_pinned(
        _store_with("api.test", _CERT_SPKI),
        extractor=crash,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)

    with pytest.raises(PinVerificationError) as exc_info:
        _run(go())
    assert "extractor-error" in exc_info.value.presented_spki


def test_extractor_exception_unpinned_host_propagates():
    """When the host isn't pinned, an extractor crash is just a
    runtime error — propagate it so callers can see the bug.
    The PinnedTransport doesn't swallow extractor failures on
    un-pinned hosts.
    """
    def crash(response):
        raise RuntimeError("extractor exploded")

    transport = _make_pinned(
        PinStore(),
        extractor=crash,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)

    with pytest.raises(RuntimeError, match="exploded"):
        _run(go())


# ---- aclose forwards to inner ----


def test_aclose_forwards_to_inner_transport():
    closed = {"flag": False}

    class _RecordingTransport(httpx.MockTransport):
        async def aclose(self):
            closed["flag"] = True

    inner = _RecordingTransport(lambda req: httpx.Response(200))
    transport = PinnedTransport(
        store=_store_with("api.test", _CERT_SPKI),
        inner_transport=inner,
        peer_cert_extractor=lambda r: _CERT_PEM,
    )

    _run(transport.aclose())
    assert closed["flag"] is True


# ---- default extractor ----


def test_default_extractor_returns_none_when_no_extensions():
    """Default extractor handles a Response without extensions
    by returning None (no crash). MockTransport-based responses
    typically have no network_stream.
    """
    response = httpx.Response(200, content=b"ok")
    assert _default_peer_cert_extractor(response) is None


def test_default_extractor_returns_none_when_no_network_stream():
    """If response.extensions exists but lacks network_stream
    (the typical MockTransport case), the extractor returns None
    cleanly.
    """
    response = httpx.Response(200, content=b"ok", extensions={})
    assert _default_peer_cert_extractor(response) is None


def test_default_extractor_returns_none_when_get_extra_info_returns_none():
    """A network_stream where get_extra_info returns None for
    ssl_object (HTTP rather than HTTPS) returns None.
    """
    class _Stream:
        def get_extra_info(self, key):
            return None

    response = httpx.Response(
        200, content=b"ok",
        extensions={"network_stream": _Stream()},
    )
    assert _default_peer_cert_extractor(response) is None


def test_default_extractor_returns_cert_when_ssl_object_present():
    """Happy path: network_stream.get_extra_info('ssl_object')
    returns an object whose getpeercert(binary_form=True)
    returns the DER-encoded cert.
    """
    cert_der = b"fake-der-bytes"

    class _SSLObject:
        def getpeercert(self, binary_form):
            assert binary_form is True
            return cert_der

    class _Stream:
        def get_extra_info(self, key):
            assert key == "ssl_object"
            return _SSLObject()

    response = httpx.Response(
        200, content=b"ok",
        extensions={"network_stream": _Stream()},
    )
    assert _default_peer_cert_extractor(response) == cert_der


# ---- end-to-end-ish: verify is invoked once per request ----


def test_extractor_invoked_once_per_request():
    calls = {"n": 0}

    def counting_extractor(response):
        calls["n"] += 1
        return _CERT_PEM

    transport = _make_pinned(
        _store_with("api.test", _CERT_SPKI),
        extractor=counting_extractor,
    )

    async def go():
        async with httpx.AsyncClient(transport=transport) as client:
            await _request(client)
            await _request(client)
            await _request(client)

    _run(go())
    assert calls["n"] == 3
