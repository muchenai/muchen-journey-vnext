"""Explicit local-only import of the six priced project36 shop products.

Dry run by default. Existing product definitions and all user balances, task
results and redemptions are left untouched. No demo account is created.
"""
import argparse
import json
import os
import uuid

from sqlalchemy import select
from journey_api.db import SessionLocal
from journey_api.medal_catalog import PROJECT36_MEDALS, install_project36_medals
from journey_api.medal_routes import medal_view
from journey_api.review_admin_models import MedalDefinition, ReviewAdminAccess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--organization', type=uuid.UUID, required=True)
    parser.add_argument('--owner', type=uuid.UUID, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.environ.get('APP_ENV', 'local') not in {'local', 'test'}:
        raise SystemExit('This importer is limited to local/test environments.')
    with SessionLocal() as session:
        owner = session.get(ReviewAdminAccess, args.owner)
        if not owner or owner.organization_id != args.organization or owner.access_role != 'super_admin' or owner.revoked_at is not None:
            raise SystemExit('A currently authorized super administrator is required.')
        before = [medal_view(row) for row in session.scalars(select(MedalDefinition).where(
            MedalDefinition.organization_id == args.organization)).all()]
        if not args.apply:
            print(json.dumps(dict(before=before, proposed=PROJECT36_MEDALS), ensure_ascii=False))
            return
        created = install_project36_medals(session, args.organization, args.owner)
        session.commit()
        print(json.dumps(dict(created=created, previousCount=len(before)), ensure_ascii=False))


if __name__ == '__main__':
    main()
