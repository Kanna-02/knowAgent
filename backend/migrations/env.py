from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from knowagent.agent.infrastructure import sqlalchemy_models as agent_models
from knowagent.documents.infrastructure import sqlalchemy_models as document_models
from knowagent.identity.infrastructure.sqlalchemy_models import Base
from knowagent.knowledge.infrastructure import sqlalchemy_models as knowledge_models
from knowagent.notifications.infrastructure import sqlalchemy_models as notification_models
from knowagent.platform import outbox as platform_outbox
from knowagent.platform.settings import Settings
from knowagent.systems.infrastructure import sqlalchemy_models as systems_models
from knowagent.tickets.infrastructure import sqlalchemy_models as ticket_models

del (
    agent_models,
    document_models,
    knowledge_models,
    notification_models,
    platform_outbox,
    systems_models,
    ticket_models,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", Settings.from_environment().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
