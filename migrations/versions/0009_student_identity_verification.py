"""Record identity checks performed at the lab without approving sign-up."""

from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('student') as batch:
        batch.add_column(sa.Column('identity_verified_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('identity_verified_by', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_student_identity_verified_by_admin', 'admin', ['identity_verified_by'], ['id'])
    # Only a recorded check-in against the student's *current* identity counts.
    # An old visit with a subsequently edited name or student number is not proof.
    op.execute('''
        UPDATE student
        SET identity_verified_at = (
            SELECT r.checked_in_at FROM reservation AS r
            WHERE r.student_pk = student.id AND r.is_attended = 1
              AND r.checked_in_at IS NOT NULL
              AND r.student_id = student.student_number AND r.student_name = student.name
            ORDER BY r.checked_in_at DESC LIMIT 1
        ),
        identity_verified_by = (
            SELECT r.checked_in_by FROM reservation AS r
            WHERE r.student_pk = student.id AND r.is_attended = 1
              AND r.checked_in_at IS NOT NULL
              AND r.student_id = student.student_number AND r.student_name = student.name
            ORDER BY r.checked_in_at DESC LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1 FROM reservation AS r
            WHERE r.student_pk = student.id AND r.is_attended = 1
              AND r.checked_in_at IS NOT NULL
              AND r.student_id = student.student_number AND r.student_name = student.name
        )
    ''')


def downgrade():
    with op.batch_alter_table('student') as batch:
        batch.drop_constraint('fk_student_identity_verified_by_admin', type_='foreignkey')
        batch.drop_column('identity_verified_by')
        batch.drop_column('identity_verified_at')
