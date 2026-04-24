"""Bundle catalog + manifest subsystem for the LibrarianAgent.

A "bundle" is a self-contained knowledge unit the librarian may select for a
downstream code agent to load. The initial corpus is Anthropic's SKILL.md
files. A manifest describes a bundle cheaply (capabilities, abstract, deps)
so the librarian can scan many bundles without reading bundle content.
"""

from .manifest import (
    Manifest,
    compute_bundle_id,
    generate_manifest,
    generate_catalog_manifests,
    load_manifest,
    save_manifest,
    regenerate,
    DEFAULT_SKILLS_ROOT,
    DEFAULT_MANIFEST_DIR,
)
from .catalog import Catalog, CatalogQuery
from .selection_drift import SelectionDriftTracker, SelectionDriftReport
