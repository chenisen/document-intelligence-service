"""Shared test configuration.

Fake credentials are pinned before any adapter import: a test that escapes its double fails on
an invalid credential instead of reaching the real account. This is the safety net that lets the
whole suite run on a machine that has real credentials configured.
"""

import os

os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ.setdefault("DIS_PROFILE", "fake")
