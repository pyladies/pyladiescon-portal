# Repairs production. While #411 was open, cabotage deployed each push of the
# branch and ran ``migrate``, so the database applied an early draft of the
# invitation table that had no ``sent_to`` column; the column was added to
# that migration in place afterwards, and the files were then squashed into
# ``0001_initial``, which the database already recorded as applied. The
# model has the field, the table does not, and every page that reads
# invitations 500s. Adds the column where it is missing; a no-op on a
# database created from the final ``0001_initial``.
#
# Lesson recorded in speakers/README.md: a migration is frozen the moment it
# is pushed, not merged, because pull-request deploys run it.

from django.db import migrations

ADD_COLUMN = """
ALTER TABLE speakers_invitation
    ADD COLUMN IF NOT EXISTS sent_to varchar(254) NOT NULL DEFAULT '';
ALTER TABLE speakers_invitation ALTER COLUMN sent_to DROP DEFAULT;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("speakers", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=ADD_COLUMN, reverse_sql=migrations.RunSQL.noop, state_operations=[]
        ),
    ]
