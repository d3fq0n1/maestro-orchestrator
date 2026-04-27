"""
Whirlpool adapter factory — turns a policy into adapters.

See docs/architecture/whirlpool.md.

The factory exists so ``IngestPolicy`` (in ``types.py``) stays a
pure dataclass without runtime imports of adapter implementations.
This module is the single place that knows the mapping between
policy slots and adapter classes; adding a new adapter type
involves a new slot on ``IngestPolicy`` and a new branch here.

The split mirrors the pattern elsewhere in Maestro of separating
data from construction.
"""

from __future__ import annotations

from typing import List

from maestro.whirlpool.adapter import IngestAdapter
from maestro.whirlpool.ingest import HttpRssAdapter
from maestro.whirlpool.types import IngestPolicy


def build_adapters(policy: IngestPolicy) -> List[IngestAdapter]:
    """Construct the adapters declared by ``policy``.

    Walks every typed adapter slot on ``policy`` and instantiates
    one adapter per config entry. The returned adapters are
    bound to the policy's ``whirlpool_id``.

    Returns an empty list when no slots are populated. The
    Whirlpool then runs without any adapters (zero items per
    cycle); ``NullIngestAdapter`` may be added explicitly by the
    caller for tests.

    Adding a new adapter type:
      1. Add a typed slot on ``IngestPolicy`` (e.g.,
         ``slack: list = field(default_factory=list)``).
      2. Add the corresponding branch below to instantiate one
         adapter per config in that slot.
    """
    adapters: list = []
    for cfg in policy.http_rss:
        adapters.append(
            HttpRssAdapter(
                config=cfg,
                whirlpool_id=policy.whirlpool_id,
            )
        )
    return adapters
