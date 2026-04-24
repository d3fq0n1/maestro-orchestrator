"""
Bundle catalog — indexed view over manifest files.

The catalog's job is cheap query: given a task description, produce a short
list of candidate manifests for the LibrarianAgent prompt. Two reasons we
don't just hand the model every manifest every time:

  1. Cost — the corpus grows; we want the model's context to stay small
     regardless of catalog size.
  2. Leverage — a deterministic tag prefilter catches obvious matches and
     mismatches without a model call. The model then picks from the
     shortlist, where its judgement actually adds value.

The prefilter is intentionally permissive: it narrows the catalog when a
clear tag match exists and otherwise returns everything. False negatives
(bundles wrongly dropped before the model sees them) are worse than false
positives (model sees a few extra candidates).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .manifest import (
    Manifest,
    DEFAULT_MANIFEST_DIR,
    DEFAULT_SKILLS_ROOT,
    _CAPABILITY_PATTERNS,
    generate_catalog_manifests,
    load_manifest,
)


# --- Task → tag extraction ---------------------------------------------

def extract_task_tags(task_description: str) -> dict[str, list[str]]:
    """Derive capability tags from a task description.

    Uses the same keyword patterns as manifest capability extraction so
    task tags and manifest tags are directly comparable.
    """
    haystack = (task_description or "").lower()
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


# --- Query shape --------------------------------------------------------

@dataclass
class CatalogQuery:
    """A structured query into the catalog.

    ``tags`` is a {axis: [tag, ...]} dict. A manifest matches if, for any
    axis present in the query, at least one manifest tag on that axis
    appears in the query tags. Axes absent from the query don't constrain.

    ``text`` is the raw task text — kept around so the tag extractor can
    run if ``tags`` is empty, and so downstream logging can record what
    the librarian was asked about.
    """

    text: str = ""
    tags: dict = field(default_factory=dict)
    max_candidates: int = 12

    @classmethod
    def from_text(cls, task_description: str, max_candidates: int = 12) -> "CatalogQuery":
        return cls(
            text=task_description,
            tags=extract_task_tags(task_description),
            max_candidates=max_candidates,
        )


# --- Catalog ------------------------------------------------------------

class Catalog:
    """Loaded, indexed view over the manifest cache.

    Construction is explicit:
        * ``Catalog.from_manifests([...])`` — in-memory only
        * ``Catalog.from_disk()``           — reads the manifest cache
        * ``Catalog.from_skills_root()``    — builds manifests live
                                              (without writing to cache)
    """

    def __init__(self, manifests: Iterable[Manifest]):
        self._manifests: list[Manifest] = list(manifests)
        self._by_id: dict[str, Manifest] = {m.bundle_id: m for m in self._manifests}
        self._tag_index: dict[str, dict[str, set]] = self._build_tag_index(self._manifests)

    # --- constructors ---

    @classmethod
    def from_manifests(cls, manifests: Iterable[Manifest]) -> "Catalog":
        return cls(manifests)

    @classmethod
    def from_disk(cls, manifest_dir: Path = None) -> "Catalog":
        """Load the cached manifests from disk. Caller is responsible for
        calling ``manifest.regenerate()`` beforehand if the corpus changed.
        """
        target_dir = Path(manifest_dir) if manifest_dir else DEFAULT_MANIFEST_DIR
        if not target_dir.is_dir():
            return cls([])
        manifests: list[Manifest] = []
        for path in sorted(target_dir.glob("*.json")):
            try:
                manifests.append(load_manifest(path.stem, target_dir))
            except (FileNotFoundError, ValueError):
                continue
        return cls(manifests)

    @classmethod
    def from_skills_root(cls, skills_root: Path = None) -> "Catalog":
        """Build manifests live from a skills root (no disk write)."""
        root = Path(skills_root) if skills_root else DEFAULT_SKILLS_ROOT
        return cls(generate_catalog_manifests(root))

    # --- accessors ---

    def __len__(self) -> int:
        return len(self._manifests)

    def __iter__(self):
        return iter(self._manifests)

    def all(self) -> list[Manifest]:
        return list(self._manifests)

    def get(self, bundle_id: str) -> Optional[Manifest]:
        return self._by_id.get(bundle_id)

    def ids(self) -> list[str]:
        return list(self._by_id.keys())

    # --- tag index ---

    @staticmethod
    def _build_tag_index(manifests: list[Manifest]) -> dict[str, dict[str, set]]:
        """{axis: {tag: {bundle_id, ...}}}."""
        index: dict[str, dict[str, set]] = {}
        for m in manifests:
            for axis, tags in (m.capabilities or {}).items():
                axis_map = index.setdefault(axis, {})
                for tag in tags:
                    axis_map.setdefault(tag, set()).add(m.bundle_id)
        return index

    # --- prefilter ---

    def prefilter(self, query: CatalogQuery) -> list[Manifest]:
        """Return a narrowed candidate set for the query.

        Semantics:
          * For each axis present in the query, collect the union of
            bundle_ids whose manifest lists at least one of those tags
            on the same axis.
          * A bundle qualifies if it matches on *any* axis. (Permissive —
            prefers false positives.)
          * Missing tag index for an axis => no filter on that axis.
          * Empty query tags => return everything, capped.
          * Always capped at ``query.max_candidates`` by a deterministic
            ranking: tag-match count (desc) then name (asc).
        """
        if not query.tags:
            return self._cap(self._manifests, query.max_candidates)

        candidates: set[str] = set()
        for axis, tag_list in query.tags.items():
            axis_map = self._tag_index.get(axis, {})
            for tag in tag_list:
                candidates.update(axis_map.get(tag, set()))

        if not candidates:
            # No tag hits — fall back to the full catalog so the model can
            # still reason over abstracts. Cap applied.
            return self._cap(self._manifests, query.max_candidates)

        filtered = [self._by_id[bid] for bid in candidates if bid in self._by_id]
        ranked = sorted(
            filtered,
            key=lambda m: (-self._match_score(m, query), m.name),
        )
        return self._cap(ranked, query.max_candidates)

    def _match_score(self, manifest: Manifest, query: CatalogQuery) -> int:
        """Count how many query tags a manifest matches across all axes."""
        score = 0
        for axis, tag_list in query.tags.items():
            manifest_tags = set((manifest.capabilities or {}).get(axis, []))
            score += sum(1 for t in tag_list if t in manifest_tags)
        return score

    @staticmethod
    def _cap(manifests: list[Manifest], limit: int) -> list[Manifest]:
        if limit <= 0:
            return list(manifests)
        return list(manifests)[:limit]

    # --- catalog snapshot for R2 ledger ---

    def snapshot_hash(self) -> str:
        """Stable hash over the set of bundle_ids currently in the catalog.

        Used by R2 metadata as ``manifest_snapshot`` — two librarian
        sessions with the same snapshot hash saw the same catalog.
        """
        import hashlib
        joined = "\n".join(sorted(self._by_id.keys()))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
