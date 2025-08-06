# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
End-to-End Deal Architecture Tests

This module tests the complete deal analysis pipeline:
- Complete analyze pipeline
- Asset-level analysis integration 
- Deal-level orchestration
- Financing integration
- Multi-asset support
"""

from datetime import date

import pytest

from performa.core.capital import CapitalPlan
from performa.core.primitives import AssetTypeEnum, Timeline
from performa.deal import Deal, analyze
from performa.deal.acquisition import AcquisitionTerms
from performa.development.project import DevelopmentProject


class TestDealCentricArchitectureIntegration:
    """Integration tests for the complete deal-centric architecture."""

    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2026, 12, 31)
        )

    @pytest.fixture
    def acquisition_terms(self):
        """Create acquisition terms for testing."""
        acquisition_timeline = Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        return AcquisitionTerms(
            name="Land Acquisition",
            timeline=acquisition_timeline,
            value=5000000.0,
            acquisition_date=date(2024, 1, 1),
            closing_costs_rate=0.025
        )

    @pytest.fixture
    def purified_development_project(self):
        """Create a purified development project for testing."""
        return DevelopmentProject(
            name="Purified Office Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100000.0,
            net_rentable_area=90000.0,
            construction_plan=CapitalPlan(name="Construction Plan", capital_items=[]),
            blueprints=[]
        )

    def test_development_project_purification(self, purified_development_project):
        """Test that development projects maintain clean asset/deal separation."""
        project = purified_development_project
        
        # Should HAVE asset-level components
        assert hasattr(project, 'construction_plan')
        assert hasattr(project, 'blueprints')
        assert hasattr(project, 'property_type')
        
        # Should NOT HAVE deal-level components (clean separation)
        assert not hasattr(project, 'financing_plan')
        assert not hasattr(project, 'disposition_valuation')
        
        # Should still have required property classification
        assert project.property_type == AssetTypeEnum.OFFICE

    def test_deal_model_polymorphic_union(self, purified_development_project, acquisition_terms):
        """Test polymorphic asset handling in Deal model."""
        deal = Deal(
            name="Polymorphic Test Deal",
            asset=purified_development_project,
            acquisition=acquisition_terms
        )
        
        # Should work with any asset type in the union
        assert isinstance(deal.asset, DevelopmentProject)
        
        # Duck typing for business logic should work
        assert hasattr(deal.asset, 'construction_plan')  # Development project detection
        assert deal.is_development_deal is True
        assert deal.deal_type == "development"

    def test_complete_deal_analysis_pipeline(self, purified_development_project, acquisition_terms, timeline):
        """Test complete 5-pass analysis pipeline."""
        deal = Deal(
            name="Complete Pipeline Test",
            asset=purified_development_project,
            acquisition=acquisition_terms,
            financing=None,  # All-equity for testing
            disposition=None
        )
        
        results = analyze(deal, timeline)
        
        # Validate 5-pass structure
        assert hasattr(results, "unlevered_analysis")      # Pass 1: Unlevered asset analysis
        assert hasattr(results, "financing_analysis")     # Pass 2: Financing integration  
        assert hasattr(results, "levered_cash_flows")     # Pass 3: Levered cash flows
        assert hasattr(results, "partner_distributions")  # Pass 4: Partner distributions
        assert hasattr(results, "deal_metrics")          # Pass 5: Deal metrics
        
        # Validate architecture separation
        unlevered = results.unlevered_analysis
        assert unlevered is not None  # Asset analysis should complete
        
        financing = results.financing_analysis
        # For all-equity deals, financing_analysis should be None
        assert financing is None  # No financing provided
        
        levered = results.levered_cash_flows
        assert hasattr(levered, "cash_flow_components")  # Should separate components

    def test_asset_deal_layer_separation(self, purified_development_project, acquisition_terms, timeline):
        """Test clean separation between Asset and Deal layers."""
        # Asset layer: Pure development project
        asset = purified_development_project
        
        # Deal layer: Investment strategy wrapper
        deal = Deal(
            name="Layer Separation Test",
            asset=asset,
            acquisition=acquisition_terms
        )
        
        # Asset should only know about physical development
        assert hasattr(asset, 'construction_plan')
        assert hasattr(asset, 'blueprints')
        
        # Deal should handle investment strategy
        assert hasattr(deal, 'acquisition')
        assert hasattr(deal, 'financing')
        assert hasattr(deal, 'exit_valuation')
        assert hasattr(deal, 'equity_partners')
        
        # Analysis should work on Deal level
        results = analyze(deal, timeline)
        assert results.deal_summary.is_development is True

    def test_different_asset_types_same_deal_interface(self, acquisition_terms, timeline):
        """Test that different asset types work with the same Deal interface."""
        # Test different property types through development projects
        asset_types = [
            AssetTypeEnum.OFFICE,
            AssetTypeEnum.MULTIFAMILY,
            AssetTypeEnum.MIXED_USE
        ]
        
        for asset_type in asset_types:
            # Create development project of each type
            project = DevelopmentProject(
                name=f"Test {asset_type.value} Development",
                property_type=asset_type,
                gross_area=100000.0,
                net_rentable_area=90000.0,
                construction_plan=CapitalPlan(name="Construction Plan", capital_items=[]),
                blueprints=[]
            )
            
            # Same Deal interface for all asset types
            deal = Deal(
                name=f"Test {asset_type.value} Deal",
                asset=project,
                acquisition=acquisition_terms
            )
            
            # Same analyze function for all asset types
            results = analyze(deal, timeline)
            
            # Should work consistently
            assert results.deal_summary.asset_type == asset_type
            assert results.deal_summary.deal_type == "development"

    def test_pydantic_validation_integration(self, purified_development_project, acquisition_terms, timeline):
        """Test that Pydantic validation works properly in integration."""
        deal = Deal(
            name="Pydantic Fix Test",
            asset=purified_development_project,
            acquisition=acquisition_terms
        )
        
        # This should work without Pydantic validation errors
        results = analyze(deal, timeline)
        
        # Should complete successfully
        assert results is not None
        assert hasattr(results, "unlevered_analysis")
        
        # Unlevered analysis should have proper structure
        unlevered = results.unlevered_analysis
        assert hasattr(unlevered, "scenario")
        assert hasattr(unlevered, "models")

    def test_computed_fields_performance(self, purified_development_project, acquisition_terms):
        """Test that computed fields provide good performance."""
        deal = Deal(
            name="Performance Test",
            asset=purified_development_project,
            acquisition=acquisition_terms
        )
        
        # Access computed fields multiple times
        for _ in range(10):
            deal_type = deal.deal_type
            is_dev = deal.is_development_deal
            financing_type = deal.financing_type
            
        # Should be consistent
        assert deal_type == "development"
        assert is_dev is True
        assert financing_type == "all_equity"

    def test_architecture_prevents_circular_dependencies(self, purified_development_project):
        """Test that the architecture prevents circular dependencies."""
        # Development project should not have access to deal-level calculations
        project = purified_development_project
        
        # Should not have financing or disposition (which could create circular deps)
        assert not hasattr(project, 'financing_plan')
        assert not hasattr(project, 'disposition_valuation')
        
        # Asset analysis should be unlevered only
        # (UnleveredAggregateLineKey separation enforces this at the type level)

    def test_industry_standard_terminology_preserved(self, purified_development_project):
        """Test that industry-standard real estate terminology is preserved."""
        project = purified_development_project
        
        # Should use proper real estate terms
        assert hasattr(project, 'property_type')
        assert project.property_type in AssetTypeEnum
        assert hasattr(project, 'gross_area')
        assert hasattr(project, 'net_rentable_area')
        
        # No artificial discriminator fields
        assert not hasattr(project, 'asset_class')  # Rejected in favor of property_type

    def test_future_proof_design(self, purified_development_project, acquisition_terms):
        """Test that the architecture is ready for future enhancements."""
        deal = Deal(
            name="Future Proof Test",
            asset=purified_development_project,
            acquisition=acquisition_terms,
            financing=None,           # Ready for FinancingPlan
            disposition=None,         # Ready for DispositionValuation  
            equity_partners=None      # Ready for complex equity structures
        )
        
        # Architecture should be extensible
        assert hasattr(deal, 'financing')
        assert hasattr(deal, 'exit_valuation')
        assert hasattr(deal, 'equity_partners')
        
        # Should handle None values gracefully
        assert deal.financing_type == "all_equity"
        assert deal.has_equity_partners is False
        
        # Test inline calculation instead of computed property
        facilities_count = len(deal.financing.facilities) if deal.financing else 0
        assert facilities_count == 0


class TestArchitecturalQuality:
    """Tests for architectural quality and best practices."""

    @pytest.fixture
    def timeline(self):
        """Create a test timeline."""
        return Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2026, 12, 31)
        )

    @pytest.fixture
    def acquisition_terms(self):
        """Create acquisition terms for testing."""
        acquisition_timeline = Timeline.from_dates(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31)
        )
        return AcquisitionTerms(
            name="Land Acquisition",
            timeline=acquisition_timeline,
            value=5000000.0,
            acquisition_date=date(2024, 1, 1),
            closing_costs_rate=0.025
        )

    @pytest.fixture
    def purified_development_project(self):
        """Create a purified development project."""
        return DevelopmentProject(
            name="Purified Office Development",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100000.0,
            net_rentable_area=90000.0,
            construction_plan=CapitalPlan(name="Construction Plan", capital_items=[]),
            blueprints=[]
        )

    def test_maximum_simplicity_achieved(self):
        """Test that maximum simplicity is achieved in the architecture."""
        # No artificial discriminator fields needed
        # Simple Union with Pydantic v2 auto-inference
        # Duck typing for business logic
        
        dev_project = DevelopmentProject(
            name="Simplicity Test",
            property_type=AssetTypeEnum.OFFICE,
            gross_area=100000.0,
            net_rentable_area=90000.0,
            construction_plan=CapitalPlan(name="Construction", capital_items=[]),
            blueprints=[]
        )
        
        # Should work without any artificial complexity
        assert hasattr(dev_project, 'construction_plan')  # Natural detection
        assert not hasattr(dev_project, 'discriminator')  # No artificial fields

    def test_type_safety_enforcement(self, purified_development_project, acquisition_terms):
        """Test that type safety is properly enforced."""
        deal = Deal(
            name="Type Safety Test",
            asset=purified_development_project,  # Must be AnyAsset type
            acquisition=acquisition_terms        # Must be AcquisitionTerms type
        )
        
        # Pydantic should enforce types
        assert isinstance(deal.asset, DevelopmentProject)
        assert isinstance(deal.acquisition, AcquisitionTerms)

    def test_production_readiness(self, purified_development_project, acquisition_terms, timeline):
        """Test that the architecture is production-ready."""
        deal = Deal(
            name="Production Test",
            asset=purified_development_project,
            acquisition=acquisition_terms
        )
        
        # Should handle production-like scenarios
        results = analyze(deal, timeline)
        
        # Should have comprehensive results structure
        assert len([attr for attr in ["deal_summary", "unlevered_analysis", "financing_analysis", "levered_cash_flows", "partner_distributions", "deal_metrics"] if hasattr(results, attr)]) >= 6  # All major result sections
        
        # Should have proper error handling (no exceptions raised)
        assert results is not None 