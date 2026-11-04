# Database migrations

Alembic owns all relational schema changes. Generate revisions from the canonical SQLAlchemy
metadata with `alembic revision --autogenerate -m "describe change"`, inspect the generated
migration, then apply with `alembic upgrade head`.

Do not call `Base.metadata.create_all()` at application startup. Published schema changes must
be explicit, reviewed, reversible where practical, and tested against PostgreSQL.
