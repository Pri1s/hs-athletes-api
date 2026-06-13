"""seed playground schools

Revision ID: cf1c477504c2
Revises: 1c50463b1679
Create Date: 2026-06-13 00:51:54.806046

Sprint 1 playground seeding (S1-005). Seeds the initial Playground
cohort: the five Round Rock ISD comprehensive high schools that field
UIL 6A boys basketball. is_playground=true marks them as the fixed
cohort that downstream Sprint 1 tasks operate on. governing_body
defaults to 'uil'. See docs/playground-district.md for source criteria.

Out of scope (no owner yet): school_seasons classification /
competition_district rows, and roster/athlete ingestion.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf1c477504c2'
down_revision: Union[str, Sequence[str], None] = '1c50463b1679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
insert into schools (name, city, school_system, is_playground) values
    ('Round Rock High School', 'Round Rock', 'Round Rock ISD', true),
    ('Cedar Ridge High School', 'Round Rock', 'Round Rock ISD', true),
    ('Stony Point High School', 'Round Rock', 'Round Rock ISD', true),
    ('McNeil High School', 'Austin', 'Round Rock ISD', true),
    ('Westwood High School', 'Austin', 'Round Rock ISD', true);
""")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
delete from schools
where school_system = 'Round Rock ISD'
  and is_playground = true
  and name in (
    'Round Rock High School',
    'Cedar Ridge High School',
    'Stony Point High School',
    'McNeil High School',
    'Westwood High School'
  );
""")
