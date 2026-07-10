"""SDK configuration model (Pydantic v2).

See ARCHITECTURE.md §2. Construct a single :class:`Settings` instance and
pass it to :class:`~placetopay.checkout.client.Checkout` — the client is
thread-safe and designed to be shared.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from placetopay.checkout.environment import (
    Country,
    Environment,
    resolve_base_url,
)


class Settings(BaseModel):
    """Runtime configuration for a :class:`Checkout` client.

    At minimum, supply ``login`` and ``secret_key``. Provide *either*
    ``environment`` (optionally paired with ``country``) or an explicit
    ``base_url``; supplying both raises a :class:`ValueError`.
    """

    # Pydantic v2 config — we allow arbitrary-typed pluggables (logger)
    # and forbid extras so typos surface loudly.
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=False,
        validate_assignment=True,
    )

    # ── Credentials ─────────────────────────────────────────────────
    login: str = Field(..., min_length=1, description="Merchant login")
    secret_key: SecretStr = Field(
        ..., description="Merchant secret (never transmitted raw)"
    )

    # ── Environment / routing ───────────────────────────────────────
    environment: Environment | None = Field(
        default=Environment.SANDBOX,
        description=(
            "Named environment (SANDBOX/PRODUCTION). Mutually exclusive "
            "with ``base_url``; unset it if you pass ``base_url``."
        ),
    )
    country: Country | None = Field(
        default=None,
        description="Country preset for default locale and currency.",
    )
    base_url: str | None = Field(
        default=None,
        description=(
            "Explicit base URL override. Must be HTTPS. Mutually exclusive "
            "with ``environment``."
        ),
    )

    # ── Timeouts ────────────────────────────────────────────────────
    timeout_connect: float = Field(
        default=10.0, gt=0, description="Connect timeout (seconds)."
    )
    timeout_read: float = Field(
        default=30.0, gt=0, description="Read timeout (seconds)."
    )

    # ── Retry policy (ARCHITECTURE §6) ──────────────────────────────
    retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Total attempts (1 = no retries). Max is 10.",
    )
    retry_initial_delay_ms: int = Field(default=200, ge=0)
    retry_max_delay_ms: int = Field(default=5_000, ge=0)

    # ── Misc ────────────────────────────────────────────────────────
    user_agent_suffix: str | None = Field(
        default=None,
        description="Optional token appended to the SDK's User-Agent header.",
    )
    additional_headers: dict[str, str] = Field(default_factory=dict)
    auth_additional: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional map transmitted inside the auth block as `additional`. "
            "Useful for merchant-specific metadata the gateway records with "
            "each authenticated session. NOT part of the signing digest."
        ),
    )
    logger: logging.Logger | None = Field(
        default=None,
        description=(
            "Optional logger. Defaults to a no-op when None. DEBUG level emits "
            "redacted request/response payloads."
        ),
    )

    # ── Validators ──────────────────────────────────────────────────
    @field_validator("base_url")
    @classmethod
    def _validate_https_only(cls, v: str | None) -> str | None:
        if v is None:
            return None
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("base_url must use https:// (plain http is rejected)")
        if not parsed.netloc:
            raise ValueError(f"base_url is not a valid URL: {v!r}")
        return v

    @field_validator("additional_headers")
    @classmethod
    def _reject_protected_headers(cls, v: dict[str, str]) -> dict[str, str]:
        protected = {"authorization", "content-type", "user-agent"}
        for key in v:
            if key.lower() in protected:
                raise ValueError(
                    f"Header {key!r} is managed by the SDK and cannot be overridden "
                    "via additional_headers (use user_agent_suffix for User-Agent)."
                )
        return v

    @model_validator(mode="after")
    def _environment_xor_base_url(self) -> Settings:
        """Enforce that ``environment`` and ``base_url`` don't both 'win'.

        Pydantic gives ``environment`` a default of ``SANDBOX``, so we can't
        simply ``xor`` the two. The rule: if the caller supplies an explicit
        ``base_url``, we clear the environment. If both were *explicitly*
        supplied (i.e. environment was set to a non-default value), we raise.
        """
        if self.base_url is not None and (
            self.environment is not None and "environment" in self.model_fields_set
        ):
            raise ValueError(
                "Pass either `environment` or `base_url`, not both. "
                "Leave `environment=None` when supplying an explicit `base_url`."
            )
        if self.retry_max_delay_ms < self.retry_initial_delay_ms:
            raise ValueError(
                "retry_max_delay_ms must be >= retry_initial_delay_ms."
            )
        return self

    # ── Derived accessors ───────────────────────────────────────────
    @property
    def resolved_base_url(self) -> str:
        """Effective base URL after applying precedence rules."""
        return resolve_base_url(
            environment=self.environment if self.base_url is None else None,
            country=self.country,
            explicit_base_url=self.base_url,
        )

    def get_secret_key(self) -> str:
        """Return the raw secret_key. Treat the returned value with care."""
        return self.secret_key.get_secret_value()

    def get_default_locale(self) -> str | None:
        return self.country.default_locale if self.country else None

    def get_default_currency(self) -> str | None:
        return self.country.default_currency if self.country else None

    def __repr__(self) -> str:  # pragma: no cover - debug repr
        # Never leak secret_key in repr.
        fields: dict[str, Any] = {
            "login": self.login,
            "environment": self.environment,
            "country": self.country,
            "base_url": self.resolved_base_url,
        }
        return f"Settings({', '.join(f'{k}={v!r}' for k, v in fields.items())})"
