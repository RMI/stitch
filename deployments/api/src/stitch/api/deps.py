from typing import Annotated

from fastapi import Depends

from stitch.api.entities import User


def get_current_user() -> User:
    """Placeholder user dependency. Replace with real auth in production."""
    return User(id=2, role="admin", email="dev@example.com", name="Dev")


CurrentUser = Annotated[User, Depends(get_current_user)]
