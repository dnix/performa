# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for Partner model with capital commitments.

Tests the enhanced Partner model functionality including capital commitment
field validation, serialization, and integration with existing partner features.
"""

import pytest
from pydantic import ValidationError

from performa.deal.entities import Partner


class TestPartnerCapitalCommitment:
    """Test Partner model with capital commitment functionality."""

    def test_partner_without_commitment(self):
        """Test Partner creation without capital commitment (derived mode)."""
        partner = Partner(name="Test GP", kind="GP", share=0.25)

        assert partner.capital_commitment is None
        assert partner.share == 0.25
        assert partner.kind == "GP"
        assert "Test GP" in str(partner)

    def test_partner_with_commitment(self):
        """Test Partner creation with explicit capital commitment."""
        partner = Partner(
            name="Institutional LP",
            kind="LP",
            share=0.75,
            capital_commitment=50_000_000,
        )

        assert partner.capital_commitment == 50_000_000
        assert partner.share == 0.75
        assert partner.kind == "LP"
        assert "Institutional LP" in str(partner)

    def test_partner_zero_commitment(self):
        """Test Partner with zero capital commitment."""
        partner = Partner(
            name="Zero Commitment GP", kind="GP", share=0.10, capital_commitment=0.0
        )

        assert partner.capital_commitment == 0.0
        assert partner.share == 0.10

    def test_partner_negative_commitment_invalid(self):
        """Test that negative capital commitments are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            Partner(
                name="Invalid Partner",
                kind="GP",
                share=0.20,
                capital_commitment=-1_000_000,  # Invalid: negative
            )

        # Should reject negative commitment
        assert "greater than or equal to 0" in str(exc_info.value).lower()

    def test_partner_share_validation_still_works(self):
        """Test that existing share validation works with commitments."""
        # Invalid share > 1.0
        with pytest.raises(ValidationError):
            Partner(
                name="Invalid Share",
                kind="LP",
                share=1.5,  # Invalid
                capital_commitment=10_000_000,
            )

        # Invalid share < 0.0
        with pytest.raises(ValidationError):
            Partner(
                name="Invalid Share",
                kind="LP",
                share=-0.1,  # Invalid
                capital_commitment=10_000_000,
            )

    def test_partner_serialization_with_commitment(self):
        """Test Partner serialization/deserialization with commitment."""
        original = Partner(
            name="Serialization Test",
            kind="GP",
            share=0.15,
            capital_commitment=5_000_000,
        )

        # Serialize to dict
        data = original.model_dump()
        assert data["capital_commitment"] == 5_000_000
        assert data["share"] == 0.15
        assert data["name"] == "Serialization Test"

        # Deserialize back
        restored = Partner.model_validate(data)
        assert restored.capital_commitment == original.capital_commitment
        assert restored.share == original.share
        assert restored.name == original.name
        assert restored.kind == original.kind

    def test_partner_serialization_without_commitment(self):
        """Test Partner serialization without commitment (None value)."""
        original = Partner(name="No Commitment Test", kind="LP", share=0.85)

        # Serialize to dict
        data = original.model_dump()
        assert data["capital_commitment"] is None
        assert data["share"] == 0.85

        # Deserialize back
        restored = Partner.model_validate(data)
        assert restored.capital_commitment is None
        assert restored.share == original.share
        assert restored.name == original.name

    def test_partner_kind_validation_still_works(self):
        """Test that existing kind validation works with commitments."""
        # Invalid kind
        with pytest.raises(ValidationError):
            Partner(
                name="Invalid Kind",
                kind="INVALID",  # Must be "GP" or "LP"
                share=0.50,
                capital_commitment=25_000_000,
            )

    def test_multiple_partners_different_commitments(self):
        """Test creating multiple partners with different commitment structures."""
        gp_with_commitment = Partner(
            name="GP with Capital", kind="GP", share=0.20, capital_commitment=2_000_000
        )

        gp_without_commitment = Partner(
            name="GP without Capital", kind="GP", share=0.10
        )

        lp_with_commitment = Partner(
            name="LP with Capital", kind="LP", share=0.70, capital_commitment=35_000_000
        )

        # All should be valid individually
        assert gp_with_commitment.capital_commitment == 2_000_000
        assert gp_without_commitment.capital_commitment is None
        assert lp_with_commitment.capital_commitment == 35_000_000

        # String representations should work
        assert "GP with Capital" in str(gp_with_commitment)
        assert "GP without Capital" in str(gp_without_commitment)
        assert "LP with Capital" in str(lp_with_commitment)
