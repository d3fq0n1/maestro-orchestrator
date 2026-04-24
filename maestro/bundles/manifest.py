"""
Bundle manifests — cheap, content-addressed descriptors over SKILL.md bundles.

A manifest is a small JSON record the librarian can scan without loading
the bundle body. Each manifest carries:

  * bundle_id    — sha256 over the canonical bundle form (SKILL.md bytes,
                   line-ending normalised, trailing whitespace stripped).
  * name         — from YAML front matter.
  * version      — semver; defaults to "0.0.0" when absent.
  * abstract     — short, sanitised natural-language summary (<=200 tokens).
  * capabilities — structured tags derived deterministically from the
                   bundle's name + description + body. Four axes:
                   language / framework / domain / task.
  * dependencies — other bundle_ids this bundle assumes are loaded. Stubbed
                   to [] for the initial corpus (populated later).
  * conflicts    — bundle_ids incompatible with this one. Stubbed to [].
  * path         — on-disk location of the bundle root.
  * signature    — detached signature stub (scheme TBD).

Parser note:
    Anthropic's SKILL.md corpus uses a restricted YAML front-matter subset
    (one-line string values, optional single/double quotes). We parse it by
    hand rather than pulling in a YAML dep — keeps the dep footprint small
    and fails loudly on anything we don't recognise.

Caching:
    Manifests are written to `data/bundles/manifests/<bundle_id>.json`.
    Regeneration is explicit (`regenerate()` / `__main__`), never automatic
    on query — per the task constraint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

from maestro.injection_guard import sanitize_untrusted_text


# --- Paths ---------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SKILLS_ROOT = _REPO_ROOT / "data" / "skills"
DEFAULT_MANIFEST_DIR = _REPO_ROOT / "data" / "bundles" / "manifests"


# --- Schema --------------------------------------------------------------

@dataclass
class Manifest:
    """Descriptor of a single knowledge bundle.

    Stable, serialisable, content-addressed. The librarian receives a list
    of these (or a projection of them) and picks a subset.
    """

    bundle_id: str
    name: str
    version: str
    abstract: str
    capabilities: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    path: str = ""
    signature: Optional[str] = None
    raw_description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        return cls(
            bundle_id=data["bundle_id"],
            name=data["name"],
            version=data.get("version", "0.0.0"),
            abstract=data.get("abstract", ""),
            capabilities=data.get("capabilities", {}),
            dependencies=data.get("dependencies", []),
            conflicts=data.get("conflicts", []),
            path=data.get("path", ""),
            signature=data.get("signature"),
            raw_description=data.get("raw_description", ""),
        )


# --- Canonicalisation + hashing -----------------------------------------

def _canonicalise_bundle_bytes(text: str) -> bytes:
    """Normalise SKILL.md text for stable content addressing.

    The same bundle must hash the same on every platform / checkout:
      * \r\n → \n
      * strip trailing whitespace from each line
      * strip trailing blank lines
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = "\n".join(line.rstrip() for line in normalised.split("\n"))
    stripped = stripped.rstrip("\n") + "\n"
    return stripped.encode("utf-8")


def compute_bundle_id(skill_md_path: Path) -> str:
    """sha256 over the canonical bundle bytes."""
    text = Path(skill_md_path).read_text(encoding="utf-8")
    return hashlib.sha256(_canonicalise_bundle_bytes(text)).hexdigest()


# --- Minimal front-matter parser ----------------------------------------

_FRONT_MATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Return (front_matter_dict, body_text).

    Supports one-line `key: value` entries with optional `'` or `"` quotes.
    Deliberately minimal — if the corpus grows past this shape we swap to
    a real YAML parser.
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text

    block = match.group(1)
    body = text[match.end():]

    result: dict = {}
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        result[key] = value
    return result, body


# --- Capability extraction ----------------------------------------------

