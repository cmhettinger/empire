import pytest

from empire_mail import MailConfig, MailConfigError


MAIL_ENV_VARS = [
    "EMPIRE_MAIL_SMTP_HOST",
    "EMPIRE_MAIL_SMTP_PORT",
    "EMPIRE_MAIL_SMTP_STARTTLS",
    "EMPIRE_MAIL_SMTP_SSL",
    "EMPIRE_MAIL_USERNAME",
    "EMPIRE_MAIL_PASSWORD",
    "EMPIRE_MAIL_FROM",
    "EMPIRE_MAIL_TO_DEFAULT",
]


@pytest.fixture(autouse=True)
def clear_mail_environment(monkeypatch):
    for name in MAIL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_mail_config_loads_from_environment(monkeypatch):
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_PORT", "2525")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_STARTTLS", "false")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_SSL", "true")
    monkeypatch.setenv("EMPIRE_MAIL_USERNAME", "user")
    monkeypatch.setenv("EMPIRE_MAIL_PASSWORD", "secret")
    monkeypatch.setenv("EMPIRE_MAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EMPIRE_MAIL_TO_DEFAULT", "ops@example.com")

    config = MailConfig.from_env()

    assert config.smtp_host == "smtp.example.com"
    assert config.smtp_port == 2525
    assert config.smtp_starttls is False
    assert config.smtp_ssl is True
    assert config.username == "user"
    assert config.password == "secret"
    assert config.from_address == "sender@example.com"
    assert config.to_default == "ops@example.com"


def test_mail_config_repr_does_not_include_password():
    config = MailConfig(
        smtp_host="smtp.example.com",
        username="user",
        password="secret",
    )

    assert "secret" not in repr(config)
    assert "password" not in repr(config)


def test_mail_config_requires_smtp_host(monkeypatch):
    monkeypatch.delenv("EMPIRE_MAIL_SMTP_HOST", raising=False)

    with pytest.raises(MailConfigError, match="EMPIRE_MAIL_SMTP_HOST"):
        MailConfig.from_env()


def test_mail_config_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_PORT", "not-a-port")

    with pytest.raises(MailConfigError, match="EMPIRE_MAIL_SMTP_PORT"):
        MailConfig.from_env()


def test_mail_config_rejects_invalid_bool(monkeypatch):
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_STARTTLS", "maybe")

    with pytest.raises(MailConfigError, match="Invalid boolean"):
        MailConfig.from_env()


def test_mail_config_rejects_starttls_and_ssl_together(monkeypatch):
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_STARTTLS", "true")
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_SSL", "true")

    with pytest.raises(MailConfigError, match="cannot both be true"):
        MailConfig.from_env()


def test_mail_config_rejects_username_without_password(monkeypatch):
    monkeypatch.setenv("EMPIRE_MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("EMPIRE_MAIL_USERNAME", "user")

    with pytest.raises(MailConfigError, match="EMPIRE_MAIL_PASSWORD"):
        MailConfig.from_env()


def test_mail_config_rejects_non_positive_timeout():
    with pytest.raises(MailConfigError, match="timeout"):
        MailConfig(smtp_host="smtp.example.com", timeout=0)
