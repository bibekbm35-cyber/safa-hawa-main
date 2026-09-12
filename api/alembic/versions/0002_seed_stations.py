"""Seed the eight Kathmandu Valley monitoring points.

Reference data, not user data, so it belongs in a migration: any freshly
created database is immediately usable, and the poller has something to poll
without a manual step. If you later change this list, add another migration --
never edit this one, because it has already run in environments you do not
control.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATIONS = [
    ("ratnapark", "Ratna Park", "Kathmandu", 27.7050, 85.3140, 1300),
    ("thamel", "Thamel", "Kathmandu", 27.7154, 85.3123, 1310),
    ("kalanki", "Kalanki", "Kathmandu", 27.6939, 85.2810, 1290),
    ("chabahil", "Chabahil", "Kathmandu", 27.7172, 85.3462, 1320),
    ("pulchowk", "Pulchowk", "Lalitpur", 27.6788, 85.3170, 1300),
    ("bhaktapur-durbar", "Bhaktapur Durbar Square", "Bhaktapur", 27.6722, 85.4278, 1400),
    ("kirtipur", "Kirtipur", "Kathmandu", 27.6786, 85.2778, 1400),
    ("budhanilkantha", "Budhanilkantha", "Kathmandu", 27.7783, 85.3617, 1450),
]


def upgrade() -> None:
    stations = sa.table(
        "stations",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("district", sa.String),
        sa.column("latitude", sa.Float),
        sa.column("longitude", sa.Float),
        sa.column("elevation_m", sa.Integer),
    )
    op.bulk_insert(
        stations,
        [
            {
                "slug": s[0],
                "name": s[1],
                "district": s[2],
                "latitude": s[3],
                "longitude": s[4],
                "elevation_m": s[5],
            }
            for s in STATIONS
        ],
    )


def downgrade() -> None:
    slugs = ", ".join(f"'{s[0]}'" for s in STATIONS)
    op.execute(f"DELETE FROM stations WHERE slug IN ({slugs})")
