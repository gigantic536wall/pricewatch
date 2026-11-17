from pricewatch.config import Settings, to_asyncpg_url


def test_neon_url_is_converted_for_asyncpg():
    url = "postgresql://user:pw@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert to_asyncpg_url(url) == "postgresql+asyncpg://user:pw@ep-x.eu-central-1.aws.neon.tech/neondb?ssl=require"


def test_heroku_style_scheme():
    assert to_asyncpg_url("postgres://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"


def test_asyncpg_url_is_kept():
    url = "postgresql+asyncpg://u:p@localhost:5432/db"
    assert to_asyncpg_url(url) == url


def test_unpooled_url_is_preferred(monkeypatch):
    monkeypatch.delenv("PRICEWATCH_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@pooler.example/db")
    monkeypatch.setenv("DATABASE_POSTGRES_URL_NON_POOLING", "postgresql://u:p@direct.example/db")
    assert Settings(_env_file=None).database_url == "postgresql+asyncpg://u:p@direct.example/db"


def test_serverless_detection(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    assert Settings(_env_file=None).serverless is True
    monkeypatch.delenv("VERCEL")
    assert Settings(_env_file=None).serverless is False


def test_cron_secret_reads_platform_variable(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert Settings(_env_file=None).cron_secret == "s3cret"
