"""Smoke test: every backend package is importable. Keeps CI green until real tests land."""

import importlib

import pytest

PACKAGES = ["app", "storage", "schemas", "extraction", "exposure"]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_importable(name: str) -> None:
    assert importlib.import_module(name) is not None
