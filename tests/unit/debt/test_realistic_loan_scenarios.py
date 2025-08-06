# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Realistic Loan Scenarios Test Suite

This demonstrates proper test design with financially realistic scenarios
that remain stable during refactoring and clearly separate compliant vs breach testing.

Key Principles:
1. Use realistic financial parameters that work in practice
2. Create separate tests for expected breaches vs expected compliance
3. Build loan parameters from first principles (NOI -> debt service -> loan amount)
4. Make test intent explicit through naming and documentation
"""

import pandas as pd

from performa.core.primitives import Timeline
from performa.debt.permanent import PermanentFacility
from performa.debt.rates import FixedRate, InterestRate


class RealisticLoanScenarios:
    """Factory for creating realistic loan scenarios for testing."""

    @staticmethod
    def create_stabilized_office_loan():
        """
        Create a realistic stabilized office building loan scenario.

        Based on typical institutional underwriting:
        - Property value: $10M (Class A office building)
        - NOI: $650k (6.5% cap rate)
        - LTV: 75% = $7.5M loan
        - DSCR: ~1.25 (meets typical hurdle)
        """
        return {
            "property_value": 10_000_000,
            "annual_noi": 650_000,
            "loan_amount": 3_992_889,  # Calculated for exact 1.25 DSCR
            "expected_ltv": 0.40,
            "expected_dscr_range": (1.24, 1.26),  # Tight range around target
            "scenario_type": "compliant",
        }

    @staticmethod
    def create_value_add_multifamily():
        """
        Create a value-add multifamily scenario with moderate leverage.

        Typical value-add deal:
        - Property value: $15M
        - Current NOI: $900k (6% current yield)
        - LTV: 70% = $10.5M loan
        - DSCR: ~1.35 (conservative for value-add risk)
        """
        return {
            "property_value": 15_000_000,
            "annual_noi": 900_000,
            "loan_amount": 5_119_088,  # Calculated for exact 1.35 DSCR
            "expected_ltv": 0.34,
            "expected_dscr_range": (1.34, 1.36),
            "scenario_type": "compliant",
        }

    @staticmethod
    def create_distressed_retail_scenario():
        """
        Create a distressed retail scenario that SHOULD breach covenants.

        Stressed retail deal:
        - Property value: $5M (declining)
        - NOI: $200k (4% yield - very low)
        - Outstanding loan: $4M (was 70% LTV, now 80%+)
        - DSCR: Will be below 1.20 due to low NOI
        """
        return {
            "property_value": 5_000_000,
            "annual_noi": 200_000,  # Deliberately low
            "loan_amount": 4_000_000,
            "expected_ltv": 0.80,  # High due to value decline
            "expected_dscr_range": (0.35, 0.40),  # BREACH EXPECTED (calculated: 0.375)
            "scenario_type": "breach_expected",
        }


class TestRealisticCovenantMonitoring:
    """
    Test covenant monitoring with realistic scenarios.

    These tests use financially sound parameters and should remain stable
    during refactoring because they represent real-world viability.
    """

    def test_stabilized_office_compliant_scenario(self):
        """Test covenant monitoring with realistic stabilized office building."""
        timeline = Timeline.from_dates("2024-01-01", "2024-12-31")
        scenario = RealisticLoanScenarios.create_stabilized_office_loan()

        # Create facility with realistic covenant thresholds
        facility = PermanentFacility(
            name="Stabilized Office Loan",
            interest_rate=InterestRate(details=FixedRate(rate=0.055)),
            loan_term_years=10,
            ltv_ratio=0.40,  # Match calculated LTV
            dscr_hurdle=1.25,
            loan_amount=scenario["loan_amount"],
            ongoing_ltv_max=0.45,  # 5% buffer above sizing LTV
            ongoing_dscr_min=1.20,  # Covenant below sizing DSCR
            ongoing_debt_yield_min=0.08,
        )

        # Create realistic time series
        property_values = pd.Series(
            [scenario["property_value"]] * 12, index=timeline.period_index
        )
        noi_values = pd.Series(
            [scenario["annual_noi"]] * 12, index=timeline.period_index
        )

        # Calculate covenant monitoring
        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=scenario["loan_amount"],
        )

        # Validate expected outcomes (should be compliant)
        assert scenario["scenario_type"] == "compliant"

        # LTV should be close to expected
        actual_ltv = results.iloc[0]["LTV"]
        expected_ltv = scenario["expected_ltv"]
        assert (
            abs(actual_ltv - expected_ltv) < 0.05
        ), f"LTV {actual_ltv:.3f} vs expected {expected_ltv:.3f}"

        # DSCR should be in healthy range
        actual_dscr = results.iloc[0]["DSCR"]
        dscr_min, dscr_max = scenario["expected_dscr_range"]
        assert (
            dscr_min <= actual_dscr <= dscr_max
        ), f"DSCR {actual_dscr:.3f} outside range {dscr_min}-{dscr_max}"

        # Should not have covenant breaches
        breach_count = (results["Covenant_Status"] == "BREACH").sum()
        assert (
            breach_count == 0
        ), f"Expected no breaches for compliant scenario, found {breach_count}"

        print(
            f"✅ Stabilized Office Scenario: LTV={actual_ltv:.3f}, DSCR={actual_dscr:.2f}, Breaches={breach_count}"
        )

    def test_value_add_multifamily_compliant_scenario(self):
        """Test covenant monitoring with realistic value-add multifamily deal."""
        timeline = Timeline.from_dates("2024-01-01", "2024-12-31")
        scenario = RealisticLoanScenarios.create_value_add_multifamily()

        facility = PermanentFacility(
            name="Value-Add Multifamily",
            interest_rate=InterestRate(
                details=FixedRate(rate=0.055)
            ),  # Match debt constant calculation
            loan_term_years=10,
            ltv_ratio=0.34,  # Match calculated LTV
            dscr_hurdle=1.35,
            loan_amount=scenario["loan_amount"],
            ongoing_ltv_max=0.40,  # Buffer above sizing LTV
            ongoing_dscr_min=1.30,
            ongoing_debt_yield_min=0.08,
        )

        property_values = pd.Series(
            [scenario["property_value"]] * 12, index=timeline.period_index
        )
        noi_values = pd.Series(
            [scenario["annual_noi"]] * 12, index=timeline.period_index
        )

        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=scenario["loan_amount"],
        )

        # Validate this conservative scenario is compliant
        actual_ltv = results.iloc[0]["LTV"]
        actual_dscr = results.iloc[0]["DSCR"]
        breach_count = (results["Covenant_Status"] == "BREACH").sum()

        assert (
            breach_count == 0
        ), f"Conservative multifamily scenario should be compliant, found {breach_count} breaches"
        assert (
            actual_dscr >= 1.25
        ), f"DSCR {actual_dscr:.3f} should be healthy for conservative deal"

        print(
            f"✅ Value-Add Multifamily: LTV={actual_ltv:.3f}, DSCR={actual_dscr:.2f}, Breaches={breach_count}"
        )

    def test_distressed_retail_breach_scenario(self):
        """Test covenant monitoring with scenario DESIGNED to breach covenants."""
        timeline = Timeline.from_dates("2024-01-01", "2024-12-31")
        scenario = RealisticLoanScenarios.create_distressed_retail_scenario()

        facility = PermanentFacility(
            name="Distressed Retail (Breach Expected)",
            interest_rate=InterestRate(
                details=FixedRate(rate=0.060)
            ),  # Higher rate for distressed
            loan_term_years=10,
            ltv_ratio=0.70,  # Original sizing
            dscr_hurdle=1.25,  # Original sizing
            loan_amount=scenario["loan_amount"],
            ongoing_ltv_max=0.75,  # Covenant threshold
            ongoing_dscr_min=1.20,  # Covenant threshold
            ongoing_debt_yield_min=0.08,
        )

        property_values = pd.Series(
            [scenario["property_value"]] * 12, index=timeline.period_index
        )
        noi_values = pd.Series(
            [scenario["annual_noi"]] * 12, index=timeline.period_index
        )

        results = facility.calculate_covenant_monitoring(
            timeline=timeline,
            property_value_series=property_values,
            noi_series=noi_values,
            loan_amount=scenario["loan_amount"],
        )

        # Validate that breaches occur as expected
        assert scenario["scenario_type"] == "breach_expected"

        actual_ltv = results.iloc[0]["LTV"]
        actual_dscr = results.iloc[0]["DSCR"]
        breach_count = (results["Covenant_Status"] == "BREACH").sum()

        # Should have breaches (this is the point of this test)
        assert breach_count > 0, "Distressed scenario should trigger covenant breaches"

        # DSCR should be in the expected distressed range
        dscr_min, dscr_max = scenario["expected_dscr_range"]
        assert (
            dscr_min <= actual_dscr <= dscr_max
        ), f"DSCR {actual_dscr:.3f} outside distressed range {dscr_min}-{dscr_max}"

        print(
            f"✅ Distressed Retail (Breaches Expected): LTV={actual_ltv:.3f}, DSCR={actual_dscr:.2f}, Breaches={breach_count}"
        )

    def test_vectorized_performance_with_realistic_data(self):
        """Test performance with multiple realistic scenarios."""
        timeline = Timeline.from_dates("2024-01-01", "2029-12-31")  # 6 years

        # Create portfolio of realistic scenarios
        scenarios = [
            RealisticLoanScenarios.create_stabilized_office_loan(),
            RealisticLoanScenarios.create_value_add_multifamily(),
            RealisticLoanScenarios.create_distressed_retail_scenario(),
        ]

        portfolio_results = []

        for i, scenario in enumerate(scenarios):
            facility = PermanentFacility(
                name=f"Realistic Loan {i + 1}",
                interest_rate=InterestRate(details=FixedRate(rate=0.055)),
                loan_term_years=10,
                ltv_ratio=0.75,
                dscr_hurdle=1.25,
                loan_amount=scenario["loan_amount"],
                ongoing_ltv_max=0.80,
                ongoing_dscr_min=1.20,
                ongoing_debt_yield_min=0.08,
            )

            property_values = pd.Series(
                [scenario["property_value"]] * len(timeline.period_index),
                index=timeline.period_index,
            )
            noi_values = pd.Series(
                [scenario["annual_noi"]] * len(timeline.period_index),
                index=timeline.period_index,
            )

            results = facility.calculate_covenant_monitoring(
                timeline=timeline,
                property_value_series=property_values,
                noi_series=noi_values,
                loan_amount=scenario["loan_amount"],
            )

            breach_count = (results["Covenant_Status"] == "BREACH").sum()
            expected_breaches = scenario["scenario_type"] == "breach_expected"

            portfolio_results.append({
                "scenario_type": scenario["scenario_type"],
                "breach_count": breach_count,
                "expected_breaches": expected_breaches,
                "avg_dscr": results["DSCR"].mean(),
            })

        # Validate that compliant scenarios remain compliant and breach scenarios breach
        for result in portfolio_results:
            if result["expected_breaches"]:
                assert (
                    result["breach_count"] > 0
                ), "Breach scenario should have breaches"
            else:
                assert (
                    result["breach_count"] == 0
                ), "Compliant scenario should not have breaches"

        print(
            f"✅ Portfolio Performance Test: {len(scenarios)} realistic scenarios processed successfully"
        )


if __name__ == "__main__":
    # Quick validation
    test_suite = TestRealisticCovenantMonitoring()
    test_suite.test_stabilized_office_compliant_scenario()
    test_suite.test_value_add_multifamily_compliant_scenario()
    test_suite.test_distressed_retail_breach_scenario()
    test_suite.test_vectorized_performance_with_realistic_data()
    print("All realistic scenario tests passed! 🎉")
