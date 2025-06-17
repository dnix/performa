from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

from performa.common.base import LeaseBase, RolloverLeaseTermsBase
from performa.common.primitives import (
    FrequencyEnum,
    LeaseStatusEnum,
    LeaseTypeEnum,
    Timeline,
    UnitOfMeasureEnum,
    UponExpirationEnum,
)

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext


logger = logging.getLogger(__name__)


class CommercialLeaseBase(LeaseBase, ABC):
    
    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        if not self.rent_escalation:
            return base_flow
        rent_with_escalations = base_flow.copy()
        periods = self.timeline.period_index
        if self.rent_escalation:
            start_period = pd.Period(self.rent_escalation.start_date, freq="M")
            mask = periods >= start_period
            if self.rent_escalation.type == "percentage":
                if self.rent_escalation.recurring:
                    freq = self.rent_escalation.frequency_months or 12
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0
                    if self.rent_escalation.is_relative:
                        growth_factor = np.power(
                            1 + (self.rent_escalation.amount / 100), cycles
                        )
                        rent_with_escalations = rent_with_escalations * growth_factor
                    else:
                        growth_factor = np.power(
                            1 + (self.rent_escalation.amount / 100), cycles
                        )
                        escalation_series = base_flow * (growth_factor - 1)
                        rent_with_escalations += escalation_series
                elif self.rent_escalation.is_relative:
                    growth_factor = 1 + (self.rent_escalation.amount / 100)
                    rent_with_escalations[mask] *= growth_factor
                else:
                    growth_factor = self.rent_escalation.amount / 100
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = base_flow[mask] * growth_factor
                    rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "fixed":
                monthly_amount = (
                    self.rent_escalation.amount / 12
                    if self.rent_escalation.unit_of_measure == UnitOfMeasureEnum.CURRENCY
                    else self.rent_escalation.amount
                )
                if self.rent_escalation.recurring:
                    freq = self.rent_escalation.frequency_months or 12
                    months_elapsed = np.array([(p - start_period).n for p in periods])
                    cycles = np.floor(months_elapsed / freq)
                    cycles[~mask] = 0
                    cumulative_increases = cycles * monthly_amount
                    escalation_series = pd.Series(cumulative_increases, index=periods)
                    rent_with_escalations += escalation_series
                else:
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = monthly_amount
                    rent_with_escalations += escalation_series
            elif self.rent_escalation.type == "cpi":
                raise NotImplementedError(
                    "CPI-based escalations are not yet implemented"
                )
        return rent_with_escalations

    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        if not self.rent_abatement:
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        abated_rent_flow = rent_flow.copy()
        abatement_amount_series = pd.Series(0.0, index=rent_flow.index)
        periods = self.timeline.period_index
        lease_start_period = pd.Period(self.lease_start, freq="M")
        abatement_start_month = self.rent_abatement.start_month - 1
        abatement_start_period = lease_start_period + abatement_start_month
        abatement_end_period = abatement_start_period + self.rent_abatement.months
        abatement_mask = (periods >= abatement_start_period) & (
            periods < abatement_end_period
        )
        abatement_reduction = (
            abated_rent_flow[abatement_mask] * self.rent_abatement.abated_ratio
        )
        abated_rent_flow[abatement_mask] -= abatement_reduction
        abatement_amount_series[abatement_mask] = abatement_reduction
        return abated_rent_flow, abatement_amount_series

    def compute_cf(self, context: AnalysisContext) -> Dict[str, pd.Series]:
        """
        Calculates all cash flows for the initial term of a commercial lease.

        This method provides the concrete implementation for the abstract `compute_cf`
        in `LeaseBase`. It orchestrates the calculation of all financial components
        associated with the lease, including:
        1.  Base Rent: Calculated from the lease's `value` and adjusted for frequency and unit of measure.
        2.  Escalations: Applies rent escalations if defined.
        3.  Abatements: Applies rent abatements if defined.
        4.  Recoveries: Computes expense reimbursements by calling the `compute_cf`
            method of its associated `RecoveryMethod` model.
        5.  TI & LC: Computes tenant improvements and leasing commissions by calling the
            `compute_cf` methods of their respective models.

        Returns:
            A dictionary of pandas Series, where each key represents a cash flow
            component (e.g., "base_rent", "recoveries", "ti_allowance").
        """
        # --- Base Rent Calculation ---
        if isinstance(self.value, (int, float)):
            initial_monthly_value = self.value
            if self.frequency == FrequencyEnum.ANNUAL:
                initial_monthly_value /= 12
            if self.unit_of_measure == UnitOfMeasureEnum.PER_UNIT:
                initial_monthly_value *= self.area
            elif self.unit_of_measure == UnitOfMeasureEnum.CURRENCY:
                pass
            else:
                raise NotImplementedError(f"Base rent unit {self.unit_of_measure} not implemented")
            base_rent = pd.Series(initial_monthly_value, index=self.timeline.period_index)
        elif isinstance(self.value, pd.Series):
            base_rent = self.value.copy()
            base_rent = base_rent.reindex(self.timeline.period_index, fill_value=0.0)
        else:
            # Handle other potential value types or raise error
            raise TypeError(f"Unsupported type for lease value: {type(self.value)}")

        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(base_rent_with_escalations)

        # --- Recovery Calculation ---
        recoveries_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            # The new context-based approach, now passing self
            recoveries_cf = self.recovery_method.compute_cf(context=context, lease=self)

            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                lease_start_period = pd.Period(self.lease_start, freq="M")
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = (abatement_start_period + self.rent_abatement.months)
                abatement_mask = (recoveries_cf.index >= abatement_start_period) & (recoveries_cf.index < abatement_end_period)
                recoveries_cf[abatement_mask] *= 1 - self.rent_abatement.abated_ratio

        # --- TI/LC Calculation ---
        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            allowance_cf = self.ti_allowance.compute_cf(context=context)
            ti_cf = allowance_cf.reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            commission_cf = self.leasing_commission.compute_cf(context=context)
            lc_cf = commission_cf.reindex(self.timeline.period_index, fill_value=0.0)

        result = {
            "base_rent": base_rent_final.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "recoveries": recoveries_cf.fillna(0.0),
            "revenue": (base_rent_final + recoveries_cf).fillna(0.0),
            "ti_allowance": ti_cf.fillna(0.0),
            "leasing_commission": lc_cf.fillna(0.0),
            "expenses": (ti_cf + lc_cf).fillna(0.0),
            "net": (base_rent_final + recoveries_cf - ti_cf - lc_cf).fillna(0.0),
        }
        return result

    def project_future_cash_flows(
        self, context: AnalysisContext, recursion_depth: int = 0
    ) -> pd.DataFrame:
        """
        Recursively projects cash flows for this lease and all subsequent rollovers.
        """
        current_cf_dict = self.compute_cf(context)
        all_cfs = [pd.DataFrame(current_cf_dict)]
        
        lease_end_period = self.timeline.end_date
        analysis_end_period = context.timeline.end_date

        if self.rollover_profile and lease_end_period < analysis_end_period:
            action = self.upon_expiration
            profile = self.rollover_profile
            logger.debug(f"Lease '{self.name}' expires {lease_end_period}. Action: {action}. Projecting rollover...")

            downtime_months = 0
            if action in [UponExpirationEnum.MARKET, UponExpirationEnum.VACATE]:
                downtime_months = profile.downtime_months
            
            # This is a bit of a hack since we don't have a real tenant object on lease yet
            # It's sufficient for naming purposes.
            current_tenant_name = self.name.split(' - ')[0]

            next_lease_start_date = (lease_end_period.to_timestamp() + pd.DateOffset(months=downtime_months + 1)).date()

            # Handle Downtime
            if downtime_months > 0:
                downtime_start_date = (lease_end_period + 1).start_time.date()
                downtime_timeline = Timeline(start_date=downtime_start_date, duration_months=downtime_months)
                market_rent_at_downtime = profile._calculate_rent(
                    terms=profile.market_terms, as_of_date=downtime_start_date, global_settings=context.settings
                )
                monthly_vacancy_loss = market_rent_at_downtime * self.area
                vacancy_loss_series = pd.Series(monthly_vacancy_loss, index=downtime_timeline.period_index, name="vacancy_loss")
                all_cfs.append(vacancy_loss_series.to_frame())

            # The Dispatcher Logic
            next_lease_terms: Optional[RolloverLeaseTermsBase] = None
            next_name_suffix: str = ""
            
            if action == UponExpirationEnum.RENEW:
                next_lease_terms = profile.renewal_terms
                next_name_suffix = f" (Renewal {recursion_depth + 1})"
            elif action == UponExpirationEnum.VACATE:
                next_lease_terms = profile.market_terms
                current_tenant_name = f"Market Tenant for {self.suite}" # New tenant
                next_name_suffix = f" (Rollover {recursion_depth + 1})"
            elif action == UponExpirationEnum.MARKET:
                next_lease_terms = profile.blend_lease_terms()
                current_tenant_name = f"Market Tenant for {self.suite}" # New tenant
                next_name_suffix = f" (Rollover {recursion_depth + 1})"
            elif action == UponExpirationEnum.OPTION and profile.option_terms:
                next_lease_terms = profile.option_terms
                next_name_suffix = f" (Option {recursion_depth + 1})"
            elif action == UponExpirationEnum.REABSORB:
                logger.debug(f"Lease '{self.name}' set to REABSORB. Stopping projection chain.")
                # next_lease_terms remains None, stopping the recursion
            
            # Create and recurse if a next step was determined
            if next_lease_terms and pd.Period(next_lease_start_date, freq='M') <= analysis_end_period:
                new_rent_rate = profile._calculate_rent(
                    terms=next_lease_terms, as_of_date=next_lease_start_date, global_settings=context.settings
                )
                speculative_lease = self._create_speculative_lease_instance(
                    start_date=next_lease_start_date,
                    lease_terms=next_lease_terms,
                    rent_rate=new_rent_rate,
                    tenant_name=current_tenant_name,
                    name_suffix=next_name_suffix,
                )
                logger.debug(f"Created speculative lease '{speculative_lease.name}' starting {next_lease_start_date}.")
                
                future_rollover_df = speculative_lease.project_future_cash_flows(
                    context, recursion_depth=recursion_depth + 1
                )
                all_cfs.append(future_rollover_df)

        # Aggregate all collected cash flows
        if not all_cfs:
            return pd.DataFrame(index=context.timeline.period_index).fillna(0)
            
        combined_df = pd.concat(all_cfs, sort=False).fillna(0)
        final_df = combined_df.groupby(combined_df.index).sum()
        
        # Ensure all standard columns from the original lease exist for safety
        base_cols = list(all_cfs[0].columns)
        for col in base_cols:
            if col not in final_df.columns:
                final_df[col] = 0.0
        
        # Only add vacancy loss if it's already present from a downtime calculation
        if 'vacancy_loss' not in final_df.columns:
            final_df['vacancy_loss'] = 0.0

        return final_df.reindex(context.timeline.period_index, fill_value=0.0)

    @abstractmethod
    def _create_speculative_lease_instance(
        self,
        start_date: date,
        lease_terms: RolloverLeaseTermsBase,
        rent_rate: float,
        tenant_name: str,
        name_suffix: str,
    ) -> "LeaseBase":
        pass
