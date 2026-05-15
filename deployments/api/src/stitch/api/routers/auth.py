from fastapi import APIRouter
from sqlalchemy import select

from stitch.api.auth import Claims
from stitch.api.db.config import UnitOfWorkDep
from stitch.api.db.model.user import User as UserModel
from stitch.api.entities import AuthMeView, TokenClaimsView
from stitch.api.entities import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=AuthMeView)
async def get_auth_me(
    *,
    claims: Claims,
    uow: UnitOfWorkDep,
) -> AuthMeView:
    user_model = (
        await uow.session.execute(select(UserModel).where(UserModel.sub == claims.sub))
    ).scalar_one_or_none()
    user = (
        None
        if user_model is None
        else User(
            id=user_model.id,
            sub=user_model.sub,
            email=user_model.email,
            name=user_model.name,
        )
    )
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
