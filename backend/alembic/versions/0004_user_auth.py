"""user: taula d'autenticació

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-08
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TYPE core.user_plan AS ENUM ('free', 'starter', 'professional', 'enterprise');
        CREATE TABLE core."user" (
            id          SERIAL PRIMARY KEY,
            email       VARCHAR NOT NULL,
            hashed_password VARCHAR NOT NULL,
            plan        core.user_plan NOT NULL DEFAULT 'free',
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_email UNIQUE (email)
        );
        CREATE INDEX ix_core_user_email ON core."user" (email);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_core_user_email;
        DROP TABLE IF EXISTS core."user";
        DROP TYPE IF EXISTS core.user_plan;
    """)
