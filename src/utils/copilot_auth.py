"""GitHub Copilot authentication utilities for Honcho.

Handles token resolution, session token exchange, and header construction
for the Copilot API.

Auth flow:
  1. Resolve a GitHub OAuth token from config or env vars
  2. Exchange it for a short-lived Copilot session token via
     https://api.github.com/copilot_internal/v2/token
  3. Use the session token as Bearer auth for Copilot API calls

Token sources (priority order):
  1. LLM_COPILOT_GITHUB_TOKEN env var (explicit override)
  2. ~/.config/github-copilot/apps.json (VS Code / Copilot CLI OAuth token)
  3. GH_TOKEN / GITHUB_TOKEN env vars (fallback)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

COPILOT_API_BASE_URL = "https://api.githubcopilot.com"
_TOKEN_EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
_EDITOR_VERSION = "vscode/1.104.1"

_CLASSIC_PAT_PREFIX = "ghp_"
_ENV_VARS = ("LLM_COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")

# Cached session token state
_session_lock = threading.Lock()
_cached_session_token: str | None = None
_cached_session_expires_at: float = 0
_resolved_github_token: str | None = None


def _read_copilot_apps_token() -> str | None:
    """Read the OAuth token from the GitHub Copilot apps.json config file."""
    apps_path = Path.home() / ".config" / "github-copilot" / "apps.json"
    if not apps_path.exists():
        return None
    try:
        with open(apps_path) as f:
            data = json.load(f)
        for entry in data.values():
            token = entry.get("oauth_token", "").strip()
            if token:
                return token
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.debug("Failed to read copilot apps.json: %s", e)
    return None


def _resolve_github_token(configured_token: str | None = None) -> str | None:
    """Resolve a GitHub token suitable for Copilot token exchange.

    Priority: configured token > apps.json > env vars.
    """
    # Check explicitly configured token first
    if configured_token and configured_token.strip():
        token = configured_token.strip()
        if token.startswith(_CLASSIC_PAT_PREFIX):
            logger.warning("Configured COPILOT_GITHUB_TOKEN is a classic PAT (ghp_*), not supported")
            return None
        return token

    # Check apps.json (VS Code / Copilot CLI OAuth token)
    apps_token = _read_copilot_apps_token()
    if apps_token:
        return apps_token

    # Check env vars as fallback
    for env_var in _ENV_VARS:
        val = os.getenv(env_var, "").strip()
        if val:
            if val.startswith(_CLASSIC_PAT_PREFIX):
                logger.warning("Token from %s is a classic PAT (ghp_*), skipping", env_var)
                continue
            return val

    return None


def _exchange_session_token(github_token: str) -> tuple[str, float]:
    """Exchange a GitHub token for a short-lived Copilot session token.

    Returns (session_token, expires_at_timestamp).
    Raises ValueError on failure.
    """
    req = urllib.request.Request(
        _TOKEN_EXCHANGE_URL,
        headers={
            "Authorization": f"token {github_token}",
            "Editor-Version": _EDITOR_VERSION,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        raise ValueError(f"Copilot token exchange failed: {e}") from e

    token = data.get("token", "").strip()
    expires_at = data.get("expires_at", 0)
    if not token:
        raise ValueError("Copilot token exchange returned empty token")

    return token, float(expires_at)


def resolve_copilot_token(configured_token: str | None = None) -> str | None:
    """Resolve a Copilot session token, exchanging if needed.

    Caches the session token and refreshes when it expires.
    Returns the session token string or None if unavailable.
    """
    global _cached_session_token, _cached_session_expires_at, _resolved_github_token

    with _session_lock:
        # Return cached token if still valid (with 60s margin)
        if _cached_session_token and time.time() < (_cached_session_expires_at - 60):
            return _cached_session_token

        # Resolve the underlying GitHub token
        github_token = _resolve_github_token(configured_token)
        if not github_token:
            logger.warning("No GitHub token available for Copilot authentication")
            return None

        _resolved_github_token = github_token

        # Exchange for session token
        try:
            session_token, expires_at = _exchange_session_token(github_token)
            _cached_session_token = session_token
            _cached_session_expires_at = expires_at
            logger.info("Copilot session token acquired (expires at %s)", expires_at)
            return session_token
        except ValueError as e:
            logger.error("Failed to acquire Copilot session token: %s", e)
            return None


def refresh_copilot_token() -> str | None:
    """Force-refresh the Copilot session token."""
    global _cached_session_token, _cached_session_expires_at

    with _session_lock:
        _cached_session_token = None
        _cached_session_expires_at = 0

    return resolve_copilot_token(_resolved_github_token)


def copilot_default_headers() -> dict[str, str]:
    """Build the required headers for Copilot API requests."""
    return {
        "Editor-Version": _EDITOR_VERSION,
        "Openai-Intent": "conversation-edits",
        "x-initiator": "agent",
    }
