"""Task editing, cancellation, optimistic versions and immutable creation input."""
import json
from alembic import op
import sqlalchemy as sa

revision='0007_task_updates'
down_revision='0006_poll_lifecycle'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('tasks', recreate='always') as batch:
        batch.drop_constraint('ck_tasks_status',type_='check')
        batch.create_check_constraint('ck_tasks_status',"status IN ('TODO','IN_PROGRESS','DONE','CANCELLED')")
        batch.add_column(sa.Column('version',sa.Integer(),nullable=False,server_default='1'))
        batch.add_column(sa.Column('creation_payload',sa.Text(),nullable=False,server_default=sa.text("''")))
        batch.create_check_constraint('ck_tasks_version',"typeof(version) = 'integer' AND version BETWEEN 1 AND 9007199254740991")
    connection=op.get_bind()
    rows=connection.execute(sa.text('SELECT id,meeting_id,assignee_id,title,description,due_at FROM tasks')).mappings().all()
    for row in rows:
        payload={key:row[key] for key in ['meeting_id','assignee_id','title','description','due_at']}
        connection.execute(sa.text('UPDATE tasks SET creation_payload=:payload WHERE id=:id'),
                           {'payload':json.dumps(payload,sort_keys=True,ensure_ascii=True),'id':row['id']})


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup instead.')
