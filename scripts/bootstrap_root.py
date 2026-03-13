import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.core.db import SessionFactory, engine
from app.models import Base
from app.models.site import Site
from app.models.user import User
from app.models.user_site_role import UserSiteRole


ROOT_USER_ID = 1
ROOT_USERNAME = "root"

ROOT_SITE_CODE = "ROOT"
ROOT_SITE_NAME = "Root Site"


async def bootstrap() -> None:
    print("Creating tables...")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionFactory() as session:
        # ---- ensure root site exists ----
        result = await session.execute(
            select(Site).where(Site.code == ROOT_SITE_CODE)
        )
        root_site = result.scalar_one_or_none()

        if root_site is None:
            print("Creating root site")
            root_site = Site(
                id=uuid4(),
                code=ROOT_SITE_CODE,
                name=ROOT_SITE_NAME,
                is_active=True,
            )
            session.add(root_site)
            await session.flush()
        else:
            print("Root site already exists")

        # ---- ensure root user exists ----
        result = await session.execute(
            select(User).where(User.id == ROOT_USER_ID)
        )
        user = result.scalar_one_or_none()

        if user is None:
            print("Creating root user")
            user = User(
                id=ROOT_USER_ID,
                username=ROOT_USERNAME,
                email="root@local",
                full_name="System Root",
                is_active=True,
            )
            session.add(user)
            await session.flush()
        else:
            print("Root user already exists")

        # ---- ensure root access exists ----
        result = await session.execute(
            select(UserSiteRole).where(
                UserSiteRole.user_id == ROOT_USER_ID,
                UserSiteRole.site_id == root_site.id,
            )
        )
        root_access = result.scalar_one_or_none()

        if root_access is None:
            print("Creating root access")
            root_access = UserSiteRole(
                user_id=ROOT_USER_ID,
                site_id=root_site.id,
                role="root",
                is_active=True,
            )
            session.add(root_access)
            await session.flush()
        else:
            print("Root access already exists")
            if root_access.role != "root":
                root_access.role = "root"
            if not root_access.is_active:
                root_access.is_active = True
            await session.flush()

        await session.commit()

    print("Bootstrap complete")
    print(f"Root user id: {ROOT_USER_ID}")
    print(f"Root site id: {root_site.id}")


if __name__ == "__main__":
    asyncio.run(bootstrap())