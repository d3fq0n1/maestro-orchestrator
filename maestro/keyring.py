"""
Keyring — Centralized API key management for Maestro.

Provides a single interface for reading, writing, masking, and validating
API keys. Used by both the CLI and the web API to ensure consistent
behavior across all entry points.

Keys are persisted in a `.env` file and also reflected into `os.environ`
so that running agents pick up changes immediately without a restart.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx


# Canonical provider definitions — single source of truth for key names,
# env vars, and display labels.
PROVIDERS = {
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "label": "OpenAI",
        "prefix": "sk-",
        "test_url": "https://api.openai.com/v1/models",
        "signup_url": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "label": "Anthropic",
        "prefix": "sk-ant-",
        "test_url": "https://api.anthropic.com/v1/models",
        "signup_url": "https://console.anthropic.com/settings/keys",
    },
    "google": {
        "env_var": "GOOGLE_API_KEY",
        "label": "Google",
        "prefix": "AI",
        "test_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "signup_url": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "label": "OpenRouter",
        "prefix": "sk-or-",
        "test_url": "https://openrouter.ai/api/v1/models",
        "signup_url": "https://openrouter.ai/keys",
    },
}


# Values treated as "not configured" (template placeholders, etc.)
_PLACEHOLDER_VALUES = frozenset({
    "", "sk-...", "...",
    "your-openai-key-here", "your-anthropic-key-here",
    "your-google-api-key-here", "your-openrouter-key-here",
})


@dataclass
class KeyStatus:
    """Status of a single API key."""
    provider: str
    label: str
    env_var: str
    configured: bool
    masked_value: str
    signup_url: str = ""
    valid: bool | None = None  # None = not tested yet
    error: str | None = None


def _default_env_path() -> Path:
    """Resolve the `.env` file that dotenv loaded (or would load)."""
    # In the Docker container the working directory is /app/backend,
    # and `orchestrator_foundry.py` loads `.env` from that directory.
    candidates = [
        Path(os.environ.get("MAESTRO_ENV_FILE", "")).resolve(),
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / "backend" / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for p in candidates:
        if p.is_file():
            return p
    # Fall back to the backend location (will be created on first write).
    return Path(__file__).resolve().parent.parent / "backend" / ".env"


def mask_key(key: str) -> str:
    """Return a masked version of a key showing only the first 4 and last 4 chars."""
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "*" * (len(key) - 2)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def get_key(provider: str) -> str | None:
    """Read the current value of a provider's API key from the environment."""
    info = PROVIDERS.get(provider)
    if not info:
        return None
    return os.environ.get(info["env_var"]) or None


def list_keys() -> list[KeyStatus]:
    """Return the status of every known provider key."""
    statuses = []
    for provider, info in PROVIDERS.items():
        raw = os.environ.get(info["env_var"]) or ""
        configured = bool(raw) and raw not in _PLACEHOLDER_VALUES
        statuses.append(KeyStatus(
            provider=provider,
            label=info["label"],
            env_var=info["env_var"],
            configured=configured,
            masked_value=mask_key(raw) if configured else "",
            signup_url=info.get("signup_url", ""),
        ))
    return statuses


def set_key(provider: str, value: str, env_path: Path | None = None) -> KeyStatus:
    """Set a provider's API key in both memory and the `.env` file.

    Returns the updated KeyStatus for the provider.
    """
    info = PROVIDERS.get(provider)
    if not info:
        raise ValueError(f"Unknown provider: {provider}")

    env_var = info["env_var"]
    value = value.strip()

    # Update the live process environment immediately
    os.environ[env_var] = value

    # Persist to .env
    path = env_path or _default_env_path()
    _upsert_env_file(path, env_var, value)

    return KeyStatus(
        provider=provider,
        label=info["label"],
        env_var=env_var,
        configured=True,
        masked_value=mask_key(value),
    )


def remove_key(provider: str, env_path: Path | None = None) -> KeyStatus:
    """Remove a provider's API key from memory and the `.env` file."""
    info = PROVIDERS.get(provider)
    if not info:
        raise ValueError(f"Unknown provider: {provider}")

    env_var = info["env_var"]
    os.environ.pop(env_var, None)

    path = env_path or _default_env_path()
    _remove_from_env_file(path, env_var)

    return KeyStatus(
        provider=provider,
        label=info["label"],
        env_var=env_var,
        configured=False,
        masked_value="",
    )


async def validate_key(provider: str) -> KeyStatus:
    """Test a single provider's API key by hitting a lightweight endpoint.

    Returns a KeyStatus with `valid` set to True/False and `error` on failure.
    """
    info = PROVIDERS.get(provider)
    if not info:
        raise ValueError(f"Unknown provider: {provider}")

    raw = os.environ.get(info["env_var"]) or ""
    configured = bool(raw) and raw not in _PLACEHOLDER_VALUES
    status = KeyStatus(
        provider=provider,
        label=info["label"],
        env_var=info["env_var"],
        configured=configured,
        masked_value=mask_key(raw) if configured else "",
    )

    if not configured:
        status.valid = False
        status.error = "Key not configured"
        return status

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if provider == "openai":
                res = await client.get(
                    info["test_url"],
                    headers={"Authorization": f"Bearer {raw}"},
                )
            elif provider == "anthropic":
                res = await client.get(
                    info["test_url"],
                    headers={
                        "x-api-key": raw,
                        "anthropic-version": "2023-06-01",
                    },
                )
            elif provider == "google":
                res = await client.get(
                    f"{info['test_url']}?key={raw}",
                )
            elif provider == "openrouter":
                res = await client.get(
                    info["test_url"],
                    headers={"Authorization": f"Bearer {raw}"},
                )
            else:
                status.valid = None
                status.error = "No validation method for this provider"
                return status

            if res.status_code in (200, 201):
                status.valid = True
            elif res.status_code == 401:
                status.valid = False
                status.error = "Invalid or expired key"
            elif res.status_code == 403:
                status.valid = False
                status.error = "Key lacks required permissions"
            else:
                status.valid = False
                status.error = f"HTTP {res.status_code}"
    except httpx.TimeoutException:
        status.valid = False
        status.error = "Connection timed out"
    except Exception as e:
        status.valid = False
        status.error = str(e)

    return status


async def validate_all_keys() -> list[KeyStatus]:
    """Validate every configured provider key in parallel."""
    import asyncio
    tasks = [validate_key(p) for p in PROVIDERS]
    return list(await asyncio.gather(*tasks))


# -- .env file helpers --

def _upsert_env_file(path: Path, key: str, value: str) -> None:
    """Insert or update a key=value pair in a .env file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False

    if path.exists():
        lines = path.read_text().splitlines(keepends=True)
        new_lines: list[str] = []
        for line in lines:
            if re.match(rf"^{re.escape(key)}\s*=", line):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        lines = new_lines

    if not found:
        # Ensure trailing newline before appending
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")

    path.write_text("".join(lines))


def _remove_from_env_file(path: Path, key: str) -> None:
    """Remove a key from a .env file."""
    if not path.exists():
        return
    lines = path.read_text().splitlines(keepends=True)
    new_lines = [l for l in lines if not re.match(rf"^{re.escape(key)}\s*=", l)]
    path.write_text("".join(new_lines))
