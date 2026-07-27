import os
import subprocess
import sys


def staging_worker_environment() -> dict[str, str]:
    env = {
        **os.environ,
        "APP_ENV": "staging",
        "APP_RELEASE": "a" * 40,
        "ALLOW_FIXTURE_IDENTITY": "false",
        "CONFIG_SCHEMA_VERSION": "3",
        "DATABASE_URL": (
            "postgresql+psycopg://journey_next_runtime:unused@"
            "db.example.invalid:5432/journey_next_staging"
        ),
        "NOTIFICATION_ADAPTER": "DISABLED",
    }
    for name in ("SESSION_SECRET", "INVITE_SECRET", "IMPORT_SIGNING_KEY"):
        env.pop(name, None)
    return env


def test_staging_worker_import_needs_database_config_only():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from journey_worker.main import WorkerSettings; "
                "settings = WorkerSettings.from_env(); "
                "assert settings.app_env == 'staging'; "
                "assert settings.adapter == 'DISABLED'"
            ),
        ],
        env=staging_worker_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_api_still_rejects_staging_without_identity_secrets():
    result = subprocess.run(
        [sys.executable, "-c", "import journey_api.main"],
        env=staging_worker_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "vNext secrets must be independently configured" in result.stderr
