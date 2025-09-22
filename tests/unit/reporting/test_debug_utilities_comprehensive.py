# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive test suite for polymorphic debug utilities.

Tests the enhanced debug.py module's ability to introspect and analyze
any Performa object type with proper class visibility and configuration extraction.
"""

from datetime import date
from unittest.mock import Mock

import pytest

from performa.core.primitives import GlobalSettings, Timeline
from performa.deal import Deal
from performa.debt.constructs import create_construction_to_permanent_plan
from performa.patterns import (
    ResidentialDevelopmentPattern,
    StabilizedAcquisitionPattern,
)
from performa.reporting.debug import (
    _classify_performa_object,  # noqa: PLC2701
    _handle_financing_plan,  # noqa: PLC2701
    _handle_generic_object,  # noqa: PLC2701
    _handle_primitive_object,  # noqa: PLC2701
    _handle_pydantic_object,  # noqa: PLC2701
    analyze_ledger_shape,
    compare_deal_configurations,
    # New debug utilities
    compare_deal_timelines,
    dump_performa_object,
    extract_component_timelines,
    format_performa_object,
    validate_deal_parity,
)
from performa.valuation import DirectCapValuation


class TestPolymorphicDebugUtility:
    """Test suite for polymorphic debug utilities."""

    def test_dump_timeline_primitive(self):
        """Test debug utility with Timeline primitive object."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=60)

        result = dump_performa_object(timeline)

        # Verify object info
        assert result["_object_info"]["class_name"] == "Timeline"
        assert result["_object_info"]["object_type"] == "Primitive"
        assert "performa.core.primitives" in result["_object_info"]["module"]

        # Verify config extraction
        assert result["config"]["duration_months"] == 60
        assert "start_date" in result["config"]

    def test_dump_global_settings_primitive(self):
        """Test debug utility with GlobalSettings primitive object."""
        settings = GlobalSettings()

        result = dump_performa_object(settings, exclude_defaults=False)

        # Verify object info
        assert result["_object_info"]["class_name"] == "GlobalSettings"
        assert result["_object_info"]["object_type"] == "Primitive"

        # Verify config has expected settings
        config_keys = result["config"].keys()
        expected_keys = {"analysis_start_date", "reporting", "calculation"}
        assert expected_keys.issubset(config_keys)

    def test_dump_residential_pattern(self):
        """Test debug utility with ResidentialDevelopmentPattern."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Residential",
            acquisition_date=date(2024, 1, 1),
            land_cost=8_000_000,
            total_units=120,
            unit_mix=[
                {"unit_type": "1BR", "count": 60, "avg_sf": 650, "target_rent": 1500},
                {"unit_type": "2BR", "count": 60, "avg_sf": 850, "target_rent": 1800},
            ],
            construction_cost_per_unit=160_000,
            construction_ltc_ratio=0.70,
            permanent_ltv_ratio=0.75,
            hold_period_years=7,
            exit_cap_rate=0.05,
        )

        result = dump_performa_object(pattern, include_computed=True)

        # Verify object info
        assert result["_object_info"]["class_name"] == "ResidentialDevelopmentPattern"
        assert result["_object_info"]["object_type"] == "Pattern"

        # Verify config extraction
        assert result["config"]["project_name"] == "Test Residential"
        assert result["config"]["total_units"] == 120
        assert result["config"]["land_cost"] == 8_000_000

        # Verify computed properties
        assert "_computed" in result["config"]
        computed = result["config"]["_computed"]
        assert "total_project_cost" in computed
        assert (
            computed["total_project_cost"] == 31_184_000
        )  # Updated: includes developer fee (5% of construction)
        assert "derived_timeline" in computed
        assert (
            computed["derived_timeline"]["duration_months"] == 123
        )  # 3 (start) + 18 (construction) + 18 (lease-up) + 84 (hold)

    def test_dump_stabilized_pattern(self):
        """Test debug utility with StabilizedAcquisitionPattern."""
        pattern = StabilizedAcquisitionPattern(
            property_name="Test Stabilized",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=12_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1000,
            hold_period_years=5,
            exit_cap_rate=0.065,
            ltv_ratio=0.75,  # Fixed: Use ltv_ratio instead of loan_amount (9M / 12M = 75%)
            interest_rate=0.055,
        )

        result = dump_performa_object(pattern, include_computed=True)

        # Verify object info
        assert result["_object_info"]["class_name"] == "StabilizedAcquisitionPattern"
        assert result["_object_info"]["object_type"] == "Pattern"

        # Verify config extraction
        assert result["config"]["property_name"] == "Test Stabilized"
        assert result["config"]["acquisition_price"] == 12_000_000
        assert result["config"]["current_avg_rent"] == 1000

    def test_dump_financing_plan(self):
        """Test debug utility with FinancingPlan construct."""
        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Test Construction",
                "loan_amount": 15_000_000,
                "interest_rate": 0.065,
                "loan_term_years": 2,
            },
            permanent_terms={
                "name": "Test Permanent",
                "loan_amount": 18_000_000,
                "interest_rate": 0.055,
                "loan_term_years": 10,
            },
        )

        result = dump_performa_object(financing_plan)

        # Verify object info
        assert result["_object_info"]["class_name"] == "FinancingPlan"
        assert result["_object_info"]["object_type"] == "Debt"

        # Verify config extraction
        assert result["config"]["name"] == "Construction-to-Permanent"
        assert "facilities" in result["config"]
        assert len(result["config"]["facilities"]) == 2

        # Verify facility class information (check if _class_name exists)
        facilities = result["config"]["facilities"]
        if facilities and "_class_name" in facilities[0]:
            facility_classes = [f["_class_name"] for f in facilities]
            assert "ConstructionFacility" in facility_classes
            assert "PermanentFacility" in facility_classes
        else:
            # Fallback: verify we have 2 facilities with loan amounts
            assert len(facilities) == 2
            assert all("loan_amount" in f for f in facilities)

    def test_dump_valuation_object(self):
        """Test debug utility with DirectCapValuation object."""
        valuation = DirectCapValuation(
            name="Test Valuation",
            cap_rate=0.06,
            hold_period_months=60,
            transaction_costs_rate=0.025,
            noi_basis_kind="LTM",
        )

        result = dump_performa_object(
            valuation, exclude_defaults=False
        )  # Include defaults to see all fields

        # Verify object info
        assert result["_object_info"]["class_name"] == "DirectCapValuation"
        assert result["_object_info"]["object_type"] == "Valuation"

        # Verify config extraction
        assert result["config"]["name"] == "Test Valuation"
        assert result["config"]["cap_rate"] == 0.06
        # Use exclude_defaults=False to ensure noi_basis_kind appears
        assert "noi_basis_kind" in result["config"]


class TestObjectClassification:
    """Test the object classification system."""

    def test_classify_deal_object(self):
        """Test classification of Deal objects."""

        # Create a simple mock that inherits from Deal for isinstance check
        class MockDeal(Deal):
            def __init__(self):
                # Skip validation by not calling super().__init__()
                pass

        mock_deal = MockDeal()

        result = _classify_performa_object(mock_deal)
        assert result == "Deal"

    def test_classify_pattern_objects(self):
        """Test classification of Pattern objects."""

        class TestPattern:
            pass

        mock_pattern = Mock()
        mock_pattern.__class__.__name__ = "ResidentialDevelopmentPattern"

        result = _classify_performa_object(mock_pattern)
        assert result == "Pattern"

    def test_classify_asset_objects(self):
        """Test classification of Asset objects."""
        mock_asset = Mock()
        mock_asset.__class__.__name__ = "ResidentialProperty"

        result = _classify_performa_object(mock_asset)
        assert result == "Asset"

        mock_project = Mock()
        mock_project.__class__.__name__ = "DevelopmentProject"

        result = _classify_performa_object(mock_project)
        assert result == "Asset"

    def test_classify_debt_objects(self):
        """Test classification of Debt objects."""
        mock_facility = Mock()
        mock_facility.__class__.__name__ = "PermanentFacility"

        result = _classify_performa_object(mock_facility)
        assert result == "Debt"

        mock_plan = Mock()
        mock_plan.__class__.__name__ = "FinancingPlan"

        result = _classify_performa_object(mock_plan)
        assert result == "Debt"

    def test_classify_valuation_objects(self):
        """Test classification of Valuation objects."""
        mock_valuation = Mock()
        mock_valuation.__class__.__name__ = "DirectCapValuation"

        result = _classify_performa_object(mock_valuation)
        assert result == "Valuation"

    def test_classify_partnership_objects(self):
        """Test classification of Partnership objects."""
        mock_partnership = Mock()
        mock_partnership.__class__.__name__ = "PartnershipStructure"

        result = _classify_performa_object(mock_partnership)
        assert result == "Partnership"

    def test_classify_unknown_objects(self):
        """Test classification of unknown objects."""
        mock_unknown = Mock()
        mock_unknown.__class__.__name__ = "SomeRandomClass"

        result = _classify_performa_object(mock_unknown)
        assert result == "Unknown"


class TestObjectHandlers:
    """Test specific object type handlers."""

    def test_handle_primitive_object(self):
        """Test handling of primitive objects."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=36)

        result = _handle_primitive_object(
            timeline, exclude_defaults=True, exclude_unset=False
        )

        assert "duration_months" in result
        assert result["duration_months"] == 36
        assert "start_date" in result

    def test_handle_pydantic_object_with_computed(self):
        """Test handling of Pydantic objects with computed properties."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Test Pattern",
            acquisition_date=date(2024, 1, 1),
            land_cost=5_000_000,
            total_units=100,
            unit_mix=[
                {"unit_type": "1BR", "count": 100, "avg_sf": 650, "target_rent": 1500}
            ],
            construction_cost_per_unit=150_000,
            construction_ltc_ratio=0.70,
            permanent_ltv_ratio=0.75,
            hold_period_years=5,
            exit_cap_rate=0.055,
        )

        result = _handle_pydantic_object(
            pattern, exclude_defaults=True, exclude_unset=False, include_computed=True
        )

        # Verify basic config
        assert result["project_name"] == "Test Pattern"
        assert result["total_units"] == 100

        # Verify computed properties
        assert "_computed" in result
        computed = result["_computed"]
        assert "total_project_cost" in computed
        assert "derived_timeline" in computed

    def test_handle_financing_plan(self):
        """Test handling of FinancingPlan objects."""
        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Test Construction",
                "loan_amount": 10_000_000,
                "interest_rate": 0.07,
                "loan_term_years": 2,
            },
            permanent_terms={
                "name": "Test Permanent",
                "loan_amount": 12_000_000,
                "interest_rate": 0.055,
                "loan_term_years": 10,
            },
        )

        result = _handle_financing_plan(
            financing_plan, exclude_defaults=True, exclude_unset=False
        )

        # Verify basic structure
        assert "_class_name" in result
        assert result["_class_name"] == "FinancingPlan"
        assert "facilities" in result
        assert len(result["facilities"]) == 2

        # Verify facility class information
        facility_classes = [f["_class_name"] for f in result["facilities"]]
        assert "ConstructionFacility" in facility_classes
        assert "PermanentFacility" in facility_classes

    def test_handle_generic_object(self):
        """Test fallback handler for unknown objects."""

        class UnknownObject:
            def __init__(self):
                self.some_attr = "test_value"
                self.numeric_attr = 42

        obj = UnknownObject()

        result = _handle_generic_object(obj, exclude_defaults=True, exclude_unset=False)

        assert "_note" in result
        assert "UnknownObject" in result["_note"]
        # Should extract basic attributes
        assert "some_attr" in result
        assert result["some_attr"] == "test_value"
        assert "numeric_attr" in result
        assert result["numeric_attr"] == 42


class TestFormattingUtilities:
    """Test formatted output utilities."""

    def test_format_performa_object_with_timeline(self):
        """Test formatted output for Timeline objects."""
        timeline = Timeline(start_date=date(2024, 6, 1), duration_months=48)

        formatted = format_performa_object(timeline, "Custom Timeline")

        # Verify structure
        assert "# Custom Timeline" in formatted
        assert "## Object Information" in formatted
        assert "Timeline" in formatted
        assert "Primitive" in formatted
        assert "48" in formatted  # duration_months

    def test_format_performa_object_with_pattern(self):
        """Test formatted output for Pattern objects."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Format Test Project",
            acquisition_date=date(2024, 1, 1),
            land_cost=6_000_000,
            total_units=80,
            unit_mix=[
                {"unit_type": "Studio", "count": 80, "avg_sf": 500, "target_rent": 1200}
            ],
            construction_cost_per_unit=140_000,
            construction_ltc_ratio=0.75,
            permanent_ltv_ratio=0.80,
            hold_period_years=6,
            exit_cap_rate=0.055,
        )

        formatted = format_performa_object(pattern)

        # Verify structure and content
        assert "ResidentialDevelopmentPattern (Pattern)" in formatted
        assert "## Object Information" in formatted
        assert "## Configuration" in formatted
        assert "Format Test Project" in formatted
        assert "80" in formatted  # total_units
        assert "$6,000,000" in formatted  # land_cost

    def test_format_performa_object_auto_title(self):
        """Test auto-title generation for formatted output."""
        settings = GlobalSettings()

        formatted = format_performa_object(settings)  # No custom title

        # Should auto-generate title from class and type
        assert "GlobalSettings (Primitive)" in formatted


