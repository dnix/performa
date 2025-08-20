# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Patterns for common real estate acquisition strategies.

These functions assemble complete Deal objects for immediate analysis.

Patterns implemented:
- create_stabilized_acquisition_deal(...) -> Deal (stabilized cash-flowing assets)
- create_value_add_acquisition_deal(...) -> Deal (value-add renovation strategies)
"""

from __future__ import annotations

from datetime import date, datetime

from ..asset.residential import (
    ResidentialCreditLoss,
    ResidentialExpenses,
    ResidentialGeneralVacancyLoss,
    ResidentialLosses,
    ResidentialProperty,
    ResidentialRentRoll,
    ResidentialRolloverLeaseTerms,
    ResidentialRolloverProfile,
    ResidentialUnitSpec,
)
from ..core.primitives import (
    Timeline,
    UponExpirationEnum,
)
from ..deal import (
    AcquisitionTerms,
    Deal,
    create_gp_lp_waterfall,
    create_simple_partnership,
)
from ..debt import (
    FinancingPlan,
    PermanentFacility,
)
from ..valuation import ReversionValuation


def create_stabilized_acquisition_deal(
    property_name: str,
    acquisition_date: date,
    purchase_price: float,
    closing_costs_rate: float,
    asset_type: str,
    property_spec: dict,
    financing_terms: dict,
    partnership_terms: dict,
    hold_period_months: int,
    exit_cap_rate: float,
    exit_transaction_costs_rate: float,
) -> Deal:
    """
    Models a standard acquisition of a stabilized, cash-flowing asset.

    This is the foundational Pattern, modeling the most common transaction in real estate:
    buying an existing, occupied asset for stable cash flow and eventual sale.

    Args:
        property_name: Human-readable name for the property (e.g., "Maple Ridge Apartments")
        acquisition_date: The closing date of the purchase
        purchase_price: The total purchase price of the asset
        closing_costs_rate: Transaction costs as percentage of purchase price (e.g., 0.025 for 2.5%)
        asset_type: Type of asset - "residential" or "office"
        property_spec: Dictionary containing asset specifications:
            - For residential: {"unit_mix": [{"unit_type_name": str, "unit_count": int,
              "current_avg_monthly_rent": float, "avg_area_sf": float, "lease_start_date": date}, ...]}
            - For office: {"net_rentable_area": float, "rent_roll": [lease_spec_dicts]}
        financing_terms: Permanent loan parameters:
            {"ltv_ratio": float, "interest_rate": {"details": {"rate_type": str, "rate": float}},
             "loan_term_years": int, "amortization_years": int}
        partnership_terms: Equity structure:
            - Simple: {"distribution_method": "pari_passu", "gp_share": float, "lp_share": float}
            - Waterfall: {"distribution_method": "waterfall", "gp_share": float, "lp_share": float,
              "pref_return": float, "promote_tiers": [(irr_hurdle, promote_rate), ...]}
        hold_period_months: Length of investment hold period
        exit_cap_rate: Capitalization rate for sale price calculation
        exit_transaction_costs_rate: Costs for selling the property (e.g., 0.015 for 1.5%)

    Returns:
        Complete Deal object ready for analysis

    Example:
        deal = create_stabilized_acquisition_deal(
            property_name="Maple Ridge Apartments",
            acquisition_date=date(2024, 1, 1),
            purchase_price=10_000_000,
            closing_costs_rate=0.025,
            asset_type="residential",
            property_spec={
                "unit_mix": [
                    {"unit_type_name": "1BR", "unit_count": 50, "current_avg_monthly_rent": 1800,
                     "avg_area_sf": 650, "lease_start_date": date(2023, 1, 1)},
                    {"unit_type_name": "2BR", "unit_count": 30, "current_avg_monthly_rent": 2200,
                     "avg_area_sf": 900, "lease_start_date": date(2023, 1, 1)}
                ]
            },
            financing_terms={
                "ltv_ratio": 0.75,
                "interest_rate": {"details": {"rate_type": "fixed", "rate": 0.06}},
                "loan_term_years": 10,
                "amortization_years": 30
            },
            partnership_terms={
                "distribution_method": "pari_passu",
                "gp_share": 0.1,
                "lp_share": 0.9
            },
            hold_period_months=60,
            exit_cap_rate=0.055,
            exit_transaction_costs_rate=0.015
        )

        results = analyze(deal, timeline)
        print(f"Deal IRR: {results.deal_metrics.irr:.2%}")
    """
    # Step 1: Input Validation
    if asset_type not in ["residential", "office"]:
        raise ValueError(
            f"asset_type must be 'residential' or 'office', got: {asset_type}"
        )

    if asset_type == "residential" and "unit_mix" not in property_spec:
        raise ValueError(
            "property_spec must contain 'unit_mix' key for residential properties"
        )

    if asset_type == "office" and not all(
        k in property_spec for k in ["net_rentable_area", "rent_roll"]
    ):
        raise ValueError(
            "property_spec must contain 'net_rentable_area' and 'rent_roll' keys for office properties"
        )

    # Step 2: Build the Asset
    if asset_type == "residential":
        # Create simple market rollover profile for stabilized property
        stabilized_rollover_profile = ResidentialRolloverProfile(
            name="Market Rollover",
            term_months=12,
            renewal_probability=0.75,  # 75% renewal for stabilized property
            downtime_months=1,  # 1 month turnover time
            upon_expiration=UponExpirationEnum.MARKET,  # Standard market rollover
            market_terms=ResidentialRolloverLeaseTerms(
                market_rent=0,  # Will be set from unit specs
                term_months=12,
            ),
            renewal_terms=ResidentialRolloverLeaseTerms(
                market_rent=0,  # Will be set from unit specs
                term_months=12,
            ),
        )

        # Create unit specs from property_spec
        unit_specs = []
        for unit_data in property_spec["unit_mix"]:
            # Update rollover profile with unit-specific rents
            unit_rollover = ResidentialRolloverProfile(
                name=f"{unit_data['unit_type_name']} Rollover",
                term_months=12,
                renewal_probability=0.75,
                downtime_months=1,
                upon_expiration=UponExpirationEnum.MARKET,
                market_terms=ResidentialRolloverLeaseTerms(
                    market_rent=unit_data["current_avg_monthly_rent"],
                    term_months=12,
                ),
                renewal_terms=ResidentialRolloverLeaseTerms(
                    market_rent=unit_data["current_avg_monthly_rent"]
                    * 0.98,  # 2% renewal discount
                    term_months=12,
                ),
            )

            unit_spec = ResidentialUnitSpec(
                unit_type_name=unit_data["unit_type_name"],
                unit_count=unit_data["unit_count"],
                avg_area_sf=unit_data["avg_area_sf"],
                current_avg_monthly_rent=unit_data["current_avg_monthly_rent"],
                rollover_profile=unit_rollover,
                lease_start_date=unit_data["lease_start_date"],
            )
            unit_specs.append(unit_spec)

        rent_roll = ResidentialRentRoll(unit_specs=unit_specs)

        # Create standard losses for stabilized property
        losses = ResidentialLosses(
            general_vacancy=ResidentialGeneralVacancyLoss(
                rate=0.05,  # 5% vacancy for stabilized property
            ),
            credit_loss=ResidentialCreditLoss(
                rate=0.01,  # 1% collection loss for stabilized property
            ),
        )

        # Create basic operating expenses (placeholder - real implementation would be more detailed)
        expenses = ResidentialExpenses(operating_expenses=[])

        # Calculate total area from unit mix
        total_area = sum(
            unit_data["unit_count"] * unit_data["avg_area_sf"]
            for unit_data in property_spec["unit_mix"]
        )

        property_asset = ResidentialProperty(
            name=property_name,
            property_type="multifamily",
            gross_area=total_area,
            net_rentable_area=total_area,
            unit_mix=rent_roll,
            capital_plans=[],  # No major capex for stabilized property
            absorption_plans=[],  # No absorption needed for stabilized property
            expenses=expenses,
            losses=losses,
            miscellaneous_income=[],
        )

    elif asset_type == "office":
        # Office implementation would go here - for now, raise NotImplementedError
        raise NotImplementedError(
            "Office property support will be added in future release"
        )

    # Step 3: Build the FinancingPlan
    permanent_facility = PermanentFacility(
        name=f"{property_name} Permanent Loan",
        ltv_ratio=financing_terms["ltv_ratio"],
        interest_rate=financing_terms["interest_rate"],
        loan_term_years=financing_terms["loan_term_years"],
        amortization_years=financing_terms.get(
            "amortization_years", 30
        ),  # Default 30-year amortization
        dscr_hurdle=financing_terms.get("dscr_hurdle", 1.25),  # Default 1.25x DSCR
    )

    financing_plan = FinancingPlan(
        name=f"{property_name} Financing", facilities=[permanent_facility]
    )

    # Step 4: Build the PartnershipStructure
    if partnership_terms["distribution_method"] == "waterfall":
        partnership = create_gp_lp_waterfall(
            gp_share=partnership_terms["gp_share"],
            lp_share=partnership_terms["lp_share"],
            pref_return=partnership_terms["pref_return"],
            promote_tiers=partnership_terms.get(
                "promote_tiers", [(0.15, 0.30)]
            ),  # Default tier
            final_promote_rate=partnership_terms.get(
                "final_promote_rate", 0.30
            ),  # Default final promote
        )
    elif partnership_terms["distribution_method"] == "pari_passu":
        partnership = create_simple_partnership(
            gp_name=f"{property_name} GP",
            lp_name=f"{property_name} LP",
            gp_share=partnership_terms["gp_share"],
            lp_share=partnership_terms["lp_share"],
        )
    else:
        raise ValueError(
            f"Unsupported distribution_method: {partnership_terms['distribution_method']}"
        )

    # Step 5: Build AcquisitionTerms
    acquisition_end_date = (
        datetime.combine(acquisition_date, datetime.min.time())
        .replace(
            month=acquisition_date.month + 1 if acquisition_date.month <= 11 else 1,
            year=acquisition_date.year
            if acquisition_date.month <= 11
            else acquisition_date.year + 1,
        )
        .date()
    )

    acquisition_timeline = Timeline.from_dates(
        start_date=acquisition_date.strftime("%Y-%m-%d"),
        end_date=acquisition_end_date.strftime("%Y-%m-%d"),
    )

    acquisition = AcquisitionTerms(
        name=f"{property_name} Acquisition",
        timeline=acquisition_timeline,
        value=purchase_price,
        acquisition_date=acquisition_date,
        closing_costs=purchase_price * closing_costs_rate,
    )

    # Step 6: Build ReversionValuation
    reversion = ReversionValuation(
        name=f"{property_name} Sale",
        cap_rate=exit_cap_rate,
        transaction_costs_rate=exit_transaction_costs_rate,
        hold_period_months=hold_period_months,
    )

    # Step 7: Assemble and Return the Final Deal
    deal = Deal(
        name=f"{property_name} Stabilized Acquisition",
        asset=property_asset,
        acquisition=acquisition,
        financing=financing_plan,
        equity_partners=partnership,
        exit_valuation=reversion,
    )

    return deal