# Deterministic keyword patterns. Match against lower-cased combined text
# of (name + description + body). Keep this readable and auditable — the
# librarian's tag prefilter depends on stable tagging.
_CAPABILITY_PATTERNS: dict[str, dict[str, tuple]] = {
    "language": {
        "python": (r"\bpython\b", r"\.py\b", r"\bpip\b", r"\bpython-"),
        "typescript": (r"\btypescript\b", r"\.ts\b", r"\bts-node\b"),
        "javascript": (r"\bjavascript\b", r"\bnode\.js\b", r"\.js\b"),
        "shell": (r"\bbash\b", r"\bshell\b", r"\bcurl\b"),
        "markdown": (r"\bmarkdown\b", r"\.md\b"),
        "html": (r"\bhtml\b", r"\.html\b"),
        "css": (r"\bcss\b", r"\.css\b"),
    },
    "framework": {
        "anthropic-sdk": (r"anthropic", r"@anthropic-ai/sdk", r"claude sdk"),
        "openai-sdk": (r"\bopenai\b",),
        "python-docx": (r"python-docx",),
        "openpyxl": (r"openpyxl",),
        "python-pptx": (r"python-pptx",),
        "pypdf": (r"\bpypdf\b", r"pdfplumber", r"reportlab"),
        "fastapi": (r"\bfastapi\b",),
        "mcp": (r"\bmcp\b", r"model context protocol"),
        "playwright": (r"\bplaywright\b",),
        "react": (r"\breact\b",),
    },
    "domain": {
        "api": (r"\bapi\b", r"\bsdk\b", r"rest\b"),
        "documents": (r"\bdocx\b", r"\bword document", r"\bdocument\b"),
        "spreadsheets": (r"\bxlsx\b", r"\bexcel\b", r"\bspreadsheet\b"),
        "presentations": (r"\bpptx\b", r"\bpowerpoint\b", r"\bslide deck\b"),
        "pdf": (r"\bpdf\b",),
        "visual-art": (r"\bposter\b", r"\bdesign\b", r"\bvisual art\b", r"\bcanvas\b"),
        "animation": (r"\bgif\b", r"\banimation\b"),
        "web": (r"\bwebapp\b", r"\bweb app\b", r"\bfrontend\b", r"\bbrowser\b"),
        "testing": (r"\btest(ing)?\b", r"\bqa\b"),
        "branding": (r"\bbrand\b", r"brand guidelines"),
        "communication": (r"\bslack\b", r"\binternal comms\b", r"\bemail\b"),
        "llm": (r"\bllm\b", r"large language model", r"\bclaude\b", r"\bgpt\b"),
    },
    "task": {
        "generate": (r"\bgenerate\b", r"\bcreate\b", r"\bauthor\b"),
        "edit": (r"\bedit\b", r"\bmodify\b", r"\bupdate\b"),
        "extract": (r"\bextract\b", r"\bparse\b", r"\bread\b"),
        "build": (r"\bbuild\b", r"\bcompile\b", r"\bserve\b"),
        "test": (r"\btest\b", r"\bverify\b", r"\bvalidate\b"),
        "design": (r"\bdesign\b", r"\btheme\b", r"\bstyle\b"),
        "debug": (r"\bdebug\b", r"\btroubleshoot\b"),
        "migrate": (r"\bmigrate\b", r"\bmigration\b"),
    },
}


def _extract_capabilities(name: str, description: str, body: str) -> dict:
    """Deterministic tag extraction. No model calls, no randomness."""
    haystack = f"{name}\n{description}\n{body}".lower()
    result: dict[str, list[str]] = {}
    for axis, tags in _CAPABILITY_PATTERNS.items():
        hits: list[str] = []
        for tag, patterns in tags.items():
            for pat in patterns:
                if re.search(pat, haystack):
                    hits.append(tag)
                    break
        if hits:
            result[axis] = sorted(set(hits))
    return result


# --- Abstract generation ------------------------------------------------

_ABSTRACT_TOKEN_CAP = 200
_CHARS_PER_TOKEN_APPROX = 4  # cheap heuristic; avoids pulling in a tokenizer