class TestParameterHandling:
    """Test parameter handling and edge cases."""

    def test_exclude_defaults_parameter(self):
        """Test exclude_defaults parameter functionality."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=24)

        # With exclude_defaults=True (default)
        result_excluded = dump_performa_object(timeline, exclude_defaults=True)

        # With exclude_defaults=False
        result_included = dump_performa_object(timeline, exclude_defaults=False)

        # Should have more keys when including defaults
        excluded_keys = set(result_excluded["config"].keys())
        included_keys = set(result_included["config"].keys())
        assert included_keys >= excluded_keys  # Should have at least as many keys

    def test_exclude_unset_parameter(self):
        """Test exclude_unset parameter functionality."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Minimal Pattern",
            acquisition_date=date(2024, 1, 1),
            land_cost=5_000_000,
            total_units=50,
            unit_mix=[
                {"unit_type": "1BR", "count": 50, "avg_sf": 650, "target_rent": 1400}
            ],
            construction_cost_per_unit=150_000,
            # Minimal required parameters only
        )

        # With exclude_unset=True
        result_unset_excluded = dump_performa_object(pattern, exclude_unset=True)

        # With exclude_unset=False
        result_unset_included = dump_performa_object(pattern, exclude_unset=False)

        # Should have fewer keys when excluding unset
        excluded_keys = set(result_unset_excluded["config"].keys())
        included_keys = set(result_unset_included["config"].keys())
        assert excluded_keys <= included_keys  # Should have fewer or equal keys

    def test_include_computed_parameter(self):
        """Test include_computed parameter functionality."""
        pattern = ResidentialDevelopmentPattern(
            project_name="Computed Test",
            acquisition_date=date(2024, 1, 1),
            land_cost=4_000_000,
            total_units=60,
            unit_mix=[
                {"unit_type": "2BR", "count": 60, "avg_sf": 800, "target_rent": 1600}
            ],
            construction_cost_per_unit=160_000,
            construction_ltc_ratio=0.70,
            permanent_ltv_ratio=0.75,
            hold_period_years=5,
            exit_cap_rate=0.06,
        )

        # Without computed properties
        result_no_computed = dump_performa_object(pattern, include_computed=False)

        # With computed properties
        result_with_computed = dump_performa_object(pattern, include_computed=True)

        # Should have _computed section when included
        assert "_computed" not in result_no_computed["config"]
        assert "_computed" in result_with_computed["config"]

        computed = result_with_computed["config"]["_computed"]
        assert "total_project_cost" in computed
        assert "derived_timeline" in computed

    def test_include_class_info_parameter(self):
        """Test include_class_info parameter functionality."""
        timeline = Timeline(start_date=date(2024, 1, 1), duration_months=12)

        # With class info (default)
        result_with_class = dump_performa_object(timeline, include_class_info=True)

        # Without class info
        result_no_class = dump_performa_object(timeline, include_class_info=False)

        # Should have _object_info when included
        assert "_object_info" in result_with_class
        assert "_object_info" not in result_no_class

        # Verify _object_info structure
        obj_info = result_with_class["_object_info"]
        assert "class_name" in obj_info
        assert "module" in obj_info
        assert "object_type" in obj_info


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_dump_none_object(self):
        """Test handling of None object."""
        result = dump_performa_object(None)

        # Should handle gracefully
        assert "_object_info" in result
        assert result["_object_info"]["class_name"] == "NoneType"

    def test_dump_non_pydantic_object(self):
        """Test handling of non-Pydantic objects."""

        class SimpleClass:
            def __init__(self):
                self.value = 100
                self.name = "test"

        obj = SimpleClass()
        result = dump_performa_object(obj)

        # Should use generic handler
        assert "_object_info" in result
        assert result["_object_info"]["class_name"] == "SimpleClass"
        assert result["_object_info"]["object_type"] == "Unknown"

        # Should extract simple attributes
        assert "value" in result["config"]
        assert "name" in result["config"]

    def test_format_object_with_missing_config(self):
        """Test formatting when configuration is minimal."""
        mock_obj = Mock()
        mock_obj.__class__.__name__ = "MockObject"
        mock_obj.model_dump = Mock(return_value={})

        formatted = format_performa_object(mock_obj)

        # Should handle gracefully without crashing
        assert "MockObject" in formatted
        assert "## Object Information" in formatted


