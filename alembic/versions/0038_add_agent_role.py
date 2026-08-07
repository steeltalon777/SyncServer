"""0038_add_agent_role: fifth domain role 'agent'

ADR-0030, TZ-AGENT-ROLE-SYNCSERVER rev.2 §3.2.

Adds the trusted-LLM domain role ``agent`` to ``users.role`` check
constraint (ADR-0030). No column change and no data rewrite:

- upgrade drops ``ck_users_role`` and recreates it with ``agent``;
- existing rows are never touched.

Downgrade refuses to silently turn agent-users into observer: it checks
for ``users.role = 'agent'`` rows and fails with an explicit operator
instruction if any exist. Only when no agent rows remain does it restore
the four-role constraint, so rollback never changes domain identity
silently.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0038_add_agent_role"
down_revision = "0037_audit_item_effects_effective_at"
branch_labels = None
depends_on = None


_FOUR_ROLE_CONSTRAINT = "role IN ('root', 'chief_storekeeper', 'storekeeper', 'observer')"
_FIVE_ROLE_CONSTRAINT = "role IN ('root', 'chief_storekeeper', 'storekeeper', 'observer', 'agent')"


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _FIVE_ROLE_CONSTRAINT)


def downgrade() -> None:
    conn = op.get_bind()
    agent_rows = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE role = 'agent'")
    ).scalar()
    if agent_rows:
        raise RuntimeError(
            f"Refusing to downgrade ck_users_role: {agent_rows} user(s) still have "
            "role='agent'. Reassign those users to a four-role value (for example "
            "'observer' or 'storekeeper') first, then retry the downgrade. "
            "Silent role conversion of agent-users is forbidden (ADR-0030, "
            "TZ-AGENT-ROLE-SYNCSERVER rev.2 §3.2)."
        )
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", _FOUR_ROLE_CONSTRAINT)
