#!/usr/bin/env python3
"""
Basic Office Development Example

This script demonstrates Performa's reporting functionality with a complete office
development project showcasing the library's core capabilities.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from performa.asset.office import (
    DirectLeaseTerms,
    EqualSpreadPace,
    OfficeAbsorptionPlan,
    OfficeDevelopmentBlueprint,
    OfficeVacantSuite,
    SpaceFilter,
)
from performa.core.capital import CapitalItem, CapitalPlan
from performa.core.primitives import (
    AssetTypeEnum,
    FirstOnlyDrawSchedule,
    LeaseTypeEnum,
    ProgramUseEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)
from performa.development import DevelopmentProject
from performa.reporting import (
    create_development_summary,
    create_draw_request,
    create_leasing_status_report,
    create_sources_and_uses_report,
)


def create_sample_development_project():
    """Create a sample office development project demonstrating Performa components"""
    
    # Create project timeline (24-month development period)
    start_date = date(2024, 1, 1)
    timeline = Timeline(start_date=start_date, duration_months=24)
    
    # Define capital expenditure plan with construction costs
    capital_items = [
        CapitalItem(
            name="Land Acquisition",
            work_type="land",
            value=5_000_000,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
        ),
        CapitalItem(
            name="Construction - Core & Shell",
            work_type="construction",
            value=15_000_000,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
        ),
        CapitalItem(
            name="Professional Fees",
            work_type="soft_costs",
            value=1_500_000,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
        ),
        CapitalItem(
            name="Developer Fee",
            work_type="developer",
            value=2_000_000,
            unit_of_measure=UnitOfMeasureEnum.CURRENCY,
            draw_schedule=FirstOnlyDrawSchedule(),
            timeline=timeline
        ),
    ]
    
    capital_plan = CapitalPlan(name="Office Development Plan", capital_items=capital_items)
    
    # Define vacant office space inventory for lease-up
    vacant_suites = [
        OfficeVacantSuite(
            suite="Floor 1",
            floor="1",
            area=15000.0,  # 15,000 SF
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,  # Average 5,000 SF per lease
            subdivision_minimum_lease_area=2500.0   # Minimum 2,500 SF
        ),
        OfficeVacantSuite(
            suite="Floor 2",
            floor="2", 
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0
        ),
        OfficeVacantSuite(
            suite="Floor 3",
            floor="3",
            area=15000.0,
            use_type=ProgramUseEnum.OFFICE,
            is_divisible=True,
            subdivision_average_lease_area=5000.0,
            subdivision_minimum_lease_area=2500.0
        ),
    ]
    
    # Define market absorption plan for space lease-up
    absorption_plan = OfficeAbsorptionPlan.with_typical_assumptions(
        name="Metro Tower Lease-Up Plan",
        space_filter=SpaceFilter(
            floors=["1", "2", "3"],
            use_types=[ProgramUseEnum.OFFICE]
        ),
        start_date_anchor=date(2025, 6, 1),  # Start leasing 6 months after construction start
        pace=EqualSpreadPace(
            type="EqualSpread",
            total_deals=9,       # 9 deals over lease-up period
            frequency_months=2   # New deal every 2 months (18 months / 9 deals)
        ),
        leasing_assumptions=DirectLeaseTerms(
            base_rent_value=35.0,  # $35/SF
            base_rent_unit_of_measure=UnitOfMeasureEnum.PER_UNIT,
            term_months=84,  # 7-year leases
            upon_expiration=UponExpirationEnum.MARKET
        )
    )
    
    # Create development blueprint combining space and absorption plan
    office_blueprint = OfficeDevelopmentBlueprint(
        name="Metro Office Tower",
        vacant_inventory=vacant_suites,
        absorption_plan=absorption_plan
    )
    
    # Create the development project
    project = DevelopmentProject(
        name="Metro Office Tower Development",
        property_type=AssetTypeEnum.OFFICE,
        gross_area=50000.0,  # 50,000 SF gross (includes common areas)
        net_rentable_area=45000.0,  # 45,000 SF rentable
        construction_plan=capital_plan,
        blueprints=[office_blueprint]
    )
    
    return project


def main():
    """Run the office development example and generate reports"""
    print("🏢 Performa Office Development Example")
    print("=" * 50)
    
    # Initialize development project
    try:
        project = create_sample_development_project()
        print(f"✅ Created project: {project.name}")
        print(f"   Total Development Cost: ${project.construction_plan.total_cost:,.0f}")
        print(f"   Net Rentable Area: {project.net_rentable_area:,.0f} SF")
        print(f"   Number of Blueprints: {len(project.blueprints)}")
    except Exception as e:
        print(f"❌ Failed to create development project: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test Sources & Uses Report
    print("\n📊 Generating Sources & Uses Report...")
    try:
        sources_uses_report = create_sources_and_uses_report(project)
        report_data = sources_uses_report.generate_data()
        
        print("   Project Info:")
        for key, value in report_data["project_info"].items():
            print(f"     {key}: {value}")
        
        print("   Uses Summary:")
        for key, value in report_data["uses"].items():
            print(f"     {key}: {value}")
            
        print("✅ Sources & Uses Report generated successfully")
    except Exception as e:
        print(f"❌ Sources & Uses Report failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Development Summary Report
    print("\n📈 Generating Development Summary...")
    try:
        summary_report = create_development_summary(project)
        summary_data = summary_report.generate_data()
        
        print("   Financial Summary:")
        for key, value in summary_data["financial_summary"].items():
            print(f"     {key}: {value}")
            
        print("✅ Development Summary generated successfully")
    except Exception as e:
        print(f"❌ Development Summary failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Construction Draw Report
    print("\n🏗️ Generating Construction Draw Request...")
    try:
        draw_period = date(2024, 6, 1)
        draw_report = create_draw_request(project, draw_period)
        draw_data = draw_report.generate_data()
        
        print("   Draw Header:")
        for key, value in draw_data["draw_header"].items():
            print(f"     {key}: {value}")
            
        print("✅ Construction Draw Request generated successfully")
    except Exception as e:
        print(f"❌ Construction Draw Request failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Leasing Status Report
    print("\n🏢 Generating Leasing Status Report...")
    try:
        status_date = date(2025, 9, 1)
        leasing_report = create_leasing_status_report(project, status_date)
        leasing_data = leasing_report.generate_data()
        
        print("   Leasing Summary:")
        for key, value in leasing_data["leasing_summary"].items():
            print(f"     {key}: {value}")
            
        print("✅ Leasing Status Report generated successfully")
    except Exception as e:
        print(f"❌ Leasing Status Report failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n🎉 All reporting functionality working!")
    print("📋 Example completed successfully!")


if __name__ == "__main__":
    main() 