class TestCashOutRefinancingValidation:
    """Test the debug utility's ability to validate cash-out refinancing scenarios."""

    def test_construction_to_permanent_cash_out_detection(self):
        """Test detection and analysis of cash-out refinancing in development deals."""
        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Development Construction",
                "loan_amount": 20_000_000,  # $20M construction
                "interest_rate": 0.065,
                "loan_term_years": 2,
            },
            permanent_terms={
                "name": "Stabilized Permanent",
                "loan_amount": 25_000_000,  # $25M permanent (cash-out scenario)
                "interest_rate": 0.055,
                "loan_term_years": 10,
            },
        )

        result = dump_performa_object(financing_plan)

        # Extract facility information (handle missing _class_name gracefully)
        facilities = result["config"]["facilities"]

        # Try to identify by class name, fall back to loan amount order
        if facilities and "_class_name" in facilities[0]:
            construction_facility = next(
                f for f in facilities if f["_class_name"] == "ConstructionFacility"
            )
            permanent_facility = next(
                f for f in facilities if f["_class_name"] == "PermanentFacility"
            )
        else:
            # Fallback: assume first is construction, second is permanent
            construction_facility = facilities[0]
            permanent_facility = facilities[1]

        # Validate cash-out calculation
        construction_amount = construction_facility["loan_amount"]
        permanent_amount = permanent_facility["loan_amount"]
        cash_out = permanent_amount - construction_amount

        assert construction_amount == 20_000_000
        assert permanent_amount == 25_000_000
        assert cash_out == 5_000_000  # $5M cash-out
        assert cash_out > 0  # Confirms cash-out refinancing

    def test_no_cash_out_scenario_detection(self):
        """Test detection when no cash-out occurs (same loan amounts)."""
        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "No Cash-Out Construction",
                "loan_amount": 15_000_000,
                "interest_rate": 0.065,
                "loan_term_years": 2,
            },
            permanent_terms={
                "name": "No Cash-Out Permanent",
                "loan_amount": 15_000_000,  # Same amount (no cash-out)
                "interest_rate": 0.055,
                "loan_term_years": 10,
            },
        )

        result = dump_performa_object(financing_plan)

        # Extract and validate (handle missing _class_name gracefully)
        facilities = result["config"]["facilities"]

        if facilities and "_class_name" in facilities[0]:
            construction_facility = next(
                f for f in facilities if f["_class_name"] == "ConstructionFacility"
            )
            permanent_facility = next(
                f for f in facilities if f["_class_name"] == "PermanentFacility"
            )
        else:
            # Fallback: assume first is construction, second is permanent
            construction_facility = facilities[0]
            permanent_facility = facilities[1]

        cash_out = (
            permanent_facility["loan_amount"] - construction_facility["loan_amount"]
        )
        assert cash_out == 0  # No cash-out

    def test_debug_utility_guides_financing_analysis(self):
        """Test that debug utility provides clear guidance for financing analysis."""
        # Create a realistic development financing scenario
        financing_plan = create_construction_to_permanent_plan(
            construction_terms={
                "name": "Institutional Development",
                "loan_amount": 30_000_000,
                "interest_rate": 0.07,
                "loan_term_years": 3,
            },
            permanent_terms={
                "name": "Institutional Permanent",
                "loan_amount": 40_000_000,  # Significant cash-out
                "interest_rate": 0.06,
                "loan_term_years": 12,
            },
        )

        # Test both raw and formatted output
        raw_result = dump_performa_object(financing_plan)
        formatted_result = format_performa_object(
            financing_plan, "Development Financing Analysis"
        )

        # Raw result should provide structured data for calculations
        facilities = raw_result["config"]["facilities"]

        # Handle missing _class_name gracefully
        if facilities and "_class_name" in facilities[0]:
            construction_amount = next(
                f["loan_amount"]
                for f in facilities
                if f["_class_name"] == "ConstructionFacility"
            )
            permanent_amount = next(
                f["loan_amount"]
                for f in facilities
                if f["_class_name"] == "PermanentFacility"
            )
        else:
            # Fallback: assume order is construction, then permanent
            construction_amount = facilities[0]["loan_amount"]
            permanent_amount = facilities[1]["loan_amount"]
        cash_out = permanent_amount - construction_amount

        assert cash_out == 10_000_000  # $10M cash-out

        # Formatted result should be human-readable
        assert "Development Financing Analysis" in formatted_result
        assert "FinancingPlan" in formatted_result
        assert "ConstructionFacility" in formatted_result
        assert "PermanentFacility" in formatted_result
        assert "$30,000,000" in formatted_result  # Construction amount
        assert "$40,000,000" in formatted_result  # Permanent amount

    def test_compare_deal_timelines(self):
        """Test timeline comparison utility."""
        # Create two patterns with different hold periods
        pattern1 = StabilizedAcquisitionPattern(
            property_name="Timeline Test A",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
            hold_period_years=5,
        )

        pattern2 = StabilizedAcquisitionPattern(
            property_name="Timeline Test B",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
            hold_period_years=7,  # Different hold period
        )

        deal1 = pattern1.create()
        deal2 = pattern2.create()

        result = compare_deal_timelines(deal1, deal2)

        # Should detect timeline differences
        assert isinstance(result, dict)
        assert "has_mismatches" in result
        assert "differences" in result
        assert "summary" in result

    def test_compare_deal_configurations(self):
        """Test configuration comparison utility."""
        pattern1 = StabilizedAcquisitionPattern(
            property_name="Config Test A",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
            exit_cap_rate=0.065,
        )

        pattern2 = StabilizedAcquisitionPattern(
            property_name="Config Test B",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
            exit_cap_rate=0.070,  # Different exit cap rate
        )

        deal1 = pattern1.create()
        deal2 = pattern2.create()

        result = compare_deal_configurations(deal1, deal2)

        assert isinstance(result, dict)
        assert "differences" in result
        assert "all_differences" in result  # Backward compatibility alias
        assert "has_differences" in result
        assert "impact_assessment" in result

    def test_deal_parity_validation(self):
        """Test deal parity validation utility."""
        # Create two similar patterns
        pattern1 = StabilizedAcquisitionPattern(
            property_name="Parity Test A",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
        )

        pattern2 = StabilizedAcquisitionPattern(
            property_name="Parity Test B",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
        )

        # Should be identical - test perfect parity
        results1 = pattern1.analyze()
        results2 = pattern2.analyze()

        parity = validate_deal_parity(results1, results2)

        assert isinstance(parity, dict)
        assert "passes" in parity
        assert "parity_level" in parity
        assert "summary" in parity
        assert "recommended_fixes" in parity

        # Should achieve parity
        assert parity["passes"] or parity["parity_level"] in ["perfect", "excellent"]

    def test_ledger_shape_analysis(self):
        """Test ledger shape analysis utility."""
        pattern = StabilizedAcquisitionPattern(
            property_name="Shape Test",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
        )

        results = pattern.analyze()
        shape = analyze_ledger_shape(results)

        assert isinstance(shape, dict)
        assert "transaction_summary" in shape
        assert "flow_summary" in shape
        assert "timeline_coverage" in shape
        assert "warnings" in shape

        # Should have reasonable transaction counts
        assert shape["transaction_summary"]["total_count"] > 100

    def test_component_timeline_extraction(self):
        """Test component timeline extraction utility."""
        pattern = StabilizedAcquisitionPattern(
            property_name="Timeline Extract Test",
            acquisition_date=date(2024, 1, 1),
            acquisition_price=10_000_000,
            total_units=100,
            avg_unit_sf=800,
            current_avg_rent=1200,
            hold_period_years=5,
        )

        deal = pattern.create()
        timelines = extract_component_timelines(deal)

        assert isinstance(timelines, dict)
        assert "misalignment_warnings" in timelines
        assert "summary" in timelines

        # Should extract multiple component timelines
        timeline_components = [
            k
            for k, v in timelines.items()
            if isinstance(v, dict) and "duration_months" in v
        ]
        assert len(timeline_components) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
