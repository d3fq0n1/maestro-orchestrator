"""
API Keys API — REST endpoints for managing provider API keys.

Provides list, set, remove, and validate operations. Keys are stored
in the `.env` file and reflected into the process environment so
running agents pick up changes without a restart.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maestro.keyring import (
    list_keys,
    set_key,
    remove_key,
    validate_key,
    validate_all_keys,
    PROVIDERS,
)

router = APIRouter(prefix="/api/keys", tags=["keys"])


class SetKeyRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=500)


# -- Endpoints --

@router.get("")
async def get_keys():
    """List all provider keys with masked values and configuration status."""
    statuses = list_keys()
    any_configured = any(s.configured for s in statuses)
    return {
        "keys": [
            {
                "provider": s.provider,
                "label": s.label,
                "env_var": s.env_var,
                "configured": s.configured,
                "masked_value": s.masked_value,
                "signup_url": s.signup_url,
            }
            for s in statuses
        ],
        "any_configured": any_configured,
    }


@router.put("/{provider}")
async def update_key(provider: str, body: SetKeyRequest):
    """Set or update a provider's API key."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    status = set_key(provider, body.value)
    return {
        "provider": status.provider,
        "label": status.label,
        "configured": status.configured,
        "masked_value": status.masked_value,
    }


@router.delete("/{provider}")
async def delete_key(provider: str):
    """Remove a provider's API key."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    status = remove_key(provider)
    return {
        "provider": status.provider,
        "label": status.label,
        "configured": status.configured,
    }


@router.post("/{provider}/validate")
async def validate_single_key(provider: str):
    """Test a single provider's API key against its service."""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    status = await validate_key(provider)
    return {
        "provider": status.provider,
        "label": status.label,
        "configured": status.configured,
        "masked_value": status.masked_value,
        "valid": status.valid,
        "error": status.error,
    }


@router.post("/validate")
async def validate_all():
    """Test all configured provider keys in parallel."""
    statuses = await validate_all_keys()
    return {
        "keys": [
            {
                "provider": s.provider,
                "label": s.label,
                "configured": s.configured,
                "masked_value": s.masked_value,
                "valid": s.valid,
                "error": s.error,
            }
            for s in statuses
        ],
    }
