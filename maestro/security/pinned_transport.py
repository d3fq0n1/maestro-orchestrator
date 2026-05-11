"""
PinnedTransport — httpx wrapper that enforces SPKI cert pinning.

Item 7 step 2. Wraps an inner ``httpx.AsyncBaseTransport`` and
verifies the peer certificate's SPKI hash against a ``PinStore``
on every response.

Limitation (Q-7.4 = a, post-hoc verification):
    Verification happens AFTER the response is received. By
    then the request body has already been transmitted on the
    underlying TCP connection. The PinnedTransport therefore
    detects a malicious cert that would intercept replies but
    does NOT prevent exfiltration of request bodies on a
    misissued cert.

    A future hardening step can switch to mid-handshake
    verification via ``ssl.SSLContext`` callbacks without
    changing this module's public API.

Wiring example::

    pin_store = load_pin_store(Path("data/security/pins.json"))
    transport = PinnedTransport(
        store=pin_store,
        inner_transport=httpx.AsyncHTTPTransport(),
    )
    client = httpx.AsyncClient(transport=transport)

Operators who want pinning on a single agent simply construct an
``httpx.AsyncClient`` with this transport and pass it to the
agent's HTTP layer. No changes to existing agent files are
required (Q-7.2 = b decision).

Test surface (Q-7.5 = a, peer-cert-extractor injection):
    The ``peer_cert_extractor`` constructor parameter is a
    ``Callable[[httpx.Response], bytes | None]``. Real clients
    use the default extractor that reads from
    ``response.extensions["network_stream"]``. Tests inject a
    synthetic extractor that returns hand-crafted cert bytes,
    so the PinnedTransport verification logic is exercised
    without a real TLS server.
"""

from __future__ import annotations

from typing import Callable, Optional

import httpx

from maestro.security.cert_pinning import (
    PinStore,
    PinVerificationError,
    verify_pin,
)


def _default_peer_cert_extractor(response: httpx.Response) -> Optional[bytes]:
    """Extract DER-encoded peer cert from an httpx response.

    Modern httpx exposes the underlying network stream via
    ``response.extensions["network_stream"]``. The stream's
    ``get_extra_info("ssl_object")`` returns an ``SSLObject``;
    that object's ``getpeercert(binary_form=True)`` returns the
    cert in DER form.

    Returns None when the response wasn't TLS-encrypted (HTTP
    request, unrecognized extensions shape, etc.). The caller
    decides what to do with None — under ``require_pin=True``
    plus a pinned hostname, None means "fail closed."
    """
    extensions = getattr(response, "extensions", None)
    if not extensions:
        return None
    network_stream = extensions.get("network_stream")
    if network_stream is None:
        return None
    try:
        ssl_object = network_stream.get_extra_info("ssl_object")
    except Exception:
        return None
    if ssl_object is None:
        return None
    try:
        return ssl_object.getpeercert(binary_form=True)
    except Exception:
        return None


class PinnedTransport(httpx.AsyncBaseTransport):
    """``httpx.AsyncBaseTransport`` that enforces SPKI pinning.

    Wraps another transport (default ``httpx.AsyncHTTPTransport``).
    On every response, extracts the peer certificate via the
    ``peer_cert_extractor`` callable and verifies its SPKI hash
    against the configured ``PinStore``. Mismatches raise
    ``PinVerificationError`` (the response is dropped).

    Parameters
    ----------
    store:
        The ``PinStore`` to consult.
    inner_transport:
        The transport that actually performs the request. When
        ``None``, an ``httpx.AsyncHTTPTransport`` with default
        settings is used.
    peer_cert_extractor:
        Callable returning the DER-encoded peer cert from a
        response (or None when no TLS / unable to extract).
        Defaults to ``_default_peer_cert_extractor`` which reads
        from ``response.extensions["network_stream"]``.
    require_pin:
        Forwarded to ``verify_pin``. When True (default), missing
        pins for the hostname raise. When False, un-pinned
        hostnames pass through without verification (useful for
        gradual rollout).
    """

    def __init__(
        self,
        store: PinStore,
        *,
        inner_transport: Optional[httpx.AsyncBaseTransport] = None,
        peer_cert_extractor: Optional[Callable[[httpx.Response], Optional[bytes]]] = None,
        require_pin: bool = True,
    ):
        self._store = store
        self._inner = inner_transport or httpx.AsyncHTTPTransport()
        self._extractor = peer_cert_extractor or _default_peer_cert_extractor
        self._require_pin = require_pin

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        hostname = request.url.host

        try:
            peer_cert = self._extractor(response)
        except Exception as exc:
            # Extractor itself crashed. Treat as fail-closed when
            # the hostname is pinned; otherwise re-raise so the
            # caller can see the underlying error.
            if self._store.is_pinned(hostname):
                raise PinVerificationError(
                    hostname=hostname,
                    presented_spki="<extractor-error>",
                    expected=[
                        p.spki_sha256 for p in self._store.pins_for(hostname)
                    ],
                ) from exc
            raise

        if peer_cert is None:
            # No cert (HTTP, or extractor saw no SSL object). Fail
            # closed when the hostname is pinned and require_pin
            # is set; otherwise pass through.
            if self._require_pin and self._store.is_pinned(hostname):
                raise PinVerificationError(
                    hostname=hostname,
                    presented_spki="<no-cert>",
                    expected=[
                        p.spki_sha256 for p in self._store.pins_for(hostname)
                    ],
                )
            return response

        # Live cert: delegate to the verification helper. Raises
        # PinVerificationError on mismatch or on missing pin
        # under require_pin=True.
        verify_pin(
            peer_cert,
            hostname,
            self._store,
            require_pin=self._require_pin,
        )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
