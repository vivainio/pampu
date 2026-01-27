"""Bamboo API client."""

import os
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

from atlassian import Bamboo
from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("pampu"))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.toml"


def load_credentials() -> dict:
    """Load credentials from config file."""
    if not CREDENTIALS_FILE.exists():
        return {}

    with open(CREDENTIALS_FILE, "rb") as f:
        return tomllib.load(f)


def save_credentials(url: str, token: str) -> None:
    """Save credentials to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    content = f'url = "{url}"\ntoken = "{token}"\n'
    CREDENTIALS_FILE.write_text(content)
    CREDENTIALS_FILE.chmod(0o600)


def get_credentials() -> tuple[str, str]:
    """Get Bamboo credentials from env vars or config file.

    Environment variables take precedence over config file.

    Returns:
        Tuple of (url, token)
    """
    # Check environment variables first
    url = os.environ.get("BAMBOO_URL")
    token = os.environ.get("BAMBOO_TOKEN")

    # Fall back to config file
    if not url or not token:
        creds = load_credentials()
        url = url or creds.get("url")
        token = token or creds.get("token")

    if not url or not token:
        print("Error: Credentials not configured.", file=sys.stderr)
        print("\nEither set environment variables:", file=sys.stderr)
        print("  export BAMBOO_URL='https://bamboo.yourcompany.com'", file=sys.stderr)
        print("  export BAMBOO_TOKEN='your-personal-access-token'", file=sys.stderr)
        print("\nOr run 'pampu init' to save credentials.", file=sys.stderr)
        sys.exit(1)

    return url, token


@lru_cache(maxsize=1)
def get_bamboo() -> Bamboo:
    """Get authenticated Bamboo client (cached)."""
    url, token = get_credentials()
    return Bamboo(url=url, token=token)
