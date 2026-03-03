"""
Code Injection Engine — applies validated proposals to the running system.

Three injection modes:

  1. **Runtime** — mutate module-level variables in-process (thresholds,
     temperatures).  Takes effect on the next orchestration call with no
     file writes and no restart.

  2. **Source patch** — rewrite a value in a ``.py`` source file via AST
     transformation and ``importlib.reload()`` so the change persists
     across restarts.

  3. **Config overlay** — write to ``data/runtime_config.json`` which
     agents and the aggregator read at session start.

Every injection is paired with a rollback snapshot so it can be undone.
"""

import ast
import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.optimization import OptimizationProposal, ProposalBatch
from maestro.rollback import RollbackLog, RollbackEntry
from maestro.injection_guard import InjectionGuard, GuardConfig


_MAESTRO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class InjectionResult:
    """Outcome of a single injection attempt."""
    proposal_id: str
    applied: bool
    injection_type: str        # "runtime", "source_patch", "config", "skipped"
    rollback_id: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = ""


class CodeInjector:
    """
    Applies validated ``OptimizationProposal`` objects to the running
    Maestro system.

    Usage::

        injector = CodeInjector()
        result = injector.apply(proposal, cycle_id="cycle-123")

    The injector delegates safety checks to an :class:`InjectionGuard`
    and records every mutation in a :class:`RollbackLog`.
    """

    def __init__(
        self,
        guard: InjectionGuard = None,
        rollback_log: RollbackLog = None,
    ):
        self._guard = guard or InjectionGuard()
        self._rollback = rollback_log or RollbackLog()

    @property
    def guard(self) -> InjectionGuard:
        return self._guard

    @property
    def rollback_log(self) -> RollbackLog:
        return self._rollback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        proposal: OptimizationProposal,
        cycle_id: str = "manual",
        dry_run: bool = False,
    ) -> InjectionResult:
        """
        Apply a single proposal.

        When *dry_run* is True the proposal is validated through the
        guard but no mutation occurs.
        """
        # Guard checks
        allowed, reason = self._guard.is_injectable(proposal)
        if not allowed:
            return InjectionResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                injection_type="skipped",
                error=reason,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        if not self._guard.check_rate_limit():
            return InjectionResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                injection_type="skipped",
                error="Rate limit exceeded",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        if dry_run:
            injection_type = self._classify_injection(proposal)
            return InjectionResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                injection_type=injection_type,
                error="dry_run",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Dispatch to the appropriate injector
        injection_type = self._classify_injection(proposal)
        try:
            if injection_type == "runtime":
                rollback_entry = self._inject_runtime(proposal, cycle_id)
            elif injection_type == "source_patch":
                rollback_entry = self._inject_source(proposal, cycle_id)
            elif injection_type == "config":
                rollback_entry = self._inject_config(proposal, cycle_id)
            else:
                return InjectionResult(
                    proposal_id=proposal.proposal_id,
                    applied=False,
                    injection_type=injection_type,
                    error=f"Unknown injection type: {injection_type}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            return InjectionResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                injection_type=injection_type,
                error=str(exc),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        self._guard.record_injection()
        proposal.status = "promoted"

        return InjectionResult(
            proposal_id=proposal.proposal_id,
            applied=True,
            injection_type=injection_type,
            rollback_id=rollback_entry.rollback_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def apply_batch(
        self,
        proposals: list,
        cycle_id: str = "manual",
        dry_run: bool = False,
    ) -> list:
        """Apply a list of proposals, returning an InjectionResult per proposal."""
        return [self.apply(p, cycle_id=cycle_id, dry_run=dry_run) for p in proposals]

    def rollback(self, rollback_id: str) -> bool:
        """
        Undo a single injection by restoring the snapshotted state.

        Returns True on success, False if the entry was not found or
        was already rolled back.
        """
        entry = self._rollback.get(rollback_id)
        if entry is None or entry["status"] != "applied":
            return False

        try:
            if entry["injection_type"] == "runtime":
                self._rollback_runtime(entry)
            elif entry["injection_type"] == "source_patch":
                self._rollback_source(entry)
            elif entry["injection_type"] == "config":
                self._rollback_config(entry)
        except Exception:
            return False

        self._rollback.mark_rolled_back(rollback_id)
        return True

    def rollback_cycle(self, cycle_id: str) -> list:
        """
        Roll back every active injection from a given improvement cycle.
        Returns list of (rollback_id, success) tuples.
        """
        entries = self._rollback.get_active_by_cycle(cycle_id)
        results = []
        for entry in entries:
            success = self.rollback(entry["rollback_id"])
            results.append((entry["rollback_id"], success))
        return results

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_injection(self, proposal: OptimizationProposal) -> str:
        """Decide which injection path to use for a proposal."""
        if proposal.change_type == "parameter_update":
            return "runtime"
        if proposal.change_type in ("code_patch", "architecture_refactor"):
            return "source_patch"
        if proposal.change_type == "config_change":
            return "config"
        if proposal.change_type == "prompt_rewrite":
            return "config"
        return "runtime"

    # ------------------------------------------------------------------
    # Runtime injection
    # ------------------------------------------------------------------

    def _inject_runtime(
        self, proposal: OptimizationProposal, cycle_id: str,
    ) -> RollbackEntry:
        """Mutate a module-level variable in the running process."""
        mod = self._import_module(proposal.module_name)
        original = str(getattr(mod, proposal.target_name))

        new_value = self._coerce_value(proposal.proposed_value, original)
        setattr(mod, proposal.target_name, new_value)

        return self._rollback.snapshot_runtime(
            proposal_id=proposal.proposal_id,
            cycle_id=cycle_id,
            module_name=proposal.module_name,
            target_name=proposal.target_name,
            original_value=original,
            new_value=str(new_value),
        )

    def _rollback_runtime(self, entry: dict):
        mod = self._import_module(entry["module_name"])
        restored = self._coerce_value(entry["original_value"], entry["new_value"])
        setattr(mod, entry["target_name"], restored)

    # ------------------------------------------------------------------
    # Source-level injection (AST rewrite)
    # ------------------------------------------------------------------

    def _inject_source(
        self, proposal: OptimizationProposal, cycle_id: str,
    ) -> RollbackEntry:
        """Rewrite a value in a .py file via AST and reload the module."""
        file_path = self._resolve_file(proposal.file_path)
        source = file_path.read_text()

        tree = ast.parse(source, filename=str(file_path))
        modified = self._ast_replace_value(
            tree, proposal.target_name, proposal.proposed_value,
        )
        new_source = ast.unparse(modified)

        rollback_entry = self._rollback.snapshot_source(
            proposal_id=proposal.proposal_id,
            cycle_id=cycle_id,
            module_name=proposal.module_name,
            target_name=proposal.target_name,
            file_path=str(file_path),
            original_value=proposal.current_value,
            new_value=proposal.proposed_value,
        )

        file_path.write_text(new_source)

        # Reload so the running process picks up the change
        mod = self._import_module(proposal.module_name)
        importlib.reload(mod)

        return rollback_entry

    def _rollback_source(self, entry: dict):
        """Restore a source file from its .bak backup."""
        backup = Path(entry["backup_path"])
        target = Path(entry["file_path"])
        if backup.exists():
            target.write_text(backup.read_text())
            mod = self._import_module(entry["module_name"])
            importlib.reload(mod)

    # ------------------------------------------------------------------
    # Config overlay injection
    # ------------------------------------------------------------------

    def _inject_config(
        self, proposal: OptimizationProposal, cycle_id: str,
    ) -> RollbackEntry:
        """Write a key to the runtime config overlay JSON."""
        import json
        config_path = _MAESTRO_ROOT / "data" / "runtime_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = {}
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
            except json.JSONDecodeError:
                config = {}

        original = str(config.get(proposal.target_name, ""))
        config[proposal.target_name] = proposal.proposed_value
        config_path.write_text(json.dumps(config, indent=2))

        return self._rollback.snapshot_config(
            proposal_id=proposal.proposal_id,
            cycle_id=cycle_id,
            module_name=proposal.module_name,
            target_name=proposal.target_name,
            original_value=original,
            new_value=proposal.proposed_value,
        )

    def _rollback_config(self, entry: dict):
        import json
        config_path = _MAESTRO_ROOT / "data" / "runtime_config.json"
        if not config_path.exists():
            return

        config = json.loads(config_path.read_text())
        if entry["original_value"]:
            config[entry["target_name"]] = entry["original_value"]
        else:
            config.pop(entry["target_name"], None)
        config_path.write_text(json.dumps(config, indent=2))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _import_module(module_name: str):
        """Import a module by dotted name, returning the module object."""
        if module_name in sys.modules:
            return sys.modules[module_name]
        return importlib.import_module(module_name)

    @staticmethod
    def _coerce_value(new_str: str, reference_str: str):
        """Attempt to cast *new_str* to the same type as *reference_str*."""
        try:
            float(reference_str)
            return float(new_str)
        except (ValueError, TypeError):
            pass
        return new_str

    @staticmethod
    def _resolve_file(rel_path: str) -> Path:
        """Resolve a proposal file_path (relative to repo root) to absolute."""
        candidate = _MAESTRO_ROOT / rel_path
        if candidate.exists():
            return candidate
        # Try relative to maestro package
        candidate2 = _MAESTRO_ROOT / "maestro" / rel_path
        if candidate2.exists():
            return candidate2
        return candidate  # return first guess for error reporting

    @staticmethod
    def _ast_replace_value(
        tree: ast.Module, target_name: str, new_value_str: str,
    ) -> ast.Module:
        """
        Walk the AST and replace the first assignment to *target_name*
        with *new_value_str*.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == target_name:
                        try:
                            new_val = float(new_value_str)
                            node.value = ast.Constant(value=new_val)
                        except (ValueError, TypeError):
                            node.value = ast.Constant(value=new_value_str)
                        return tree
        return tree
