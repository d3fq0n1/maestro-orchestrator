"""
Manifest signature verification — count valid sigs, decide threshold.

See docs/architecture/librarian.md §Threshold policy.

Verification has three concerns:

* Hash integrity. ``content_hash`` must match the body bytes
  (under the manifest's ``canonical_form``); ``manifest_hash``
  must match the recomputed canonicalization of the manifest
  payload. If either fails, every signature is treated as invalid
  — a signature is only meaningful relative to the hashes it
  attests to.
* Per-signature validity. A signature is valid iff:
  - ``algo`` is ``"ed25519"``,
  - ``key_id`` resolves to a trusted key in the trust list,
  - ``sig`` decodes from base64,
  - ``crypto.verify`` succeeds against the trusted public PEM
    and the manifest_hash bytes.
* Threshold decision. The number of valid signatures must meet
  ``policy.min_signatures_by_kind[kind]`` (default 1).

The whole thing collapses into a single ``verify_manifest`` call
returning a structured ``VerificationResult`` (option V2 from the
step 4 design).
"""

import base64
from dataclasses import dataclass

from maestro.librarian.addressing import (
    compute_content_hash,
    compute_manifest_hash,
)
from maestro.librarian.crypto import verify
from maestro.librarian.types import (
    Manifest,
    Policy,
    Signature,
    TrustList,
)


_DEFAULT_MIN_SIGNATURES = 1


@dataclass(frozen=True)
class SignatureResult:
    """Per-signature verification outcome."""

    signature: Signature
    valid: bool
    reason: str = ""        # populated when ``valid`` is False


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of ``verify_manifest``.

    The signatures field is a tuple of per-signature results in the
    same order they appear on the manifest. The convenience
    properties report counts and partition the results.
    """

    signatures: tuple                   # tuple[SignatureResult, ...]
    threshold_required: int
    threshold_met: bool
    manifest_hash_ok: bool
    content_hash_ok: bool

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.signatures if r.valid)

    @property
    def valid_signatures(self) -> list:
        return [r.signature for r in self.signatures if r.valid]

    @property
    def invalid_signatures(self) -> list:
        """Returns ``list[(Signature, reason: str)]`` for invalid sigs."""
        return [(r.signature, r.reason) for r in self.signatures if not r.valid]


def _verify_one_sig(
    sig: Signature,
    manifest_hash: str,
    trust_list: TrustList,
) -> SignatureResult:
    """Verify a single signature against the trust list and the
    expected ``manifest_hash``.
    """
    if sig.algo != "ed25519":
        return SignatureResult(sig, False, f"unsupported algo: {sig.algo!r}")
    trusted = trust_list.keys.get(sig.key_id)
    if trusted is None:
        return SignatureResult(sig, False, "unknown signer")
    try:
        sig_bytes = base64.b64decode(sig.sig)
    except Exception:
        return SignatureResult(sig, False, "malformed base64 in sig")
    pub_pem = trusted.public_key.encode("utf-8")
    if not verify(pub_pem, manifest_hash.encode("utf-8"), sig_bytes):
        return SignatureResult(sig, False, "signature does not verify")
    return SignatureResult(sig, True)


def verify_manifest(
    manifest: Manifest,
    body: bytes,
    trust_list: TrustList,
    policy: Policy,
) -> VerificationResult:
    """Verify a manifest against a trust list and decide threshold.

    Returns a ``VerificationResult``. Does not raise: malformed
    inputs, mismatched hashes, and unknown signers all surface as
    invalid signatures with a populated ``reason``.

    Threshold lookup uses ``policy.min_signatures_by_kind`` keyed
    by ``manifest.kind.value`` (the string form). Default when no
    entry exists is 1.
    """
    threshold = policy.min_signatures_by_kind.get(
        manifest.kind.value, _DEFAULT_MIN_SIGNATURES,
    )

    # Hash integrity checks. Wrapped because canonicalize_body can
    # raise NotImplementedError for forms not yet wired up
    # (TEXT_UTF8_NFC, JSON_RFC8785) and ValueError for unknown forms.
    try:
        actual_content_hash = compute_content_hash(body, manifest.canonical_form)
        content_hash_ok = (manifest.content_hash == actual_content_hash)
    except (NotImplementedError, ValueError) as exc:
        content_hash_ok = False
        # Note: not propagating; the manifest is unverifiable, all
        # signatures are reported invalid below.
        del exc
    try:
        actual_manifest_hash = compute_manifest_hash(manifest)
        manifest_hash_ok = (manifest.manifest_hash == actual_manifest_hash)
    except Exception:
        manifest_hash_ok = False

    if not content_hash_ok or not manifest_hash_ok:
        reason = (
            "content_hash mismatch" if not content_hash_ok
            else "manifest_hash mismatch"
        )
        results = tuple(
            SignatureResult(s, False, reason)
            for s in manifest.signatures
        )
        return VerificationResult(
            signatures=results,
            threshold_required=threshold,
            threshold_met=False,
            manifest_hash_ok=manifest_hash_ok,
            content_hash_ok=content_hash_ok,
        )

    results = tuple(
        _verify_one_sig(s, manifest.manifest_hash, trust_list)
        for s in manifest.signatures
    )
    valid_count = sum(1 for r in results if r.valid)
    return VerificationResult(
        signatures=results,
        threshold_required=threshold,
        threshold_met=valid_count >= threshold,
        manifest_hash_ok=True,
        content_hash_ok=True,
    )
