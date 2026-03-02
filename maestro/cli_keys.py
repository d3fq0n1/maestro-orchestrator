#!/usr/bin/env python3
"""
Maestro Key Management CLI.

Usage:
    python -m maestro.cli_keys list
    python -m maestro.cli_keys set openai sk-abc123...
    python -m maestro.cli_keys remove google
    python -m maestro.cli_keys validate
    python -m maestro.cli_keys validate openai

Works with the same .env file used by the web server and agents.
"""

import argparse
import asyncio
import os
import sys

# Allow imports from the project root so the maestro package resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

from maestro.keyring import (
    PROVIDERS,
    list_keys,
    set_key,
    remove_key,
    validate_key,
    validate_all_keys,
    _default_env_path,
)


def _load_env():
    """Ensure .env is loaded before any key operations."""
    env_path = _default_env_path()
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=True)


def cmd_list(args):
    """Show the status of all provider API keys."""
    _load_env()
    statuses = list_keys()

    print(f"\n  {'Provider':<14} {'Status':<14} {'Key'}")
    print(f"  {'--------':<14} {'------':<14} {'---'}")
    for s in statuses:
        status_str = "configured" if s.configured else "missing"
        key_str = s.masked_value if s.configured else "-"
        print(f"  {s.label:<14} {status_str:<14} {key_str}")
    print()


def cmd_set(args):
    """Set a provider's API key."""
    _load_env()
    provider = args.provider.lower()
    if provider not in PROVIDERS:
        print(f"  Error: Unknown provider '{args.provider}'.")
        print(f"  Available: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)

    status = set_key(provider, args.key)
    print(f"\n  {status.label} key set: {status.masked_value}")
    print(f"  Saved to: {_default_env_path()}\n")


def cmd_remove(args):
    """Remove a provider's API key."""
    _load_env()
    provider = args.provider.lower()
    if provider not in PROVIDERS:
        print(f"  Error: Unknown provider '{args.provider}'.")
        sys.exit(1)

    status = remove_key(provider)
    print(f"\n  {status.label} key removed.\n")


def cmd_validate(args):
    """Validate one or all provider keys against their services."""
    _load_env()

    if args.provider:
        provider = args.provider.lower()
        if provider not in PROVIDERS:
            print(f"  Error: Unknown provider '{args.provider}'.")
            sys.exit(1)
        statuses = [asyncio.run(validate_key(provider))]
    else:
        statuses = asyncio.run(validate_all_keys())

    print(f"\n  {'Provider':<14} {'Status':<14} {'Result'}")
    print(f"  {'--------':<14} {'------':<14} {'------'}")
    for s in statuses:
        if not s.configured:
            result = "not configured"
        elif s.valid:
            result = "valid"
        elif s.valid is False:
            result = f"invalid ({s.error})"
        else:
            result = "unknown"
        status_str = "configured" if s.configured else "missing"
        print(f"  {s.label:<14} {status_str:<14} {result}")
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="maestro-keys",
        description="Maestro API Key Management",
    )
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="Show all configured API keys (masked).")

    # set
    p_set = sub.add_parser("set", help="Set a provider's API key.")
    p_set.add_argument("provider", help="Provider name (openai, anthropic, google, openrouter).")
    p_set.add_argument("key", help="The API key value.")

    # remove
    p_rm = sub.add_parser("remove", help="Remove a provider's API key.")
    p_rm.add_argument("provider", help="Provider name.")

    # validate
    p_val = sub.add_parser("validate", help="Validate API keys against their services.")
    p_val.add_argument("provider", nargs="?", default=None, help="Provider name (omit to validate all).")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "set": cmd_set,
        "remove": cmd_remove,
        "validate": cmd_validate,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
