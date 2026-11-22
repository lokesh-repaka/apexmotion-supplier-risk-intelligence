"""Unit tests for centralized settings in src/core/config.py."""

from decimal import Decimal

from pydantic import SecretStr


def test_settings_import_and_defaults():
    """Verify that Settings can be instantiated with expected default values."""
    from src.core.config import Settings

    settings = Settings()

    # AWS
    assert settings.AWS_REGION == "eu-central-1"
    assert settings.AWS_ACCOUNT_ID == "123456789012"

    # Aurora PostgreSQL
    assert "postgresql+asyncpg://" in str(settings.DATABASE_URL)

    # Neptune
    assert settings.NEPTUNE_ENDPOINT == "localhost"
    assert settings.NEPTUNE_PORT == 8182

    # OpenSearch
    assert settings.OPENSEARCH_ENDPOINT == "http://localhost:9200"
    assert settings.OPENSEARCH_INDEX_CONTRACTS == "contracts-v1"
    assert settings.OPENSEARCH_INDEX_NEWS == "news-v1"

    # Redis
    assert settings.REDIS_URL == "redis://localhost:6379/0"

    # Kafka
    assert settings.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"
    assert settings.KAFKA_TOPIC_SUPPLIER_EVENTS == "supplier-events"
    assert settings.KAFKA_TOPIC_RISK_ALERTS == "risk-alerts"
    assert settings.KAFKA_CONSUMER_GROUP == "apexmotion-risk-engine"

    # AI Models & LiteLLM
    assert settings.LITELLM_BASE_URL == "http://localhost:4000"
    assert "claude-3-5-sonnet" in settings.BEDROCK_SYNTHESIS_MODEL
    assert "claude-3-5-haiku" in settings.BEDROCK_EXTRACTION_MODEL

    # Keycloak
    assert settings.KEYCLOAK_URL == "http://localhost:8080/auth"
    assert settings.KEYCLOAK_REALM == "apexmotion"
    assert settings.KEYCLOAK_CLIENT_ID == "apexmotion-risk-api"

    # Okta & JWT
    assert settings.OKTA_DOMAIN == "dev-apexmotion.okta.com"
    assert settings.OKTA_ISSUER == "https://dev-apexmotion.okta.com/oauth2/default"
    assert settings.OKTA_AUDIENCE == "api://apexmotion-risk"
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_SECRET_KEY.get_secret_value() is not None

    # Offline dev flags
    assert settings.USE_LOCALSTACK is True
    assert settings.USE_MOCK_LLM is True
    assert settings.USE_LOCAL_KAFKA is True


def test_hitl_thresholds_precision():
    """Verify HITL spend thresholds strictly enforce Decimal types to satisfy BR-RULE-001."""
    from src.core.config import Settings

    settings = Settings()

    assert isinstance(settings.HITL_TIER_1_THRESHOLD_USD, Decimal)
    assert settings.HITL_TIER_1_THRESHOLD_USD == Decimal("25000.00")

    assert isinstance(settings.HITL_TIER_2_THRESHOLD_USD, Decimal)
    assert settings.HITL_TIER_2_THRESHOLD_USD == Decimal("100000.00")


def test_get_settings_lru_cache():
    """Verify that get_settings() caches and returns the exact same instance."""
    from src.core.config import get_settings

    settings_1 = get_settings()
    settings_2 = get_settings()

    assert settings_1 is settings_2


def test_settings_environment_override(monkeypatch):
    """Verify environment variables correctly override default settings."""
    from src.core.config import get_settings

    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    monkeypatch.setenv("HITL_TIER_1_THRESHOLD_USD", "30000.00")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.AWS_REGION == "ap-south-1"
    assert settings.HITL_TIER_1_THRESHOLD_USD == Decimal("30000.00")

    # Clean up cache
    get_settings.cache_clear()


def test_secret_str_masking():
    """Verify sensitive credentials are protected using SecretStr."""
    from src.core.config import Settings

    settings = Settings(KEYCLOAK_CLIENT_SECRET="super-secret-key")

    assert isinstance(settings.KEYCLOAK_CLIENT_SECRET, SecretStr)
    assert settings.KEYCLOAK_CLIENT_SECRET.get_secret_value() == "super-secret-key"
    assert "super-secret-key" not in repr(settings)
    assert "super-secret-key" not in str(settings)
