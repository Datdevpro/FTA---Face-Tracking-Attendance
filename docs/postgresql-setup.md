# PostgreSQL Setup

FTA can run with SQLite for quick local demos, but PostgreSQL should be used for product-style local testing and production-like development.

## 1. Start PostgreSQL

From the project root:

```powershell
docker compose up -d postgres
```

This starts a local PostgreSQL container with:

- Host: `localhost`
- Port: `5432`
- Database: `fta_db`
- User: `fta_user`
- Password: `fta_password`

The data is stored in the Docker volume `fta_postgres_data`.

If Docker is not installed, install PostgreSQL directly on Windows and create the database manually:

```powershell
psql -U postgres
```

Then run inside `psql`:

```sql
CREATE USER fta_user WITH PASSWORD 'fta_password';
CREATE DATABASE fta_db OWNER fta_user;
GRANT ALL PRIVILEGES ON DATABASE fta_db TO fta_user;
```

If `psql` is not recognized, add the PostgreSQL `bin` folder to your Windows `PATH`, for example:

```text
C:\Program Files\PostgreSQL\16\bin
```

## 2. Configure the app

In `.env`, use:

```env
DATABASE_URL=postgresql://fta_user:fta_password@localhost:5432/fta_db
```

For a quick SQLite fallback, use:

```env
DATABASE_URL=sqlite:///./data/fta.db
```

## 3. Initialize tables and seed data

After PostgreSQL is running:

```powershell
python -m scripts.init_db
```

This creates the database tables and default login:

```text
admin / admin123
```

Change the default password before using a production or pilot environment.

## 4. Start FTA

```powershell
.\start-fta.ps1
```

or:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Notes

- Do not delete `data/fta.db` until you are sure you no longer need old local data.
- This setup does not migrate existing SQLite data into PostgreSQL. Treat migration as a separate controlled step.
- For production, use a strong database password, a non-default JWT secret, backup automation, and restricted network access.
