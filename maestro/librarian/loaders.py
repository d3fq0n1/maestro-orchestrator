"""
On-disk loaders for Policy and TrustList.

See docs/architecture/librarian.md §Threshold policy and
§Federation.

Trust list shape on disk (``trusted.json``)::

    {
      "keys": [
        {
          "key_id": "sha256:...",
          "public_key": "-----BEGIN PUBLIC KEY-----\\n...",
          "added_at": "2024-01-01T00:00:00+00:00",
          "added_by_operator_key": "sha256:..."
        },
        ...
      ],
      "operator_signature": "<base64 over canonicalized keys>"
    }

The ``operator_signature`` is an Ed25519 signature over the
canonical-form serialization of the keys array (sorted by
``key_id``, JSON-serialized with ``sort_keys=True``). It is
verified at load time against the operator public PEM stored in
``policy.json``.

Policy shape on disk (``policy.json``)::

    {
      "min_signatures_by_kind": {"statute_text": 2, ...},
      "review_external_imports": false,
      "import_caps_by_key": {...},
      "canonical_form_registry": ["bytes/raw", ...],
      "operator_key_fingerprint": "sha256:...",
      "operator_key_pem": "-----BEGIN PUBLIC KEY-----\\n..."
    }

Day 1 caveat: ``policy.json`` itself is unsigned; an attacker
with simultaneous filesystem-write *and* operator-key compromise
can replace both the trust list and the operator PEM in
``policy.json`` and avoid detection. This is the residual risk
documented in vortex-threat-model.md §C-3. A future hardening
step (out of scope here) would put the operator PEM on a
tamper-evident medium — code-baked, env var, hardware token.
"""

import base64
import json
from pathlib import Path

from maestro.librarian.crypto import (
    sign as _sign_bytes,
    verify,
)
from maestro.librarian.types import (
    Policy,
    TrustList,
    TrustedKey,
)


class TrustListVerificationError(Exception):
    """Raised when ``trusted.json``'s operator signature fails to
    verify, or when required fields are missing from the file or
    its companion ``policy.json``.
    """


# ---- Policy ----


def load_policy(path) -> Policy:
    """Load ``policy.json`` from ``path`` and return a Policy.

    Missing fields default to empty / falsy. ``operator_key_pem``
    is read into the Policy object via the dataclass's metadata
    dict for downstream consumers; the canonical Policy fields
    don't include it (the spec stores the fingerprint, not the
    PEM, in the dataclass).
    """
    data = json.loads(Path(path).read_text())
    return Policy(
        min_signatures_by_kind=data.get("min_signatures_by_kind", {}),
        review_external_imports=data.get("review_external_imports", False),
        import_caps_by_key=data.get("import_caps_by_key", {}),
        canonical_form_registry=data.get("canonical_form_registry", []),
        operator_key_fingerprint=data.get("operator_key_fingerprint", ""),
    )


def save_policy(
    policy: Policy,
    path,
    operator_key_pem: str = "",
) -> None:
    """Save ``policy`` to ``path`` as JSON.

    ``operator_key_pem`` (if provided) is embedded alongside the
    fingerprint and is read at trust-list load time to verify
    the operator signature.
    """
    data = {
        "min_signatures_by_kind": policy.min_signatures_by_kind,
        "review_external_imports": policy.review_external_imports,
        "import_caps_by_key": policy.import_caps_by_key,
        "canonical_form_registry": policy.canonical_form_registry,
        "operator_key_fingerprint": policy.operator_key_fingerprint,
        "operator_key_pem": operator_key_pem,
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))


def read_operator_pem(policy_path) -> str:
    """Read the operator PEM out of ``policy.json``.

    Separated from ``load_policy`` because the PEM is not a Policy
    dataclass field; it's a sibling field used only by the trust
    list loader.
    """
    data = json.loads(Path(policy_path).read_text())
    return data.get("operator_key_pem", "")


# ---- TrustList ----


def _canonicalize_trust_keys(keys: dict) -> bytes:
    """Deterministic byte form of the keys mapping.

    Sorted by ``key_id`` so order is independent of insertion;
    JSON-serialized with sort_keys + compact separators so two
    semantically equal trust lists produce the same bytes.
    """
    sorted_entries = [
        {
            "key_id": k.key_id,
            "public_key": k.public_key,
            "added_at": k.added_at,
            "added_by_operator_key": k.added_by_operator_key,
        }
        for _, k in sorted(keys.items())
    ]
    return json.dumps(
        sorted_entries,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_trust_list(path, policy_path) -> TrustList:
    """Load ``trusted.json`` and verify its operator signature.

    Reads the operator public PEM from ``policy.json`` (via
    ``read_operator_pem``). Verification failure raises
    ``TrustListVerificationError``.
    """
    operator_pem = read_operator_pem(policy_path)
    if not operator_pem:
        raise TrustListVerificationError(
            "policy.json has no operator_key_pem; "
            "cannot verify trusted.json"
        )

    data = json.loads(Path(path).read_text())
    operator_sig_b64 = data.get("operator_signature", "")
    if not operator_sig_b64:
        raise TrustListVerificationError(
            "trusted.json has no operator_signature"
        )
    keys_array = data.get("keys", [])

    keys: dict = {}
    for entry in keys_array:
        kid = entry["key_id"]
        keys[kid] = TrustedKey(
            key_id=kid,
            public_key=entry["public_key"],
            added_at=entry.get("added_at", ""),
            added_by_operator_key=entry.get("added_by_operator_key", ""),
        )
    canonical = _canonicalize_trust_keys(keys)

    try:
        sig_bytes = base64.b64decode(operator_sig_b64)
    except Exception:
        raise TrustListVerificationError(
            "trusted.json operator_signature is not valid base64"
        )

    if not verify(operator_pem.encode("utf-8"), canonical, sig_bytes):
        raise TrustListVerificationError(
            "trusted.json operator_signature does not verify"
        )

    return TrustList(keys=keys, operator_signature=operator_sig_b64)


def save_trust_list(
    trust_list: TrustList,
    path,
    operator_private_pem: bytes,
) -> None:
    """Save ``trust_list`` to ``path`` with a fresh operator
    signature over the canonicalized keys.

    The in-memory ``trust_list.operator_signature`` is updated to
    the newly-written value so callers can serialize and use the
    same object in-process without reloading.
    """
    canonical = _canonicalize_trust_keys(trust_list.keys)
    sig_bytes = _sign_bytes(operator_private_pem, canonical)
    operator_sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

    keys_array = [
        {
            "key_id": k.key_id,
            "public_key": k.public_key,
            "added_at": k.added_at,
            "added_by_operator_key": k.added_by_operator_key,
        }
        for _, k in sorted(trust_list.keys.items())
    ]
    data = {
        "keys": keys_array,
        "operator_signature": operator_sig_b64,
    }
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))
    trust_list.operator_signature = operator_sig_b64
