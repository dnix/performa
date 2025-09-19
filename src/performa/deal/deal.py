# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Core Deal Model - Universal Investment Container

This module defines the central Deal model that wraps any asset type with
complete investment strategy including acquisition, financing, disposition, and equity structure.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import Field

from ..asset.office.property import OfficeProperty
from ..asset.residential.property import ResidentialProperty
from ..core.primitives import AssetTypeEnum, Model
from ..debt.plan import FinancingPlan
from ..development.project import DevelopmentProject
from ..valuation import AnyValuation
from .acquisition import AcquisitionTerms
from .fees import DealFee
from .partnership import PartnershipStructure

# Simple union for all asset types that can be in a Deal
# Pydantic v2 automatically infers the correct type based on unique fields:
# - OfficeProperty: has unique 'rent_roll' field of type OfficeRentRoll
# - ResidentialProperty: has unique 'unit_mix' field of type ResidentialRentRoll
# - DevelopmentProject: has unique 'construction_plan' and 'blueprints' fields
# No artificial discriminator needed - let Pydantic do the smart type inference
# Required by Pydantic for polymorphic validation across all asset types
AnyAsset = Union[OfficeProperty, ResidentialProperty, DevelopmentProject]


class Deal(Model):
    """
    Universal deal container for any real estate investment.

    This is the core model that enables the unified deal-centric architecture.
    It cleanly separates the physical asset from the investment strategy,
    allowing the same analyze() function to handle any scenario.

    Key Architecture:
    - asset: The physical real estate property or development project
    - acquisition: How the asset is purchased (timing, costs)
    - financing: Complete debt structure over asset lifecycle
    - disposition: Exit strategy and assumptions
    - equity: Partner structure and waterfall logic

    Examples:
        # Simple stabilized acquisition
        deal = Deal(
            name="123 Main Street Acquisition",
            asset=office_property,
            acquisition=AcquisitionTerms(...),
            financing=FinancingPlan([permanent_loan]),
            exit_valuation=DirectCapValuation(...)
        )

        # Complex development project
        deal = Deal(
            name="Urban Mixed-Use Development",
            asset=development_project,
            acquisition=AcquisitionTerms(...),  # Land acquisition
            financing=FinancingPlan([construction_loan, permanent_loan]),
            exit_valuation=DCFValuation(...)
        )
    """

    # Core Identity
    uid: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Deal name for identification")
    description: Optional[str] = Field(default=None, description="Deal description")

    # Core Components - The Universal Deal Structure
    asset: AnyAsset = Field(..., description="The physical real estate asset")
    acquisition: AcquisitionTerms = Field(
        ..., description="Acquisition terms and costs"
    )

    # Financing - Complete debt structure over asset lifecycle
    financing: Optional[FinancingPlan] = Field(
        default=None, description="Debt facilities sequence"
    )

    # Exit/Disposition/Terminal Valuation - Exit strategy and valuation assumptions
    exit_valuation: Optional[AnyValuation] = Field(
        default=None, description="Exit strategy and valuation assumptions"
    )

    # Equity Structure - Partnership structure for equity waterfall
    equity_partners: Optional[PartnershipStructure] = Field(
        default=None,
        description="Partnership structure for equity waterfall and distributions",
    )

    # Funding Strategy - Order of capital deployment during development
    funding_cascade: Literal["equity_first", "pro_rata", "debt_first"] = Field(
        "equity_first", description="Order of capital deployment during development"
    )

    # Deal Fees - Optional deal fee structures (developer, management, etc.)
    deal_fees: Optional[List[DealFee]] = Field(
        default=None, description="Deal-level fee structures and payment schedules"
    )

    @property
    def deal_type(self) -> str:
        """
        Classify the deal based on the asset type.

        Returns:
            String classification of the deal type
        """
        # FIXME: this could be problematic to maintain as we add more use types
        if hasattr(self.asset, "construction_plan"):
            return "development"
        elif self.asset.property_type == AssetTypeEnum.OFFICE:
            return "office_acquisition"
        elif self.asset.property_type == AssetTypeEnum.MULTIFAMILY:
            return "residential_acquisition"
        else:
            return f"{self.asset.property_type.value}_acquisition"

    @property
    def is_development_deal(self) -> bool:
        """Check if this is a development deal."""
        return hasattr(self.asset, "construction_plan")

    @property
    def financing_type(self) -> str:
        """Classify the financing structure."""
        if self.financing is None:
            return "all_equity"
        elif self.financing.has_refinancing:
            return "refinancing"
        elif self.financing.has_construction_financing:
            return "construction_financing"
        elif self.financing.has_permanent_financing:
            return "permanent_financing"
        else:
            return "other_financing"

    @property
    def has_equity_partners(self) -> bool:
        """Check if this deal has equity partners."""
        return (
            self.equity_partners is not None and self.equity_partners.partner_count > 0
        )
