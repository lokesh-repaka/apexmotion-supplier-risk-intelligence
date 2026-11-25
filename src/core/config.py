"""Centralized configuration module for ApexMotion Supplier Risk Intelligence Platform.

Validates and manages all application environment variables via pydantic-settings.
Enforces monetary precision with Decimal types according to BR-RULE-001.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema for the ApexMotion platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --------------------------------------------------------------------------
    # AWS Infrastructure
    # --------------------------------------------------------------------------
    AWS_REGION: str = Field(
        default="eu-central-1",
        description="AWS primary region (EU data sovereignty in Frankfurt)",
    )
    AWS_ACCOUNT_ID: str = Field(
        default="123456789012",
        description="Target AWS Account ID",
    )

    # --------------------------------------------------------------------------
    # Aurora PostgreSQL
    # --------------------------------------------------------------------------
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://apexmotion_app:local_dev_password@localhost:5432/apexmotion",
        description="SQLAlchemy async connection string for Aurora PostgreSQL",
    )

    # --------------------------------------------------------------------------
    # Amazon Neptune (OpenCypher Graph DB)
    # --------------------------------------------------------------------------
    NEPTUNE_ENDPOINT: str = Field(
        default="localhost",
        description="Neptune host endpoint or local emulation",
    )
    NEPTUNE_PORT: int = Field(
        default=8182,
        description="Neptune Bolt/Gremlin port",
    )

    # --------------------------------------------------------------------------
    # Amazon OpenSearch (Vector Search)
    # --------------------------------------------------------------------------
    OPENSEARCH_ENDPOINT: str = Field(
        default="http://localhost:9200",
        description="OpenSearch cluster endpoint",
    )
    OPENSEARCH_INDEX_CONTRACTS: str = Field(
        default="contracts-v1",
        description="OpenSearch index for supplier contract clause vectors",
    )
    OPENSEARCH_INDEX_NEWS: str = Field(
        default="news-v1",
        description="OpenSearch index for external risk news articles",
    )

    # --------------------------------------------------------------------------
    # Redis Cache & Broker
    # --------------------------------------------------------------------------
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for prompt caching and Celery",
    )

    # --------------------------------------------------------------------------
    # Amazon MSK (Kafka)
    # --------------------------------------------------------------------------
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Kafka broker bootstrap servers",
    )
    KAFKA_TOPIC_SUPPLIER_EVENTS: str = Field(
        default="supplier-events",
        description="Topic for incoming real-time supplier disruption events",
    )
    KAFKA_TOPIC_RISK_ALERTS: str = Field(
        default="risk-alerts",
        description="Topic for calculated risk alerts",
    )
    KAFKA_TOPIC_HITL_REQUIRED: str = Field(
        default="hitl-required",
        description="Topic for actions requiring human approval",
    )
    KAFKA_TOPIC_AUDIT_EVENTS: str = Field(
        default="audit-events",
        description="Topic for immutable audit event streams",
    )
    KAFKA_CONSUMER_GROUP: str = Field(
        default="apexmotion-risk-engine",
        description="MSK consumer group identifier",
    )

    # --------------------------------------------------------------------------
    # AI Models & LiteLLM Gateway
    # --------------------------------------------------------------------------
    LITELLM_BASE_URL: str = Field(
        default="http://localhost:4000",
        description="LiteLLM proxy gateway URL",
    )
    BEDROCK_SYNTHESIS_MODEL: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        description="Synthesis model for narrative explanation",
    )
    BEDROCK_EXTRACTION_MODEL: str = Field(
        default="anthropic.claude-3-5-haiku-20241022-v1:0",
        description="Extraction model for contract and news triage",
    )
    VLLM_BASE_URL: str = Field(
        default="http://localhost:8080",
        description="Self-hosted vLLM endpoint for confidential contracts",
    )
    VLLM_MODEL: str = Field(
        default="meta-llama/Llama-3.1-70B-Instruct",
        description="Self-hosted vLLM model for confidential contract extraction",
    )
    VLLM_API_KEY: SecretStr | None = Field(
        default=None,
        description="Optional API key for authenticated self-hosted vLLM endpoint",
    )

    # --------------------------------------------------------------------------
    # Keycloak Identity & RBAC (OIDC)
    # --------------------------------------------------------------------------
    KEYCLOAK_URL: str = Field(
        default="http://localhost:8080/auth",
        description="Keycloak base server URL",
    )
    KEYCLOAK_REALM: str = Field(
        default="apexmotion",
        description="Keycloak security realm",
    )
    KEYCLOAK_CLIENT_ID: str = Field(
        default="apexmotion-risk-api",
        description="Keycloak client identifier for the API",
    )
    KEYCLOAK_CLIENT_SECRET: SecretStr = Field(
        default=SecretStr("local_dev_keycloak_secret"),
        description="Keycloak client secret for token verification",
    )

    # --------------------------------------------------------------------------
    # Okta Identity & RBAC (SAML 2.0 / OIDC)
    # --------------------------------------------------------------------------
    OKTA_DOMAIN: str = Field(
        default="dev-apexmotion.okta.com",
        description="Okta enterprise tenant domain",
    )
    OKTA_ISSUER: str = Field(
        default="https://dev-apexmotion.okta.com/oauth2/default",
        description="Okta OIDC issuer URL",
    )
    OKTA_AUDIENCE: str = Field(
        default="api://apexmotion-risk",
        description="Expected Okta audience claim (aud)",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Default JWT signing algorithm for local dev/testing (RS256 in prod with Okta JWKS)",
    )
    JWT_SECRET_KEY: SecretStr = Field(
        default=SecretStr("apexmotion_super_secure_jwt_dev_secret_key_min_32_chars"),
        description="HMAC secret key for local development and test token signing",
    )

    # --------------------------------------------------------------------------
    # AWS KMS (HITL Cryptographic Signatures)
    # --------------------------------------------------------------------------
    KMS_KEY_ARN: str = Field(
        default="arn:aws:kms:eu-central-1:123456789012:key/12345678-1234-1234-1234-123456789012",
        description="AWS KMS ECDSA P-256 Key ARN for HITL spend signing and verification",
    )

    # --------------------------------------------------------------------------
    # Langfuse Observability
    # --------------------------------------------------------------------------
    LANGFUSE_PUBLIC_KEY: str = Field(
        default="pk-lf-1234567890",
        description="Langfuse project public API key",
    )
    LANGFUSE_SECRET_KEY: SecretStr = Field(
        default=SecretStr("sk-lf-1234567890"),
        description="Langfuse project secret API key",
    )
    LANGFUSE_HOST: str = Field(
        default="http://localhost:3000",
        description="Langfuse host URL",
    )

    # --------------------------------------------------------------------------
    # OpenTelemetry Tracing (P15-1)
    # --------------------------------------------------------------------------
    OTEL_SERVICE_NAME: str = Field(
        default="apexmotion-supplier-risk",
        description="OpenTelemetry service name attribute",
    )
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(
        default="http://localhost:4318",
        description="OpenTelemetry OTLP exporter HTTP endpoint",
    )
    OTEL_ENABLED: bool = Field(
        default=True,
        description="Enable OpenTelemetry distributed tracing and span instrumentation",
    )

    # --------------------------------------------------------------------------
    # HITL Spend Authority Gates (BR-RULE-001 Monetary Precision)
    # --------------------------------------------------------------------------
    HITL_TIER_1_THRESHOLD_USD: Decimal = Field(
        default=Decimal("25000.00"),
        description="Category Manager approval threshold limit",
    )
    HITL_TIER_2_THRESHOLD_USD: Decimal = Field(
        default=Decimal("100000.00"),
        description="Procurement Director approval threshold limit (Dual VP above)",
    )

    # --------------------------------------------------------------------------
    # Local Development & Offline Mock Flags
    # --------------------------------------------------------------------------
    USE_LOCALSTACK: bool = Field(
        default=True,
        description="Mock AWS services via LocalStack stubs",
    )
    USE_MOCK_LLM: bool = Field(
        default=True,
        description="Return offline fixture responses without calling live LLMs",
    )
    USE_LOCAL_KAFKA: bool = Field(
        default=True,
        description="Use local Redpanda/Kafka broker",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached, validated singleton instance of Settings."""
    return Settings()