def _build_abstract(description: str, body: str) -> str:
    """Produce a short, sanitised abstract for the librarian prompt.

    Prefer the front-matter description (authored summary). Fall back to
    the first prose paragraph of the body. Cap at ~200 tokens.
    """
    candidate = description.strip() if description else ""
    if not candidate:
        for chunk in body.split("\n\n"):
            chunk = chunk.strip()
            if chunk and not chunk.startswith("#"):
                candidate = chunk
                break

    char_cap = _ABSTRACT_TOKEN_CAP * _CHARS_PER_TOKEN_APPROX
    if len(candidate) > char_cap:
        candidate = candidate[:char_cap].rsplit(" ", 1)[0] + "…"

    return sanitize_untrusted_text(candidate)


# --- Public API ---------------------------------------------------------

def generate_manifest(bundle_dir: Path) -> Manifest:
    """Build a manifest from one bundle directory containing SKILL.md.

    The bundle directory is the on-disk root; the SKILL.md inside it is
    the canonical hashable artifact.
    """
    bundle_dir = Path(bundle_dir)
    skill_md = bundle_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"No SKILL.md under {bundle_dir}")

    text = skill_md.read_text(encoding="utf-8")
    front, body = _parse_front_matter(text)

    name = front.get("name") or bundle_dir.name
    description = front.get("description", "")
    version = front.get("version", "0.0.0")

    bundle_id = compute_bundle_id(skill_md)
    capabilities = _extract_capabilities(name, description, body)
    abstract = _build_abstract(description, body)

    return Manifest(
        bundle_id=bundle_id,
        name=name,
        version=version,
        abstract=abstract,
        capabilities=capabilities,
        dependencies=[],
        conflicts=[],
        path=str(bundle_dir),
        signature=None,
        raw_description=description,
    )


def generate_catalog_manifests(skills_root: Path = None) -> list[Manifest]:
    """Walk a skills root and produce one Manifest per bundle directory."""
    root = Path(skills_root) if skills_root else DEFAULT_SKILLS_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"Skills root not found: {root}")

    manifests: list[Manifest] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "SKILL.md").is_file():
            continue
        manifests.append(generate_manifest(entry))
    return manifests


def save_manifest(manifest: Manifest, manifest_dir: Path = None) -> Path:
    """Persist a manifest to `<manifest_dir>/<bundle_id>.json`."""
    target_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{manifest.bundle_id}.json"
    target.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))
    return target


def load_manifest(bundle_id: str, manifest_dir: Path = None) -> Manifest:
    """Load a manifest by bundle_id. Raises FileNotFoundError if missing."""
    target_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
    target = target_dir / f"{bundle_id}.json"
    if not target.is_file():
        raise FileNotFoundError(f"Manifest not found: {bundle_id}")
    return Manifest.from_dict(json.loads(target.read_text()))


def regenerate(
    skills_root: Path = None,
    manifest_dir: Path = None,
    prune_stale: bool = True,
) -> list[Manifest]:
    """Rebuild the manifest cache from the current skills corpus.

    Explicit, not auto-triggered. When `prune_stale` is True, manifest
    files for bundle_ids no longer present in the corpus are deleted.
    """
    target_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    manifests = generate_catalog_manifests(skills_root)
    current_ids = {m.bundle_id for m in manifests}

    for m in manifests:
        save_manifest(m, target_dir)

    if prune_stale:
        for existing in target_dir.glob("*.json"):
            if existing.stem not in current_ids:
                existing.unlink()

    return manifests


def _main() -> None:
    ap = argparse.ArgumentParser(description="Regenerate the bundle manifest cache.")
    ap.add_argument("--skills-root", type=Path, default=None)
    ap.add_argument("--manifest-dir", type=Path, default=None)
    ap.add_argument("--no-prune", action="store_true", help="Keep manifests for removed bundles.")
    args = ap.parse_args()

    manifests = regenerate(
        skills_root=args.skills_root,
        manifest_dir=args.manifest_dir,
        prune_stale=not args.no_prune,
    )
    print(f"Generated {len(manifests)} manifest(s).")
    for m in manifests:
        tags = ", ".join(f"{k}={'/'.join(v)}" for k, v in m.capabilities.items()) or "-"
        print(f"  {m.name:28s} {m.bundle_id[:12]}  [{tags}]")


if __name__ == "__main__":
    _main()
