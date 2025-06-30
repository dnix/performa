"""
Development-specific reports using industry-standard terminology.

These reports transform Performa's internal development models into
familiar real estate industry formats and language.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from .base import IndustryMetrics, Report, ReportTemplate


class SourcesAndUsesReport(Report):
    """
    Industry-standard Sources & Uses report for development projects.
    
    Transforms CapitalPlan and financing data into the familiar two-column
    Sources & Uses format expected by lenders, investors, and industry professionals.
    """
    
    def __init__(self, development_project, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="sources_and_uses",
            title=f"Sources & Uses - {development_project.property_name or 'Development Project'}",
            source_project_id=development_project.uid,
            template=template,
            **kwargs
        )
        self.project = development_project
    
    @classmethod
    def from_development_project(cls, development_project, template: Optional[ReportTemplate] = None):
        """Factory method to create report from DevelopmentProject"""
        return cls(development_project, template)
    
    def generate_data(self) -> Dict[str, Any]:
        """Generate Sources & Uses in industry-standard format"""
        
        # Extract capital plan (our internal "construction_plan")
        capital_plan = self.project.construction_plan
        
        # Categorize uses from capital items
        uses = self._categorize_project_uses(capital_plan)
        
        # Calculate/extract sources 
        sources = self._categorize_project_sources()
        
        # Calculate key ratios
        total_uses = sum(uses.values())
        total_sources = sum(sources.values())
        
        return {
            "project_info": {
                "project_name": self.project.property_name or "Development Project",
                "asset_type": getattr(self.project.development_program, 'program_type', 'Mixed Use'),
                "report_date": self.generated_date.strftime("%B %d, %Y"),
            },
            "uses": {
                "Land Acquisition": self.format_currency(uses.get('land', 0)),
                "Direct Construction Costs": self.format_currency(uses.get('hard_costs', 0)),
                "Indirect/Soft Costs": self.format_currency(uses.get('soft_costs', 0)),
                "Financing Fees": self.format_currency(uses.get('financing_fees', 0)),
                "Contingency": self.format_currency(uses.get('contingency', 0)),
                "Developer Fee": self.format_currency(uses.get('developer_fee', 0)),
                "Total Project Cost": self.format_currency(total_uses)
            },
            "sources": {
                "Equity Investment": f"{self.format_currency(sources.get('equity', 0))} ({sources.get('equity', 0)/total_uses:.1%})",
                "Senior Construction Loan": f"{self.format_currency(sources.get('senior_debt', 0))}",
                "Mezzanine Financing": f"{self.format_currency(sources.get('mezzanine', 0))}",
                "Government Subsidies": f"{self.format_currency(sources.get('subsidies', 0))}",
                "Total Sources": self.format_currency(total_sources)
            },
            "key_metrics": {
                "Loan-to-Cost (Senior)": self.format_percentage(sources.get('senior_debt', 0) / total_uses if total_uses > 0 else 0),
                "Total Leverage": self.format_percentage((sources.get('senior_debt', 0) + sources.get('mezzanine', 0)) / total_uses if total_uses > 0 else 0),
                "Equity Requirement": self.format_percentage(sources.get('equity', 0) / total_uses if total_uses > 0 else 0),
                "Cost per Unit": self._calculate_cost_per_unit(),
                "Cost per SF": self._calculate_cost_per_sf(),
            },
            "validation": {
                "sources_equal_uses": abs(total_sources - total_uses) < 0.01,
                "variance": total_sources - total_uses
            }
        }
    
    def _categorize_project_uses(self, capital_plan) -> Dict[str, float]:
        """Categorize capital items into industry-standard use categories"""
        uses = {
            'land': 0.0,
            'hard_costs': 0.0,
            'soft_costs': 0.0,
            'financing_fees': 0.0,
            'contingency': 0.0,
            'developer_fee': 0.0
        }
        
        for item in capital_plan.capital_items:
            # Get item value (handle different value types)
            value = item.value if isinstance(item.value, (int, float)) else 0.0
            
            # Categorize based on work_type or name
            work_type = (item.work_type or item.name or "").lower()
            
            if any(term in work_type for term in ['land', 'acquisition', 'purchase']):
                uses['land'] += value
            elif any(term in work_type for term in ['construction', 'building', 'renovation', 'improvement']):
                uses['hard_costs'] += value
            elif any(term in work_type for term in ['fee', 'legal', 'permit', 'design', 'architect']):
                uses['soft_costs'] += value
            elif any(term in work_type for term in ['financing', 'loan', 'interest']):
                uses['financing_fees'] += value
            elif any(term in work_type for term in ['contingency', 'reserve']):
                uses['contingency'] += value
            elif any(term in work_type for term in ['developer', 'management']):
                uses['developer_fee'] += value
            else:
                # Default to hard costs if unclear
                uses['hard_costs'] += value
        
        return uses
    
    def _categorize_project_sources(self) -> Dict[str, float]:
        """Extract/estimate financing sources"""
        # In full implementation, this would extract from ConstructionFacility
        # For now, estimate based on typical financing structure
        
        total_cost = self.project.construction_plan.total_cost
        
        # Default financing structure (could be enhanced with actual facility data)
        return {
            'equity': total_cost * 0.30,      # 30% equity
            'senior_debt': total_cost * 0.65,  # 65% senior debt  
            'mezzanine': total_cost * 0.05,   # 5% mezzanine
            'subsidies': 0.0                  # No subsidies
        }
    
    def _calculate_cost_per_unit(self) -> str:
        """Calculate cost per unit if program includes unit count"""
        try:
            program = self.project.development_program.program_spec
            if hasattr(program, 'total_units'):
                cost_per_unit = self.project.construction_plan.total_cost / program.total_units
                return self.format_currency(cost_per_unit)
        except:
            pass
        return "N/A"
    
    def _calculate_cost_per_sf(self) -> str:
        """Calculate cost per square foot if program includes area"""
        try:
            program = self.project.development_program.program_spec
            if hasattr(program, 'total_area'):
                cost_per_sf = self.project.construction_plan.total_cost / program.total_area
                return f"${cost_per_sf:.0f}/SF"
        except:
            pass
        return "N/A"


class DevelopmentSummaryReport(Report):
    """
    Executive summary report for development projects with key metrics.
    
    Provides high-level project overview using industry-standard terminology
    and metrics familiar to developers, lenders, and investors.
    """
    
    def __init__(self, development_project, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="development_summary", 
            title=f"Development Summary - {development_project.property_name or 'Development Project'}",
            source_project_id=development_project.uid,
            template=template,
            **kwargs
        )
        self.project = development_project
    
    @classmethod
    def from_development_project(cls, development_project, template: Optional[ReportTemplate] = None):
        """Factory method to create report from DevelopmentProject"""
        return cls(development_project, template)
    
    def generate_data(self) -> Dict[str, Any]:
        """Generate development summary with industry metrics"""
        
        # Project basics
        total_cost = self.project.construction_plan.total_cost
        
        # Estimate key metrics (enhanced in full implementation)
        estimated_stabilized_noi = total_cost * 0.06  # 6% development yield assumption
        estimated_value = estimated_stabilized_noi / 0.055  # 5.5% exit cap assumption
        
        return {
            "project_overview": {
                "Project Name": self.project.property_name or "Development Project",
                "Asset Type": getattr(self.project.development_program, 'program_type', 'Mixed Use'),
                "Construction Start": self._get_construction_start_date(),
                "Estimated Completion": self._get_estimated_completion_date(),
                "Development Period": self._get_development_period_months(),
            },
            "financial_summary": {
                "Total Development Cost": self.format_currency(total_cost),
                "Estimated Stabilized NOI": self.format_currency(estimated_stabilized_noi),
                "Estimated Stabilized Value": self.format_currency(estimated_value),
                "Estimated Profit on Cost": self.format_percentage(estimated_stabilized_noi / total_cost),
                "Estimated Development Margin": self.format_currency(estimated_value - total_cost),
            },
            "program_summary": self._get_program_summary(),
            "leasing_summary": self._get_leasing_summary(),
            "construction_summary": self._get_construction_summary(),
        }
    
    def _get_construction_start_date(self) -> str:
        """Get construction start date in readable format"""
        try:
            capital_plan = self.project.construction_plan
            if capital_plan.capital_items:
                earliest_start = min(item.timeline.start_date for item in capital_plan.capital_items)
                return earliest_start.strftime("%B %Y")
        except:
            pass
        return "TBD"
    
    def _get_estimated_completion_date(self) -> str:
        """Get estimated completion date"""
        try:
            capital_plan = self.project.construction_plan
            if capital_plan.capital_items:
                latest_end = max(item.timeline.end_date for item in capital_plan.capital_items)
                return latest_end.strftime("%B %Y")
        except:
            pass
        return "TBD"
    
    def _get_development_period_months(self) -> str:
        """Get total development period"""
        return f"{self.project.construction_plan.duration_months} months"
    
    def _get_program_summary(self) -> Dict[str, str]:
        """Get development program summary with industry terminology"""
        try:
            program = self.project.development_program.program_spec
            if hasattr(program, 'total_units'):
                return {
                    "Unit Count": f"{program.total_units:,} units",
                    "Unit Mix": getattr(program, 'unit_mix_summary', 'Mixed'),
                    "Average Unit Size": getattr(program, 'avg_unit_size', 'TBD'),
                }
            else:
                return {
                    "Building Area": getattr(program, 'total_area', 'TBD'),
                    "Leasable Area": getattr(program, 'leasable_area', 'TBD'),
                    "Parking Spaces": getattr(program, 'parking_spaces', 'TBD'),
                }
        except:
            return {"Program": "Under Development"}
    
    def _get_leasing_summary(self) -> Dict[str, str]:
        """Get market leasing summary"""
        try:
            absorption_plan = self.project.space_absorption_plan
            return {
                "Absorption Strategy": getattr(absorption_plan, 'strategy_type', 'TBD'),
                "Target Occupancy": "95%",  # Default assumption
                "Estimated Lease-Up Period": getattr(absorption_plan, 'absorption_months', 'TBD'),
            }
        except:
            return {"Market Leasing": "Under Development"}
    
    def _get_construction_summary(self) -> Dict[str, str]:
        """Get construction summary"""
        capital_plan = self.project.construction_plan
        
        # Categorize costs
        total_cost = capital_plan.total_cost
        hard_costs = sum(
            item.value for item in capital_plan.capital_items
            if isinstance(item.value, (int, float)) and 
            any(term in (item.work_type or "").lower() for term in ['construction', 'building', 'renovation'])
        )
        
        return {
            "Total Hard Costs": self.format_currency(hard_costs),
            "Total Project Cost": self.format_currency(total_cost),
            "Construction Method": "General Contractor",  # Default assumption
            "Major Phases": f"{len(capital_plan.capital_items)} construction phases"
        }


# Placeholder classes for future implementation
class ConstructionDrawReport(Report):
    """Monthly construction draw request report"""
    
    def __init__(self, development_project, period: date, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="construction_draw",
            title=f"Draw Request - {period.strftime('%B %Y')}",
            source_project_id=development_project.uid,
            as_of_date=period,
            template=template,
            **kwargs
        )
        self.project = development_project
        self.period = period
    
    @classmethod
    def from_development_project(cls, development_project, period: date, template: Optional[ReportTemplate] = None):
        return cls(development_project, period, template)
    
    def generate_data(self) -> Dict[str, Any]:
        """Generate monthly draw request data"""
        return {
            "draw_period": self.period.strftime("%B %Y"),
            "status": "Implementation Pending",
            "note": "Full draw request functionality will be implemented in Phase 3"
        }


class LeasingStatusReport(Report):
    """Market leasing progress report"""
    
    def __init__(self, development_project, as_of_date: date, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="leasing_status",
            title=f"Leasing Status - {as_of_date.strftime('%B %Y')}",
            source_project_id=development_project.uid,
            as_of_date=as_of_date,
            template=template,
            **kwargs
        )
        self.project = development_project
    
    @classmethod
    def from_development_project(cls, development_project, as_of_date: date, template: Optional[ReportTemplate] = None):
        return cls(development_project, as_of_date, template)
    
    def generate_data(self) -> Dict[str, Any]:
        """Generate leasing status report"""
        return {
            "as_of_date": self.as_of_date.strftime("%B %Y"),
            "status": "Implementation Pending", 
            "note": "Full leasing status functionality will be implemented in Phase 2/3"
        } 