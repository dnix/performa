# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for refinancing functionality.

These tests ensure that the refinancing bug fix remains working and that
construction loans are properly paid off when permanent financing arrives.
"""

from datetime import date

from performa.patterns import OfficeDevelopmentPattern, ResidentialDevelopmentPattern


class TestRefinancingIntegration:
    """
    Integration tests for construction-to-permanent refinancing.

    These tests validate the critical refinancing functionality that was
    previously broken and causing double debt counting.
    """

    def test_residential_development_refinancing_works(self):
        """Test that construction loan is paid off when permanent arrives (residential)."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Refinancing Test Residential",
            acquisition_date=date(2024, 1, 1),
            land_cost=2_000_000,
            total_units=100,
            unit_mix=[
                {"unit_type": "1BR", "count": 100, "avg_sf": 750, "target_rent": 2400}
            ],
            construction_cost_per_unit=250_000,
            construction_duration_months=18,
            hold_period_years=5,
        )

        results = pattern.analyze()
        ledger_df = results.ledger_df

        # Check that refinancing payoff exists
        refinancing_payoffs = ledger_df[
            ledger_df["subcategory"] == "Refinancing Payoff"
        ]
        assert (
            not refinancing_payoffs.empty
        ), "Construction loan must be paid off via refinancing"

        # Verify payoff amount equals construction proceeds
        construction_proceeds = ledger_df[
            (ledger_df["item_name"].str.contains("Construction", na=False))
            & (ledger_df["subcategory"] == "Loan Proceeds")
        ]["amount"].sum()

        refinancing_payoff = abs(refinancing_payoffs["amount"].sum())
        assert (
            abs(construction_proceeds - refinancing_payoff) < 1000
        ), f"Refinancing payoff ${refinancing_payoff:,.0f} must equal construction proceeds ${construction_proceeds:,.0f}"

        # Verify construction loan NOT paid off at disposition
        disposition_payoffs = ledger_df[
            (ledger_df["subcategory"] == "Prepayment")
            & (ledger_df["item_name"].str.contains("Construction", na=False))
        ]
        assert (
            disposition_payoffs.empty
        ), "Construction loan must NOT be paid off at disposition"

    def test_office_development_refinancing_works(self):
        """Test that construction loan is paid off when permanent arrives (office)."""
        pattern = OfficeDevelopmentPattern(
            project_name="Refinancing Test Office",
            acquisition_date=date(2024, 1, 1),
            land_cost=2_500_000,  # Reduced land cost
            gross_area=100_000,
            net_rentable_area=85_000,
            target_rent_psf=45.0,  # Higher rent
            construction_cost_psf=250,  # Reduced construction cost
            construction_duration_months=24,
            hold_period_years=7,
        )

        results = pattern.analyze()
        ledger_df = results.ledger_df

        # Check that refinancing payoff exists
        refinancing_payoffs = ledger_df[
            ledger_df["subcategory"] == "Refinancing Payoff"
        ]
        assert (
            not refinancing_payoffs.empty
        ), "Construction loan must be paid off via refinancing"

        # Verify construction loan NOT paid off at disposition
        disposition_payoffs = ledger_df[
            (ledger_df["subcategory"] == "Prepayment")
            & (ledger_df["item_name"].str.contains("Construction", na=False))
        ]
        assert (
            disposition_payoffs.empty
        ), "Construction loan must NOT be paid off at disposition"

    def test_leverage_never_exceeds_reasonable_bounds(self):
        """Test that total leverage stays within reasonable bounds."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Leverage Test",
            acquisition_date=date(2024, 1, 1),
            land_cost=1_000_000,
            total_units=50,
            unit_mix=[
                {"unit_type": "1BR", "count": 50, "avg_sf": 750, "target_rent": 2200}
            ],
            construction_cost_per_unit=200_000,
            construction_duration_months=18,
            hold_period_years=5,
        )

        results = pattern.analyze()
        ledger_df = results.ledger_df

        # Calculate net debt (accounting for refinancing)
        loan_proceeds = ledger_df[ledger_df["subcategory"] == "Loan Proceeds"][
            "amount"
        ].sum()

        refinancing_payoffs = ledger_df[
            ledger_df["subcategory"] == "Refinancing Payoff"
        ]["amount"].sum()

        refinancing_proceeds = ledger_df[
            ledger_df["subcategory"] == "Refinancing Proceeds"
        ]["amount"].sum()

        net_debt = (
            loan_proceeds + refinancing_payoffs + refinancing_proceeds
        )  # payoffs are negative

        # Calculate project cost and property value for different leverage metrics
        project_cost = pattern.land_cost + (
            pattern.construction_cost_per_unit * pattern.total_units
        )

        # For development projects with cash-out refinancing, use property value for LTV calculation
        # This gives a more accurate picture of leverage vs the completed asset value
        property_valuations = ledger_df[
            ledger_df["subcategory"] == "Other"  # Property valuation entries
        ]["amount"].sum()

        # Use property value if available (more accurate for LTV), else fall back to project cost
        leverage_denominator = (
            property_valuations if property_valuations > 0 else project_cost
        )
        leverage_ratio = net_debt / leverage_denominator

        # Leverage should be reasonable (< 90% LTV or < 150% of project cost for cash-out)
        max_leverage = (
            0.9 if property_valuations > 0 else 1.5
        )  # 90% LTV or 150% of cost
        assert (
            leverage_ratio < max_leverage
        ), f"Leverage ratio {leverage_ratio:.1%} exceeds reasonable bounds ({max_leverage:.0%})"

        # Leverage should be substantial (> 40%) to justify using debt
        assert (
            leverage_ratio > 0.4
        ), f"Leverage ratio {leverage_ratio:.1%} too low - may indicate financing issue"

    def test_leveraged_returns_exceed_unleveraged(self):
        """Test that leverage enhances returns as expected."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Returns Test",
            acquisition_date=date(2024, 1, 1),
            land_cost=1_500_000,
            total_units=75,
            unit_mix=[
                {"unit_type": "1BR", "count": 75, "avg_sf": 750, "target_rent": 2300}
            ],
            construction_cost_per_unit=220_000,
            construction_duration_months=18,
            hold_period_years=5,
        )

        results = pattern.analyze()

        # Leveraged returns should be substantial
        assert (
            results.levered_irr > 0.15
        ), f"Leveraged IRR {results.levered_irr:.2%} should exceed 15% with proper refinancing"

        assert (
            results.equity_multiple > 2.0
        ), f"Equity Multiple {results.equity_multiple:.2f}x should exceed 2.0x with proper financing"

    def test_refinancing_timing_is_correct(self):
        """Test that refinancing happens at the correct time."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Timing Test",
            acquisition_date=date(2024, 1, 1),
            land_cost=500_000,  # Reduced land cost
            total_units=40,
            unit_mix=[
                {
                    "unit_type": "Studio",
                    "count": 40,
                    "avg_sf": 500,
                    "target_rent": 2200,
                }  # Higher rent
            ],
            construction_cost_per_unit=180_000,  # Reduced construction cost
            construction_duration_months=18,  # Should refinance at month 21
            hold_period_years=4,
        )

        results = pattern.analyze()
        ledger_df = results.ledger_df

        # Find refinancing payoff date
        refinancing_payoffs = ledger_df[
            ledger_df["subcategory"] == "Refinancing Payoff"
        ]
        assert not refinancing_payoffs.empty, "Must have refinancing payoff"

        payoff_date = refinancing_payoffs.iloc[0]["date"]

        # Expected refinancing date: construction_duration(18) + 80% of lease_up(18) = month 32
        # Smart timing: refinance after substantial lease-up completion (80% of 18 months = ~14 months)
        # Which is 2026-08-01
        expected_month = 32  # 18 + 14 (80% of 18-month lease-up)

        # Convert to actual date for comparison
        if hasattr(payoff_date, "start_time"):  # PeriodIndex
            payoff_year = payoff_date.start_time.year
            payoff_month = payoff_date.start_time.month
        else:  # datetime.date
            payoff_year = payoff_date.year
            payoff_month = payoff_date.month

        expected_date = date(2024, 1, 1)  # Start date
        expected_date = date(
            expected_date.year + (expected_month - 1) // 12,
            expected_date.month + (expected_month - 1) % 12,
            1,
        )

        assert (
            payoff_year == expected_date.year
        ), f"Refinancing year {payoff_year} should be {expected_date.year}"
        assert (
            payoff_month == expected_date.month
        ), f"Refinancing month {payoff_month} should be {expected_date.month}"

    def test_no_construction_interest_after_refinancing(self):
        """Test that construction loan stops accruing interest after refinancing."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Interest Test",
            acquisition_date=date(2024, 1, 1),
            land_cost=1_000_000,
            total_units=50,
            unit_mix=[
                {"unit_type": "1BR", "count": 50, "avg_sf": 700, "target_rent": 2200}
            ],
            construction_cost_per_unit=200_000,
            construction_duration_months=18,
            hold_period_years=5,
        )

        results = pattern.analyze()
        ledger_df = results.ledger_df

        # Find refinancing date
        refinancing_payoffs = ledger_df[
            ledger_df["subcategory"] == "Refinancing Payoff"
        ]
        assert not refinancing_payoffs.empty
        refinancing_date = refinancing_payoffs.iloc[0]["date"]

        # Find construction interest payments
        construction_interest = ledger_df[
            (ledger_df["subcategory"] == "Interest Payment")
            & (ledger_df["item_name"].str.contains("Construction", na=False))
        ]

        if not construction_interest.empty:
            # Check that no construction interest occurs after refinancing
            post_refinancing_interest = construction_interest[
                construction_interest["date"] > refinancing_date
            ]

            assert post_refinancing_interest.empty, f"Construction loan must stop accruing interest after refinancing at {refinancing_date}"
