# Database and AWS deployment notes

## Which database?

Use PostgreSQL for this Django shop. Orders, order lines, inventory, payments, coupons, addresses, and status history refer to one another, and checkout must update an order and stock as one transaction. Django supports PostgreSQL directly; MongoDB uses a third-party Django backend whose transaction behavior differs from Django's normal `transaction.atomic()` API.

The app continues to use the existing `db.sqlite3` for direct local development. The standard Compose file also keeps SQLite for compatibility with that local data. PostgreSQL is available as an opt-in Compose overlay:

1. Copy `.env.example` to `.env` and set a long random `POSTGRES_PASSWORD` and `SECRET_KEY`.
2. Start it with `docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build`.
3. PostgreSQL data is stored in the named `postgres_data` volume. The first start creates an empty database and runs migrations; it does not copy data out of `db.sqlite3`.

Do not switch a live EC2 shop to the empty PostgreSQL database until its SQLite data has been backed up and migrated. Keep a separate backup before any database cutover.

## Local catalog and demo data

For a local coursework/demo database, the catalog can be expanded without deleting existing rows:

```powershell
.\env\Python310\python.exe manage.py populate_catalog
```

This idempotently brings the active catalog to at least 100 products and records variants, sample price history, and opening stock. The image fields refer to local files in `media_root/`.

To generate a larger **synthetic demo database** for a size demonstration, run:

```powershell
.\env\Python310\python.exe manage.py seed_demo_data --target-mb 100
```

This adds clearly identified `demo_buyer_*` users, inactive `demo-catalog-*` products, `DMD...` order references, and synthetic payments, delivery histories, reviews, refunds, and stock movements until the selected database reaches the target size. These records are for local demos/coursework only; do not use this command against a production database or present the generated orders as real sales. It does not migrate the local SQLite database to PostgreSQL or upload it to AWS.

## AWS production shape

- Run Django behind HTTPS with `ENVIRONMENT=production`, a private `SECRET_KEY`, and the site's real domain/IP in `ALLOWED_HOSTS`.
- Use Amazon RDS for PostgreSQL for a managed production database; keep it private and allow inbound database traffic only from the app's security group.
- Store product images and customer uploads in durable object storage such as S3, or maintain tested backups of the persistent media directory.
- Configure SMTP credentials before relying on order status emails. In local development, emails are printed to the runserver console.
- Set real item stock counts in the admin before accepting customer orders. Existing catalogue rows received a temporary stock default when the stock field was introduced.
- Shipping carrier updates remain manual in the admin. Courier APIs, online card payments, tax rules, and automated return labels are not configured in this project.

Never commit `.env`, AWS credentials, database passwords, or customer database exports.
