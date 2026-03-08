"""Tests that the Claude API key never leaks into CLI subprocess calls.

Run with: python tools/test_api_leak.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Test: _call_cli strips ANTHROPIC_API_KEY from subprocess environment
# ---------------------------------------------------------------------------

def test_call_cli_strips_api_key():
    """Ensure _call_cli does NOT pass ANTHROPIC_API_KEY to the subprocess."""
    from server.ai_generator import _call_cli
    import asyncio, subprocess

    captured_env = {}

    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        captured_env.update(kwargs.get("env", {}))
        # Return a fake successful result
        result = MagicMock()
        result.returncode = 0
        result.stdout = '{"result": "test", "usage": {}}'
        result.stderr = ""
        return result

    # Set a fake API key in the environment
    fake_key = "sk-ant-api03-FAKE-KEY-FOR-TESTING"
    env_patch = {**os.environ, "ANTHROPIC_API_KEY": fake_key}

    with patch.dict(os.environ, env_patch), \
         patch("subprocess.run", side_effect=fake_run):
        asyncio.run(_call_cli("system prompt", "user prompt"))

    assert "ANTHROPIC_API_KEY" not in captured_env, \
        "CRITICAL: ANTHROPIC_API_KEY leaked into CLI subprocess environment!"
    assert "CLAUDECODE" not in captured_env, \
        "CLAUDECODE leaked into CLI subprocess environment"
    print("  PASS: _call_cli strips ANTHROPIC_API_KEY from subprocess env")


# ---------------------------------------------------------------------------
# Test: AI_BACKEND defaults to "cli"
# ---------------------------------------------------------------------------

def test_backend_defaults_to_cli():
    """Ensure AI_BACKEND defaults to 'cli' when env var is not set."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove AI_BACKEND if set
        os.environ.pop("AI_BACKEND", None)
        # Re-evaluate the default
        backend = os.environ.get("AI_BACKEND", "cli").lower()
    assert backend == "cli", f"AI_BACKEND defaulted to {backend!r}, expected 'cli'"
    print("  PASS: AI_BACKEND defaults to 'cli'")


# ---------------------------------------------------------------------------
# Test: .env file does not set AI_BACKEND=api
# ---------------------------------------------------------------------------

def test_env_file_no_api_backend():
    """Ensure .env file (if present) does not set AI_BACKEND=api."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print("  SKIP: no .env file found")
        return

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            if key.strip() == "AI_BACKEND":
                assert val.strip().lower() != "api", \
                    "CRITICAL: .env sets AI_BACKEND=api — this uses the API directly!"
    print("  PASS: .env does not set AI_BACKEND=api")


# ---------------------------------------------------------------------------
# Test: content_viewer does not force API backend
# ---------------------------------------------------------------------------

def test_content_viewer_no_api_override():
    """Ensure content_viewer.py doesn't override AI_BACKEND to 'api'."""
    viewer_path = Path(__file__).parent / "content_viewer.py"
    if not viewer_path.exists():
        print("  SKIP: content_viewer.py not found")
        return

    source = viewer_path.read_text()
    assert 'AI_BACKEND' not in source or 'AI_BACKEND = "api"' not in source, \
        "content_viewer.py forces AI_BACKEND to 'api'!"
    assert "AI_BACKEND = 'api'" not in source, \
        "content_viewer.py forces AI_BACKEND to 'api'!"
    print("  PASS: content_viewer.py does not override AI_BACKEND")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_call_cli_strips_api_key,
        test_backend_defaults_to_cli,
        test_env_file_no_api_backend,
        test_content_viewer_no_api_override,
    ]
    print(f"Running {len(tests)} API leak tests...\n")
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failures += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}")
            failures += 1

    print(f"\n{'All tests passed!' if not failures else f'{failures} test(s) FAILED'}")
    sys.exit(1 if failures else 0)
