# Anthropic Skills Corpus

This directory stages a real SKILL.md corpus for the Maestro LibrarianAgent.
Contents are a snapshot of https://github.com/anthropics/skills (Apache 2.0)
limited to each skill's `SKILL.md` and `LICENSE.txt`. Binary assets (fonts,
templates, examples) and auxiliary reference files are intentionally excluded
— the Librarian only needs to read SKILL.md front matter and prose to build
manifests. When a bundle is selected, downstream callers can resolve the
bundle path to the full upstream directory if needed.

Provenance: https://github.com/anthropics/skills (upstream commit captured at
import time; not version-pinned here).

Each skill preserves its Apache 2.0 LICENSE.txt verbatim. Skill content is
not modified. See `THIRD_PARTY_NOTICES.md` in the upstream repo for the
complete attribution list.

Regenerate manifests (and re-hash) after any SKILL.md change via
`python -m maestro.bundles.manifest --regenerate`.
