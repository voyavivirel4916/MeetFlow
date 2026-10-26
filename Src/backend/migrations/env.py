from alembic import context
from app.db.models import metadata

# Connection belongs to the explicit migration command or an isolated test.
connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('Run python -m app.db.migrate; a managed connection is required.')
context.configure(connection=connection, target_metadata=metadata, compare_type=True,
                  compare_server_default=True, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
