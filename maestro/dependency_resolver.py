"""
Dependency resolver and environment health checker for Maestro.

Checks Python packages, system tools, API key configuration, and runtime
readiness. Used by both the TUI and Web UI to surface actionable diagnostics
before orchestration fails.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass
class CheckResult:
    name: str
    category: str  # "python", "system", "api_key", "runtime"
    severity: Severity
    message: str
    hint: str = ""


# ---------------------------------------------------------------------------
# Required packages: (import_name, pip_name, required_by)
# ---------------------------------------------------------------------------

_REQUIRED_PACKAGES: list[tuple[str, str, str]] = [
    ("openai", "openai", "Sol / Aria agents (OpenAI provider)"),
    ("anthropic", "anthropic", "Prism agent (Anthropic provider)"),
    ("httpx", "httpx", "HTTP client for TUI / agent calls"),
    ("pydantic", "pydantic", "Request validation (FastAPI)"),
    ("dotenv", "python-dotenv", "Environment file loading"),
    ("fastapi", "fastapi", "Backend API server"),
    ("uvicorn", "uvicorn", "ASGI server"),
    ("rich", "rich", "TUI rich text rendering"),
    ("textual", "textual", "TUI framework"),
    ("safetensors", "safetensors", "Shard storage (SafeTensors format)"),
    ("huggingface_hub", "huggingface_hub", "Model downloading from HuggingFace"),
]

_OPTIONAL_PACKAGES: list[tuple[str, str, str]] = [
    ("numpy", "numpy", "NCG drift calculation (optional)"),
]

# ---------------------------------------------------------------------------
# System tools
# ---------------------------------------------------------------------------

_SYSTEM_TOOLS: list[tuple[str, str]] = [
    ("git", "System updates and version checking"),
    ("docker", "Docker deployment"),
]

# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

_API_KEYS: list[tuple[str, str, str]] = [
    ("OPENAI_API_KEY", "OpenAI", "Required for Sol, Aria, and headless NCG generation"),
    ("ANTHROPIC_API_KEY", "Anthropic", "Required for Prism agent"),
]

_OPTIONAL_API_KEYS: list[tuple[str, str, str]] = [
    ("HUGGINGFACE_TOKEN", "HuggingFace", "Optional; needed for gated model downloads"),
]


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_python_packages() -> list[CheckResult]:
    """Check that required Python packages are importable."""
    results: list[CheckResult] = []

    for import_name, pip_name, used_by in _REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "installed")
            results.append(CheckResult(
                name=pip_name,
                category="python",
                severity=Severity.OK,
                message=f"{pip_name} {version}",
            ))
        except ImportError:
            results.append(CheckResult(
                name=pip_name,
                category="python",
                severity=Severity.ERROR,
                message=f"{pip_name} is not installed",
                hint=f"pip install {pip_name}  (used by: {used_by})",
            ))

    for import_name, pip_name, used_by in _OPTIONAL_PACKAGES:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "installed")
            results.append(CheckResult(
                name=pip_name,
                category="python",
                severity=Severity.OK,
                message=f"{pip_name} {version}",
            ))
        except ImportError:
            results.append(CheckResult(
                name=pip_name,
                category="python",
                severity=Severity.WARN,
                message=f"{pip_name} is not installed (optional)",
                hint=f"pip install {pip_name}  ({used_by})",
            ))

    return results


def check_system_tools() -> list[CheckResult]:
    """Check that expected system tools are on PATH."""
    results: list[CheckResult] = []
    for tool, purpose in _SYSTEM_TOOLS:
        path = shutil.which(tool)
        if path:
            results.append(CheckResult(
                name=tool,
                category="system",
                severity=Severity.OK,
                message=f"{tool} found at {path}",
            ))
        else:
            results.append(CheckResult(
                name=tool,
                category="system",
                severity=Severity.WARN,
                message=f"{tool} not found on PATH",
                hint=f"Install {tool} for: {purpose}",
            ))
    return results


def check_api_keys() -> list[CheckResult]:
    """Check that API keys are configured in the environment."""
    results: list[CheckResult] = []

    for env_var, provider, purpose in _API_KEYS:
        value = os.environ.get(env_var, "").strip()
        if value:
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
            results.append(CheckResult(
                name=env_var,
                category="api_key",
                severity=Severity.OK,
                message=f"{provider} key configured ({masked})",
            ))
        else:
            results.append(CheckResult(
                name=env_var,
                category="api_key",
                severity=Severity.ERROR,
                message=f"{provider} key not set",
                hint=f"Set {env_var} in your .env file or environment. {purpose}.",
            ))

    for env_var, provider, purpose in _OPTIONAL_API_KEYS:
        value = os.environ.get(env_var, "").strip()
        if value:
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
            results.append(CheckResult(
                name=env_var,
                category="api_key",
                severity=Severity.OK,
                message=f"{provider} key configured ({masked})",
            ))
        else:
            results.append(CheckResult(
                name=env_var,
                category="api_key",
                severity=Severity.WARN,
                message=f"{provider} key not set (optional)",
                hint=f"{purpose}.",
            ))

    return results


def check_runtime() -> list[CheckResult]:
    """Check runtime environment readiness."""
    results: list[CheckResult] = []

    # Python version
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        results.append(CheckResult(
            name="python_version",
            category="runtime",
            severity=Severity.OK,
            message=f"Python {major}.{minor}.{sys.version_info[2]}",
        ))
    else:
        results.append(CheckResult(
            name="python_version",
            category="runtime",
            severity=Severity.ERROR,
            message=f"Python {major}.{minor} — requires 3.10+",
            hint="Upgrade Python to 3.10 or later.",
        ))

    # .env file presence
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    backend_env = os.path.join(project_root, "backend", ".env")
    root_env = os.path.join(project_root, ".env")
    env_path = os.environ.get("MAESTRO_ENV_FILE", "")

    if env_path and os.path.isfile(env_path):
        results.append(CheckResult(
            name="dotenv",
            category="runtime",
            severity=Severity.OK,
            message=f".env loaded from MAESTRO_ENV_FILE ({env_path})",
        ))
    elif os.path.isfile(backend_env):
        results.append(CheckResult(
            name="dotenv",
            category="runtime",
            severity=Severity.OK,
            message=f".env found at {backend_env}",
        ))
    elif os.path.isfile(root_env):
        results.append(CheckResult(
            name="dotenv",
            category="runtime",
            severity=Severity.OK,
            message=f".env found at {root_env}",
        ))
    else:
        results.append(CheckResult(
            name="dotenv",
            category="runtime",
            severity=Severity.WARN,
            message="No .env file found",
            hint="Create backend/.env with your API keys.",
        ))

    # Data directory
    data_dir = os.path.join(project_root, "data")
    if os.path.isdir(data_dir):
        results.append(CheckResult(
            name="data_dir",
            category="runtime",
            severity=Severity.OK,
            message=f"Data directory exists ({data_dir})",
        ))
    else:
        results.append(CheckResult(
            name="data_dir",
            category="runtime",
            severity=Severity.WARN,
            message="Data directory not found",
            hint=f"Create {data_dir} for session logs and shard storage.",
        ))

    return results


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

@dataclass
class DependencyReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def errors(self) -> list[CheckResult]:
        return [c for c in self.checks if c.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.severity == Severity.WARN]

    @property
    def ok_count(self) -> int:
        return sum(1 for c in self.checks if c.severity == Severity.OK)

    @property
    def healthy(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "total": len(self.checks),
            "ok": self.ok_count,
            "warnings": len(self.warnings),
            "errors": len(self.errors),
            "checks": [
                {
                    "name": c.name,
                    "category": c.category,
                    "severity": c.severity.value,
                    "message": c.message,
                    "hint": c.hint,
                }
                for c in self.checks
            ],
        }


def resolve_all() -> DependencyReport:
    """Run all dependency checks and return a unified report."""
    report = DependencyReport()
    report.checks.extend(check_runtime())
    report.checks.extend(check_python_packages())
    report.checks.extend(check_system_tools())
    report.checks.extend(check_api_keys())
    return report
