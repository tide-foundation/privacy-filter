"""Verified-identity seam. Tide authentication is deliberately not implemented yet."""
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class VerifiedOwner:
    owner_id: str

    def __post_init__(self):
        if not self.owner_id or len(self.owner_id) > 200:
            raise ValueError('A verified internal owner identifier is required.')


def require_owner(request: Request) -> VerifiedOwner:
    # No token parsing, unverified claim extraction, header-based impersonation,
    # demo identity or fallback to guest authorization. Raziel supplies this adapter.
    if request.headers.get('authorization'):
        raise HTTPException(401, 'Authentication could not be verified.', headers={'WWW-Authenticate': 'Bearer'})
    raise HTTPException(503, 'Secure history is not configured.')
