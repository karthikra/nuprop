"""Unit tests for the ``_slugify`` helper.

It is currently duplicated in both the auth and client viewmodels — both copies
are exercised here so the duplication stays behaviourally identical.
"""

from __future__ import annotations

import pytest

from app.viewmodels.auth_viewmodel import _slugify as auth_slugify
from app.viewmodels.client_viewmodel import _slugify as client_slugify


@pytest.mark.parametrize("slugify", [auth_slugify, client_slugify])
class TestSlugify:
    def test_lowercases_and_dashes_spaces(self, slugify):
        assert slugify("Acme Design Studio") == "acme-design-studio"

    def test_strips_special_characters(self, slugify):
        assert slugify("Bob's Burgers & Co.!") == "bobs-burgers-co"

    def test_collapses_repeated_separators(self, slugify):
        assert slugify("a   --  b") == "a-b"

    def test_trims_surrounding_whitespace(self, slugify):
        assert slugify("  Padded Name  ") == "padded-name"
