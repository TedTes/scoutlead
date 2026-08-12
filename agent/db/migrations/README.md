Alembic migrations belong here.

Local development can still auto-create tables with `AUTO_CREATE_TABLES=true`. For Railway or any production deployment, set `AUTO_CREATE_TABLES=false` and run:

```bash
alembic upgrade head
```
