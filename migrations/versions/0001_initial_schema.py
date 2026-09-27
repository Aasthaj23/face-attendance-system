"""Create the current Face Attendance schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "student",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("roll_no", sa.String(length=50), nullable=False),
        sa.Column("class_name", sa.String(length=100), nullable=True),
        sa.Column("section", sa.String(length=20), nullable=True),
        sa.Column("photo_path", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_student_roll_no", "student", ["roll_no"], unique=True)

    op.create_table(
        "subject",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_username", "user", ["username"], unique=True)
    op.create_index("ix_user_student_id", "user", ["student_id"], unique=False)

    op.create_table(
        "attendance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"]),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "subject_id", "date", name="uq_attendance_student_subject_date"),
    )
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"], unique=False)
    op.create_index("ix_attendance_subject_id", "attendance", ["subject_id"], unique=False)
    op.create_index("ix_attendance_date", "attendance", ["date"], unique=False)

    op.create_table(
        "face_embedding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_face_embedding_student_id", "face_embedding", ["student_id"], unique=False)


def downgrade():
    op.drop_index("ix_face_embedding_student_id", table_name="face_embedding")
    op.drop_table("face_embedding")
    op.drop_index("ix_attendance_date", table_name="attendance")
    op.drop_index("ix_attendance_subject_id", table_name="attendance")
    op.drop_index("ix_attendance_student_id", table_name="attendance")
    op.drop_table("attendance")
    op.drop_index("ix_user_student_id", table_name="user")
    op.drop_index("ix_user_username", table_name="user")
    op.drop_table("user")
    op.drop_table("subject")
    op.drop_index("ix_student_roll_no", table_name="student")
    op.drop_table("student")
