from fastapi import APIRouter

from stitch.api.auth import Claims, CurrentUser
from stitch.api.entities import AuthMeView, TokenClaimsView

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeView)
async def get_auth_me(
    *,
    claims: Claims,
    user: CurrentUser,
) -> AuthMeView:
    return AuthMeView(
        user=user,
        claims=TokenClaimsView(
            sub=claims.sub,
            email=claims.email,
            name=claims.name,
            permissions=sorted(claims.permissions),
            raw=claims.raw,
        ),
    )
