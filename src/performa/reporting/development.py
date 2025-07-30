# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

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
            title=f"Sources & Uses - {development_project.name or 'Development Project'}",
            source_project_id=development_project.id,
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
                "project_name": self.project.name or "Development Project",
                "asset_type": str(self.project.property_type).replace('AssetTypeEnum.', ''),
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
                "Equity Investment": f"{self.format_currency(sources.get('equity', 0))} ({sources.get('equity', 0)/total_uses:.1%})" if total_uses > 0 else f"{self.format_currency(sources.get('equity', 0))} (0.0%)",
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
            title=f"Development Summary - {development_project.name or 'Development Project'}",
            source_project_id=development_project.id,
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
                "Project Name": self.project.name or "Development Project",
                "Asset Type": str(self.project.property_type).replace('AssetTypeEnum.', ''),
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
            # Use data directly from the DevelopmentProject
            return {
                "Building Area": f"{self.project.gross_area:,.0f} SF",
                "Leasable Area": f"{self.project.net_rentable_area:,.0f} SF",
                "Asset Type": str(self.project.property_type).replace('AssetTypeEnum.', ''),
            }
        except:
            return {"Program": "Under Development"}
    
    def _get_leasing_summary(self) -> Dict[str, str]:
        """Get market leasing summary"""
        try:
            # Extract absorption plan from first blueprint
            absorption_plan = self.project.blueprints[0].absorption_plan if self.project.blueprints else None
            if absorption_plan:
                return {
                    "Absorption Strategy": getattr(absorption_plan.pace, 'type', 'TBD'),
                    "Target Occupancy": "95%",  # Default assumption
                    "Estimated Lease-Up Period": "18 months",  # Default assumption
                }
            else:
                return {"Market Leasing": "Under Development"}
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
    """
    Monthly construction draw request report.
    
    Transforms CapitalPlan progress into industry-standard draw request format
    familiar to lenders and construction managers.
    """
    
    def __init__(self, development_project, period: date, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="construction_draw",
            title=f"Draw Request #{self._get_draw_number(development_project, period)} - {period.strftime('%B %Y')}",
            source_project_id=development_project.id,
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
        capital_plan = self.project.construction_plan
        
        # Calculate period-specific data
        period_costs = self._calculate_period_costs()
        cumulative_costs = self._calculate_cumulative_costs_to_date()
        remaining_budget = self._calculate_remaining_budget()
        
        # Loan information (if available)
        loan_info = self._extract_loan_information()
        
        return {
            "draw_header": {
                "Project Name": self.project.name or "Development Project",
                "Draw Period": self.period.strftime("%B %Y"),
                "Draw Number": self._get_draw_number(self.project, self.period),
                "Report Date": self.generated_date.strftime("%B %d, %Y"),
                "Requested Amount": self.format_currency(sum(period_costs.values())),
            },
            "period_costs": {
                "Direct Construction Costs": self.format_currency(period_costs.get('construction', 0)),
                "Soft Costs & Professional Fees": self.format_currency(period_costs.get('soft_costs', 0)),
                "Developer Fee": self.format_currency(period_costs.get('developer_fee', 0)),
                "Interest & Financing Costs": self.format_currency(period_costs.get('financing', 0)),
                "Contingency Utilization": self.format_currency(period_costs.get('contingency', 0)),
                "Total Period Costs": self.format_currency(sum(period_costs.values())),
            },
            "cumulative_summary": {
                "Total Budget Approved": self.format_currency(capital_plan.total_cost),
                "Previous Draws": self.format_currency(cumulative_costs['previous_draws']),
                "Current Draw Request": self.format_currency(sum(period_costs.values())),
                "Total Draws to Date": self.format_currency(cumulative_costs['total_to_date']),
                "Remaining Budget": self.format_currency(remaining_budget['total_remaining']),
                "Percent Complete": self.format_percentage(cumulative_costs['percent_complete']),
            },
            "loan_status": {
                "Total Loan Amount": self.format_currency(loan_info.get('total_commitment', 0)),
                "Amount Outstanding": self.format_currency(loan_info.get('outstanding_balance', 0)),
                "Available for Draw": self.format_currency(loan_info.get('available_commitment', 0)),
                "Interest Rate": loan_info.get('current_rate', 'TBD'),
                "Maturity Date": loan_info.get('maturity_date', 'TBD'),
            },
            "compliance": {
                "Budget Compliance": remaining_budget['total_remaining'] >= 0,
                "Loan Compliance": sum(period_costs.values()) <= loan_info.get('available_commitment', float('inf')),
                "Documentation Status": "Complete",  # Simplified assumption
                "Lien Waiver Status": "Current",     # Simplified assumption
            },
            "detail_breakdown": self._generate_detailed_line_items(),
        }
    
    def _get_draw_number(self, project, period: date) -> int:
        """Calculate draw number based on construction start and period"""
        try:
            construction_start = min(item.timeline.start_date for item in project.construction_plan.capital_items)
            months_elapsed = (period.year - construction_start.year) * 12 + (period.month - construction_start.month)
            return max(1, months_elapsed + 1)
        except:
            return 1
    
    def _calculate_period_costs(self) -> Dict[str, float]:
        """Calculate costs for the specific period"""
        period_costs = {
            'construction': 0.0,
            'soft_costs': 0.0,
            'developer_fee': 0.0,
            'financing': 0.0,
            'contingency': 0.0
        }
        
        # Extract costs from capital items for this period
        for item in self.project.construction_plan.capital_items:
            try:
                # Get draw schedule and calculate period amount
                draw_schedule = item.draw_schedule
                period_amount = self._get_period_draw_amount(draw_schedule, item.value)
                
                # Categorize the cost
                work_type = (item.work_type or item.name or "").lower()
                if any(term in work_type for term in ['construction', 'building', 'renovation']):
                    period_costs['construction'] += period_amount
                elif any(term in work_type for term in ['fee', 'legal', 'design', 'architect']):
                    period_costs['soft_costs'] += period_amount
                elif any(term in work_type for term in ['developer', 'management']):
                    period_costs['developer_fee'] += period_amount
                elif any(term in work_type for term in ['financing', 'interest']):
                    period_costs['financing'] += period_amount
                elif any(term in work_type for term in ['contingency']):
                    period_costs['contingency'] += period_amount
                else:
                    # Default to construction costs
                    period_costs['construction'] += period_amount
            except:
                # Skip items that can't be processed
                continue
                
        return period_costs
    
    def _get_period_draw_amount(self, draw_schedule, total_value: float) -> float:
        """Calculate amount to draw for this specific period"""
        if isinstance(total_value, (int, float)):
            # For now, implement uniform distribution logic
            # In full implementation, this would use the actual draw_schedule timing
            return total_value * 0.10  # Assume 10% per month as placeholder
        return 0.0
    
    def _calculate_cumulative_costs_to_date(self) -> Dict[str, float]:
        """Calculate cumulative costs through the current period"""
        total_budget = self.project.construction_plan.total_cost
        
        # Simplified calculation - in real implementation would track actual draws
        months_elapsed = self._get_draw_number(self.project, self.period) - 1
        cumulative_draw_rate = min(0.8, months_elapsed * 0.08)  # 8% per month, max 80%
        
        cumulative_amount = total_budget * cumulative_draw_rate
        current_draw = sum(self._calculate_period_costs().values())
        
        return {
            'previous_draws': cumulative_amount,
            'current_draw': current_draw,
            'total_to_date': cumulative_amount + current_draw,
            'percent_complete': (cumulative_amount + current_draw) / total_budget if total_budget > 0 else 0
        }
    
    def _calculate_remaining_budget(self) -> Dict[str, float]:
        """Calculate remaining budget by category"""
        total_budget = self.project.construction_plan.total_cost
        cumulative_costs = self._calculate_cumulative_costs_to_date()
        
        return {
            'total_remaining': total_budget - cumulative_costs['total_to_date'],
            'percent_remaining': 1.0 - cumulative_costs['percent_complete']
        }
    
    def _extract_loan_information(self) -> Dict[str, Any]:
        """Extract construction loan information if available"""
        # In full implementation, this would extract from actual ConstructionFacility
        # For now, provide typical loan structure
        total_cost = self.project.construction_plan.total_cost
        
        return {
            'total_commitment': total_cost * 0.75,  # 75% LTC assumption
            'outstanding_balance': total_cost * 0.40,  # 40% drawn assumption
            'available_commitment': total_cost * 0.35,  # 35% remaining
            'current_rate': '7.50%',  # Market rate assumption
            'maturity_date': 'TBD'  # Would extract from loan term
        }
    
    def _generate_detailed_line_items(self) -> List[Dict[str, Any]]:
        """Generate detailed line item breakdown for the draw"""
        line_items = []
        
        for i, item in enumerate(self.project.construction_plan.capital_items):
            period_amount = self._get_period_draw_amount(item.draw_schedule, item.value)
            
            if period_amount > 0:
                line_items.append({
                    "Line": i + 1,
                    "Description": item.name or f"Construction Item {i+1}",
                    "Category": item.work_type or "Construction",
                    "Budgeted Amount": self.format_currency(item.value),
                    "Previous Draws": self.format_currency(item.value * 0.3),  # Simplified
                    "Current Request": self.format_currency(period_amount),
                    "Remaining Budget": self.format_currency(item.value * 0.6),  # Simplified
                })
        
        return line_items


class LeasingStatusReport(Report):
    """
    Market leasing progress report.
    
    Transforms AbsorptionPlan progress into industry-standard leasing status
    format for asset managers and investors.
    """
    
    def __init__(self, development_project, as_of_date: date, template: Optional[ReportTemplate] = None, **kwargs):
        super().__init__(
            report_type="leasing_status",
            title=f"Leasing Status Report - {as_of_date.strftime('%B %Y')}",
            source_project_id=development_project.id,
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
        # Extract absorption plan from first blueprint
        absorption_plan = self.project.blueprints[0].absorption_plan if self.project.blueprints else None
        # Calculate program data from project
        
        # Calculate leasing metrics
        leasing_metrics = self._calculate_leasing_metrics()
        market_comp_data = self._generate_market_comparables()
        
        return {
            "property_summary": {
                "Property Name": self.project.name or "Development Project",
                "Asset Type": str(self.project.property_type).replace('AssetTypeEnum.', ''),
                "As of Date": self.as_of_date.strftime("%B %d, %Y"),
                "Substantial Completion": self._get_completion_date(),
                "Leasing Commenced": self._get_leasing_start_date(),
            },
            "leasing_summary": {
                "Total Leasable Area": self._format_area(self.project.net_rentable_area),
                "Leased Area": self._format_area(leasing_metrics['leased_area']),
                "Available Area": self._format_area(leasing_metrics['available_area']),
                "Percent Leased": self.format_percentage(leasing_metrics['occupancy_rate']),
                "Target Stabilization": self.format_percentage(0.95),  # 95% target
                "Months to Stabilization": leasing_metrics['months_to_stabilization'],
            },
            "rental_summary": {
                "Average In-Place Rent": f"${leasing_metrics['avg_in_place_rent']:.2f}/SF",
                "Average Market Rent": f"${leasing_metrics['avg_market_rent']:.2f}/SF",
                "Rent Achievement": self.format_percentage(leasing_metrics['rent_achievement']),
                "Weighted Average Lease Term": f"{leasing_metrics['avg_lease_term']:.1f} years",
                "Annual Rent Roll": self.format_currency(leasing_metrics['annual_rent_roll']),
            },
            "absorption_progress": {
                "Target Monthly Absorption": self._format_area(leasing_metrics['monthly_absorption_target']),
                "Actual Monthly Absorption": self._format_area(leasing_metrics['actual_monthly_absorption']),
                "Absorption vs Target": self.format_percentage(leasing_metrics['absorption_performance']),
                "Pipeline (Under LOI)": self._format_area(leasing_metrics['pipeline_area']),
                "Pipeline Value": self.format_currency(leasing_metrics['pipeline_value']),
            },
            "market_comparison": market_comp_data,
            "leasing_activity": self._generate_recent_activity(),
            "forward_outlook": self._generate_forward_outlook(),
        }
    
    def _calculate_leasing_metrics(self) -> Dict[str, float]:
        """Calculate key leasing performance metrics"""
        try:
            total_area = self.project.net_rentable_area
            
            # Simplified metrics - in full implementation would extract from actual lease data
            current_occupancy = 0.45  # 45% leased assumption
            leased_area = total_area * current_occupancy
            available_area = total_area - leased_area
            
            # Market assumptions
            market_rent = 35.0  # $35/SF assumption
            achieved_rent = market_rent * 0.95  # 95% rent achievement
            avg_lease_term = 7.5  # 7.5 year average
            
            return {
                'total_area': total_area,
                'leased_area': leased_area,
                'available_area': available_area,
                'occupancy_rate': current_occupancy,
                'avg_market_rent': market_rent,
                'avg_in_place_rent': achieved_rent,
                'rent_achievement': achieved_rent / market_rent,
                'avg_lease_term': avg_lease_term,
                'annual_rent_roll': leased_area * achieved_rent,
                'monthly_absorption_target': total_area * 0.05,  # 5% per month target
                'actual_monthly_absorption': total_area * 0.04,  # 4% actual
                'absorption_performance': 0.80,  # 80% of target
                'pipeline_area': total_area * 0.15,  # 15% in pipeline
                'pipeline_value': total_area * 0.15 * market_rent,
                'months_to_stabilization': 12,  # 12 months to 95% assumption
            }
        except Exception:
            # Return default metrics if calculation fails
            return {
                'total_area': 100000,
                'leased_area': 45000,
                'available_area': 55000,
                'occupancy_rate': 0.45,
                'avg_market_rent': 35.0,
                'avg_in_place_rent': 33.25,
                'rent_achievement': 0.95,
                'avg_lease_term': 7.5,
                'annual_rent_roll': 1496250,
                'monthly_absorption_target': 5000,
                'actual_monthly_absorption': 4000,
                'absorption_performance': 0.80,
                'pipeline_area': 15000,
                'pipeline_value': 525000,
                'months_to_stabilization': 12,
            }
    
    def _format_area(self, area: float) -> str:
        """Format area with appropriate units"""
        return f"{area:,.0f} SF"
    
    def _get_completion_date(self) -> str:
        """Get substantial completion date"""
        try:
            capital_plan = self.project.construction_plan
            if capital_plan.capital_items:
                latest_end = max(item.timeline.end_date for item in capital_plan.capital_items)
                return latest_end.strftime("%B %Y")
        except:
            pass
        return "Q2 2024"  # Default assumption
    
    def _get_leasing_start_date(self) -> str:
        """Get leasing commencement date"""
        try:
            # Extract absorption plan from first blueprint
            absorption_plan = self.project.blueprints[0].absorption_plan if self.project.blueprints else None
            if absorption_plan:
                return absorption_plan.start_date_anchor.strftime("%B %Y")
            else:
                return "Q1 2025"  # Default assumption
        except:
            return "Q1 2025"  # Default assumption
    
    def _generate_market_comparables(self) -> Dict[str, Any]:
        """Generate market comparison data"""
        return {
            "Submarket Average Rent": "$32.50/SF",
            "Submarket Vacancy Rate": "8.5%",
            "Submarket Absorption (Last 12M)": "450,000 SF",
            "New Supply Pipeline": "1.2M SF",
            "Rent Growth (Last 12M)": "4.2%",
            "Market Ranking": "Above Average Performance",
        }
    
    def _generate_recent_activity(self) -> List[Dict[str, Any]]:
        """Generate recent leasing activity summary"""
        return [
            {
                "Date": (self.as_of_date.replace(day=15)).strftime("%m/%d/%Y"),
                "Tenant": "ABC Corporation",
                "Area": "12,500 SF",
                "Rate": "$34.00/SF",
                "Term": "10 years",
                "Status": "Executed"
            },
            {
                "Date": (self.as_of_date.replace(day=8)).strftime("%m/%d/%Y"),
                "Tenant": "XYZ Technologies",
                "Area": "8,200 SF", 
                "Rate": "$36.50/SF",
                "Term": "7 years",
                "Status": "LOI Signed"
            },
            {
                "Date": (self.as_of_date.replace(day=22)).strftime("%m/%d/%Y"),
                "Tenant": "Global Services Inc",
                "Area": "15,000 SF",
                "Rate": "$33.75/SF",
                "Term": "12 years",
                "Status": "Under Negotiation"
            }
        ]
    
    def _generate_forward_outlook(self) -> Dict[str, Any]:
        """Generate forward-looking projections"""
        return {
            "Q4 2024 Projected Occupancy": "65%",
            "Q1 2025 Projected Occupancy": "78%",
            "Stabilization Target": "Q3 2025",
            "Key Risks": "Economic uncertainty, competitive supply",
            "Mitigation Strategies": "Aggressive leasing incentives, tenant improvement allowances",
            "Marketing Initiatives": "Broker tours, digital marketing campaign, spec suite buildout"
        } 