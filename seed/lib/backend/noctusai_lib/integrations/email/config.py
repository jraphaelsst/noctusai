"""`SmtpConfig` — the Real sender's configuration.

`SMTP_SECURITY_MODES` / `DEFAULT_SMTP_SECURITY` intentionally mirror
`digest._SMTP_SECURITY_MODES` / `digest._DEFAULT_SMTP_SECURITY`
(`starttls` default, `ssl` for implicit-TLS/465, `none` only for local
test servers that don't speak TLS at all) — one vocabulary for "what
does SMTP security mean here", not two modules quietly disagreeing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import EmailNotConfigured

SMTP_SECURITY_MODES = ("ssl", "starttls", "none")
DEFAULT_SMTP_SECURITY = "starttls"
DEFAULT_SMTP_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class SmtpConfig:
    """Everything `SmtpEmailSender` needs to open a connection and
    identify itself. `from_email`'s domain is also what
    `SmtpEmailSender` derives a `Message-ID` from when the caller
    doesn't supply one."""

    host: str
    port: int
    username: str
    password: str
    security: str = DEFAULT_SMTP_SECURITY
    from_email: str = ""
    from_name: str = ""
    timeout_seconds: float = DEFAULT_SMTP_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.security not in SMTP_SECURITY_MODES:
            raise ValueError(
                f"invalid smtp security {self.security!r}; "
                f"allowed: {SMTP_SECURITY_MODES}"
            )

    @classmethod
    def from_credentials(cls, creds: Mapping[str, Any]) -> "SmtpConfig":
        """Build from a plain dict keyed exactly like
        `digest._resolve_smtp_config`'s credential names —
        `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password`,
        `smtp_security`, `email_from`, `email_from_name` — the same
        names `resolve_credential(...)` resolves on both the digest
        path and this one, so a caller building this dict from the
        3-tier credential chain (org → platform → env) agrees with the
        digest module about what each key means.

        Raises `EmailNotConfigured` when host/port/username/password
        don't all resolve — never falls back to a partially-built,
        certain-to-fail config.
        """
        host = creds.get("smtp_host")
        port = creds.get("smtp_port")
        username = creds.get("smtp_username")
        password = creds.get("smtp_password")
        if not (host and port and username and password):
            raise EmailNotConfigured(
                "smtp_host / smtp_port / smtp_username / smtp_password "
                "must all resolve to build an SmtpConfig."
            )
        try:
            port_int = int(port)
        except (TypeError, ValueError) as exc:
            raise EmailNotConfigured(
                f"non-integer smtp_port: {port!r}"
            ) from exc

        security = str(creds.get("smtp_security") or DEFAULT_SMTP_SECURITY).lower()
        if security not in SMTP_SECURITY_MODES:
            security = DEFAULT_SMTP_SECURITY

        return cls(
            host=str(host),
            port=port_int,
            username=str(username),
            password=str(password),
            security=security,
            from_email=str(creds.get("email_from") or username),
            from_name=str(creds.get("email_from_name") or ""),
        )


__all__ = [
    "DEFAULT_SMTP_SECURITY",
    "DEFAULT_SMTP_TIMEOUT_SECONDS",
    "SMTP_SECURITY_MODES",
    "SmtpConfig",
]
