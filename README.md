## stars_backend
### Notes

[Central Repo](https://github.com/mollymachin/astro-app)

Run:
- `uvicorn database_service:app --host 127.0.0.1 --port 5000 --reload`

Use Alembic for database change management.

Libraries: SQLAlchemy is a basic select read update library.
FastAPI is nice. It has its own built in SQLmodel (SQL relational mapping).

Azure can give us a Postgres db - this takes away the maintenance.
Start VM (Azure portal), download postgreSQL onto it and run.

Jason previously used azure table storage - unstructured db - it's an API and is more scalable and good for load testing.

Think about cloud based db usiing Azure table storage, or sharding.
