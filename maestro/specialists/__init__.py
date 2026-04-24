"""Role-specialised Maestro agents that go beyond the general-purpose council.

Specialists are ordinary ``Agent`` subclasses (see ``maestro.agents.base``)
wrapped with a narrow, structured contract for a single responsibility. Each
specialist owns its own prompt shape and output parser, and publishes a
strongly-typed result alongside the raw string ``fetch`` contract.
"""

from .librarian import (
    LibrarianAgent,
    LibrarianSelection,
    LibrarianSessionResult,
    run_librarian_session,
    default_librarian_council,
)
