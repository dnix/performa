# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Asset valuation helpers for explicit ledger-based valuations.

This module provides utilities for creating explicit asset valuations that are
recorded in the transactional ledger, enabling proper LTV calculations and
other financing metrics that depend on asset values.
"""

from typing import Optional
from uuid import UUID, uuid4

import pandas as pd

from ..core.ledger import Ledger, SeriesMetadata
from ..core.primitives import (
    CashFlowCategoryEnum,
    ValuationSubcategoryEnum,
)


class AssetValuation:
    """
    Helper for creating explicit asset valuations in the ledger.

    Phase 1 Implementation: Provides explicit valuation recording
    Phase 2 Future: May integrate with automated valuation models

    This class supports the explicit-first philosophy by requiring
    all asset values to be explicitly set rather than calculated
    from magic defaults or implicit assumptions.
    """

    @staticmethod
    def add_to_ledger(
        ledger: Ledger,
        value: float,
        date: pd.Timestamp,
        method: str = "Direct",
        asset_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
    ) -> UUID:
        """
        Add an explicit asset valuation to the ledger.

        Args:
            ledger: The ledger to write to
            value: Asset value (positive amount)
            date: Valuation date
            method: Valuation method description (e.g., "Appraisal", "DCF", "Direct")
            asset_id: Asset identifier (optional)
            source_id: Source of valuation (optional, generates UUID if None)

        Returns:
            UUID: Source ID of the valuation record

        Example:
            valuation_id = AssetValuation.add_to_ledger(
                ledger=context.ledger,
                value=12_000_000,
                date=pd.Timestamp("2024-01-01"),
                method="Appraisal",
                asset_id=property.uid
            )
        """
        if source_id is None:
            source_id = uuid4()

        # Create valuation series (positive value, no cash flow impact)
        valuation_series = pd.Series([value], index=[date])

        metadata = SeriesMetadata(
            category=CashFlowCategoryEnum.VALUATION,  # Dedicated valuation category
            subcategory=ValuationSubcategoryEnum.ASSET_VALUATION,
            item_name=f"Asset Valuation - {method}",
            source_id=source_id,
            asset_id=asset_id or source_id,  # Use source_id as fallback
            pass_num=1,  # Valuations are independent of other calculations
        )

        ledger.add_series(valuation_series, metadata)
        return source_id

    @classmethod
    def from_cap_rate(
        cls,
        ledger: Ledger,
        annual_noi: float,
        cap_rate: float,
        date: pd.Timestamp,
        asset_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
    ) -> tuple[float, UUID]:
        """
        Create valuation from NOI and cap rate.

        This is the most common valuation method in commercial real estate,
        using the direct capitalization approach: Value = NOI / Cap Rate

        Args:
            ledger: The ledger to write to
            annual_noi: Annual Net Operating Income
            cap_rate: Capitalization rate (as decimal, e.g., 0.06 for 6%)
            date: Valuation date
            asset_id: Asset identifier (optional)
            source_id: Source of valuation (optional)

        Returns:
            tuple: (calculated_value, source_id)

        Example:
            value, valuation_id = AssetValuation.from_cap_rate(
                ledger=context.ledger,
                annual_noi=1_200_000,
                cap_rate=0.06,  # 6% cap rate
                date=acquisition_date,
                asset_id=property.uid
            )
            # value = 20_000_000 (1.2M / 0.06)
        """
        if cap_rate <= 0:
            raise ValueError("Cap rate must be positive")
        if annual_noi <= 0:
            raise ValueError("Annual NOI must be positive")

        value = annual_noi / cap_rate

        source_id = cls.add_to_ledger(
            ledger=ledger,
            value=value,
            date=date,
            method=f"Direct Cap ({cap_rate:.1%})",
            asset_id=asset_id,
            source_id=source_id,
        )

        return value, source_id

    @classmethod
    def from_price_per_unit(
        cls,
        ledger: Ledger,
        price_per_unit: float,
        unit_count: int,
        date: pd.Timestamp,
        asset_id: Optional[UUID] = None,
        source_id: Optional[UUID] = None,
    ) -> tuple[float, UUID]:
        """
        Create valuation from price per unit and unit count.

        Common for multifamily properties where valuations are often
        expressed as price per dwelling unit.

        Args:
            ledger: The ledger to write to
            price_per_unit: Price per unit (e.g., price per apartment)
            unit_count: Number of units
            date: Valuation date
            asset_id: Asset identifier (optional)
            source_id: Source of valuation (optional)

        Returns:
            tuple: (calculated_value, source_id)

        Example:
            value, valuation_id = AssetValuation.from_price_per_unit(
                ledger=context.ledger,
                price_per_unit=200_000,  # $200k per unit
                unit_count=100,          # 100 units
                date=acquisition_date,
                asset_id=property.uid
            )
            # value = 20_000_000 (200k * 100 units)
        """
        if price_per_unit <= 0:
            raise ValueError("Price per unit must be positive")
        if unit_count <= 0:
            raise ValueError("Unit count must be positive")

        value = price_per_unit * unit_count

        source_id = cls.add_to_ledger(
            ledger=ledger,
            value=value,
            date=date,
            method=f"Price/Unit (${price_per_unit:,.0f}/unit)",
            asset_id=asset_id,
            source_id=source_id,
        )

        return value, source_id
