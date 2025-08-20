# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import numpy as np
import pandas as pd

from performa.core.base import LeaseBase, RentEscalationBase, RolloverLeaseTermsBase
from performa.core.primitives import (
    FrequencyEnum,
    PropertyAttributeKey,
    Timeline,
    UponExpirationEnum,
)

if TYPE_CHECKING:
    from performa.analysis import AnalysisContext
    from performa.core.primitives.growth_rates import (
        GrowthRateBase,
    )


logger = logging.getLogger(__name__)


def _extract_rate_value(rate_object: GrowthRateBase, period: pd.Period) -> float:
    """
    Extract the appropriate rate value for a given period from a rate object.

    Args:
        rate_object: PercentageGrowthRate or FixedGrowthRate object with value as float, pd.Series, or Dict[date, float]
        period: The period for which to extract the rate

    Returns:
        The rate value for the specified period
    """
    if isinstance(rate_object.value, (int, float)):
        # Simple constant rate
        return rate_object.value

    elif isinstance(rate_object.value, pd.Series):
        # Time-based series - no interpolation, use as-is (assume monthly)
        try:
            return rate_object.value.loc[period]
        except KeyError:
            # If period not found, use the last available rate
            return rate_object.value.iloc[-1]

    elif isinstance(rate_object.value, dict):
        # Date-based dict - map to period (assume monthly keys)
        for date_key, rate in rate_object.value.items():
            if pd.Period(date_key, freq="M") == period:
                return rate
        # If not found, use the last available rate
        return list(rate_object.value.values())[-1]

    else:
        raise ValueError(f"Unsupported rate value type: {type(rate_object.value)}")


class CommercialLeaseBase(LeaseBase, ABC):
    # Multiple escalations support
    rent_escalations: Optional[Union[RentEscalationBase, List[RentEscalationBase]]] = (
        None
    )

    def _get_escalations_list(self) -> List[RentEscalationBase]:
        """Get escalations as a list, handling both single and multiple formats"""
        if self.rent_escalations is None:
            return []

        if isinstance(self.rent_escalations, list):
            return self.rent_escalations
        else:
            return [self.rent_escalations]

    def _apply_escalations(self, base_flow: pd.Series) -> pd.Series:
        """Apply all escalations to the base rent flow"""
        escalations = self._get_escalations_list()
        if not escalations:
            return base_flow

        rent_with_escalations = base_flow.copy()
        periods = self.timeline.period_index
        lease_start_period = periods[0]

        # Sort escalations by start timing to apply in chronological order
        sorted_escalations = sorted(
            escalations, key=lambda esc: esc.get_start_period(lease_start_period)
        )

        for escalation in sorted_escalations:
            rent_with_escalations = self._apply_single_escalation(
                rent_with_escalations, escalation, periods, lease_start_period
            )

        return rent_with_escalations

    def _apply_single_escalation(
        self,
        current_flow: pd.Series,
        escalation: RentEscalationBase,
        periods: pd.PeriodIndex,
        lease_start_period: pd.Period,
    ) -> pd.Series:
        """Apply a single escalation to the current rent flow"""
        start_period = escalation.get_start_period(lease_start_period)
        mask = periods >= start_period

        if escalation.type == "percentage":
            if escalation.recurring:
                freq = escalation.frequency_months or 12
                months_elapsed = np.array([(p - start_period).n for p in periods])
                # For recurring escalations, the first escalation applies immediately at start_period
                cycles = np.floor(months_elapsed / freq) + 1
                cycles[~mask] = 0

                if escalation.uses_rate_object:
                    # For time-varying rates, handle each escalation cycle separately
                    result_flow = current_flow.copy()

                    # Calculate escalation dates
                    escalation_dates = []
                    current_date = start_period
                    while current_date <= periods[-1]:
                        escalation_dates.append(current_date)
                        current_date += freq

                    # Apply each escalation using the rate for that period
                    for i, escalation_date in enumerate(escalation_dates):
                        period_mask = periods >= escalation_date
                        if period_mask.any():
                            rate = _extract_rate_value(escalation.rate, escalation_date)
                            if escalation.is_relative:
                                result_flow[period_mask] *= 1 + rate
                            else:
                                escalation_amount = current_flow[period_mask] * rate
                                result_flow[period_mask] += escalation_amount

                    return result_flow
                else:
                    # Use fixed rate value (existing logic)
                    rate = escalation.rate
                    if escalation.is_relative:
                        growth_factor = np.power(1 + rate, cycles)
                        return current_flow * growth_factor
                    else:
                        growth_factor = np.power(1 + rate, cycles)
                        escalation_series = current_flow * (growth_factor - 1)
                        return current_flow + escalation_series

            elif escalation.is_relative:
                if escalation.uses_rate_object:
                    # Extract rate for start period and apply to all masked periods
                    rate = _extract_rate_value(escalation.rate, start_period)
                    growth_factor = np.ones(len(periods))
                    growth_factor[mask] = 1 + rate
                else:
                    growth_factor = np.ones(len(periods))
                    growth_factor[mask] = 1 + escalation.rate
                return current_flow * growth_factor
            else:
                if escalation.uses_rate_object:
                    rate = _extract_rate_value(escalation.rate, start_period)
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = current_flow[mask] * rate
                else:
                    escalation_series = pd.Series(0.0, index=periods)
                    escalation_series[mask] = current_flow[mask] * escalation.rate
                return current_flow + escalation_series

        elif escalation.type == "fixed":
            if escalation.uses_rate_object:
                # For fixed escalations with rate objects, treat as dollar amounts
                rate = _extract_rate_value(escalation.rate, start_period)
                if escalation.reference is None:
                    monthly_amount = rate / 12
                elif escalation.reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                    monthly_amount = (rate * self.area) / 12
                else:
                    raise NotImplementedError(
                        f"Escalation reference {escalation.reference} not implemented"
                    )
            else:
                rate = escalation.rate
                if escalation.reference is None:
                    monthly_amount = rate / 12
                elif escalation.reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                    monthly_amount = (rate * self.area) / 12
                else:
                    raise NotImplementedError(
                        f"Escalation reference {escalation.reference} not implemented"
                    )

            if escalation.recurring:
                freq = escalation.frequency_months or 12
                months_elapsed = np.array([(p - start_period).n for p in periods])
                # For recurring escalations, the first escalation applies immediately at start_period
                cycles = np.floor(months_elapsed / freq) + 1
                cycles[~mask] = 0
                cumulative_increases = cycles * monthly_amount
                escalation_series = pd.Series(cumulative_increases, index=periods)
                return current_flow + escalation_series
            else:
                escalation_series = pd.Series(0.0, index=periods)
                escalation_series[mask] = monthly_amount
                return current_flow + escalation_series

        return current_flow

    def _apply_abatements(self, rent_flow: pd.Series) -> tuple[pd.Series, pd.Series]:
        if not self.rent_abatement:
            return rent_flow, pd.Series(0.0, index=rent_flow.index)
        abated_rent_flow = rent_flow.copy()
        abatement_amount_series = pd.Series(0.0, index=rent_flow.index)
        periods = self.timeline.period_index
        lease_start_period = self.timeline.start_date
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
        2.  Escalations: Applies multiple rent escalations if defined.
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
            # New unified reference-based calculation system for leases
            if self.reference is None:
                # Direct currency amount - no multiplication needed
                pass
            elif isinstance(self.reference, PropertyAttributeKey):
                # DYNAMIC RESOLUTION: Property attribute calculation
                if self.reference == PropertyAttributeKey.NET_RENTABLE_AREA:
                    # Special case: Use lease area for per-SF calculations
                    initial_monthly_value *= self.area
                elif self.reference == PropertyAttributeKey.UNIT_COUNT:
                    # For office suites, this would be 1 (one suite)
                    initial_monthly_value *= 1
                else:
                    # EXTENSIBLE: Could be enhanced to handle other PropertyAttributeKey types
                    # For now, assume unit-based (1x multiplier)
                    initial_monthly_value *= 1
            else:
                raise NotImplementedError(
                    f"Reference type {type(self.reference)} not implemented for leases"
                )
            base_rent = pd.Series(
                initial_monthly_value, index=self.timeline.period_index
            )
        elif isinstance(self.value, pd.Series):
            base_rent = self.value.copy()
            base_rent = base_rent.reindex(self.timeline.period_index, fill_value=0.0)
        else:
            # Handle other potential value types or raise error
            raise TypeError(f"Unsupported type for lease value: {type(self.value)}")

        base_rent_with_escalations = self._apply_escalations(base_rent)
        base_rent_final, abatement_cf = self._apply_abatements(
            base_rent_with_escalations
        )

        # --- Recovery Calculation ---
        recoveries_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.recovery_method:
            # The new context-based approach, now passing self
            recoveries_cf = self.recovery_method.compute_cf(context=context, lease=self)

            if self.rent_abatement and self.rent_abatement.includes_recoveries:
                lease_start_period = self.timeline.start_date
                abatement_start_month = self.rent_abatement.start_month - 1
                abatement_start_period = lease_start_period + abatement_start_month
                abatement_end_period = (
                    abatement_start_period + self.rent_abatement.months
                )
                abatement_mask = (recoveries_cf.index >= abatement_start_period) & (
                    recoveries_cf.index < abatement_end_period
                )
                recoveries_cf[abatement_mask] *= 1 - self.rent_abatement.abated_ratio

        # --- TI/LC Calculation ---
        ti_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.ti_allowance:
            # Set lease context for TI calculation
            context_with_lease = context
            context_with_lease.current_lease = self
            allowance_cf = self.ti_allowance.compute_cf(context=context_with_lease)
            ti_cf = allowance_cf.reindex(self.timeline.period_index, fill_value=0.0)

        lc_cf = pd.Series(0.0, index=self.timeline.period_index)
        if self.leasing_commission:
            # Set lease context for LC calculation
            context_with_lease = context
            context_with_lease.current_lease = self
            commission_cf = self.leasing_commission.compute_cf(
                context=context_with_lease
            )
            lc_cf = commission_cf.reindex(self.timeline.period_index, fill_value=0.0)

        # Return only base components to avoid duplicate transactions in ledger
        # The ledger aggregation system will handle totals (revenue, expenses, net)
        result = {
            "base_rent": base_rent_final.fillna(0.0),
            "abatement": abatement_cf.fillna(0.0),
            "recoveries": recoveries_cf.fillna(0.0),
            "ti_allowance": ti_cf.fillna(0.0),
            "leasing_commission": lc_cf.fillna(0.0),
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
            logger.debug(
                f"Lease '{self.name}' expires {lease_end_period}. Action: {action}. Projecting rollover..."
            )

            downtime_months = 0
            if action in [UponExpirationEnum.MARKET, UponExpirationEnum.VACATE]:
                downtime_months = profile.downtime_months

            # Placeholder for tenant name
            current_tenant_name = self.name.split(" - ")[0]

            next_lease_start_date = (
                lease_end_period.to_timestamp()
                + pd.DateOffset(months=downtime_months + 1)
            ).date()

            # Handle Downtime
            if downtime_months > 0:
                downtime_start_date = (lease_end_period + 1).start_time.date()
                downtime_timeline = Timeline(
                    start_date=downtime_start_date, duration_months=downtime_months
                )
                market_rent_at_downtime = profile._calculate_rent(
                    terms=profile.market_terms,
                    as_of_date=downtime_start_date,
                    global_settings=context.settings,
                )
                monthly_vacancy_loss = market_rent_at_downtime * self.area
                vacancy_loss_series = pd.Series(
                    monthly_vacancy_loss,
                    index=downtime_timeline.period_index,
                    name="vacancy_loss",
                )
                all_cfs.append(vacancy_loss_series.to_frame())

            # The Dispatcher Logic
            next_lease_terms: Optional[RolloverLeaseTermsBase] = None
            next_name_suffix: str = ""

            if action == UponExpirationEnum.RENEW:
                next_lease_terms = profile.renewal_terms
                next_name_suffix = f" (Renewal {recursion_depth + 1})"
            elif action == UponExpirationEnum.VACATE:
                next_lease_terms = profile.market_terms
                current_tenant_name = f"Market Tenant for {self.suite}"  # New tenant
                next_name_suffix = f" (Rollover {recursion_depth + 1})"
            elif action == UponExpirationEnum.MARKET:
                next_lease_terms = profile.blend_lease_terms()
                current_tenant_name = f"Market Tenant for {self.suite}"  # New tenant
                next_name_suffix = f" (Rollover {recursion_depth + 1})"
            elif action == UponExpirationEnum.OPTION and profile.option_terms:
                next_lease_terms = profile.option_terms
                next_name_suffix = f" (Option {recursion_depth + 1})"
            elif action == UponExpirationEnum.REABSORB:
                logger.debug(
                    f"Lease '{self.name}' set to REABSORB. Stopping projection chain."
                )
                # next_lease_terms remains None, stopping the recursion

            # Create and recurse if a next step was determined
            if (
                next_lease_terms
                and pd.Period(next_lease_start_date, freq="M") <= analysis_end_period
            ):
                new_rent_rate = profile._calculate_rent(
                    terms=next_lease_terms,
                    as_of_date=next_lease_start_date,
                    global_settings=context.settings,
                )
                speculative_lease = self._create_speculative_lease_instance(
                    start_date=next_lease_start_date,
                    lease_terms=next_lease_terms,
                    rent_rate=new_rent_rate,
                    tenant_name=current_tenant_name,
                    name_suffix=next_name_suffix,
                )
                logger.debug(
                    f"Created speculative lease '{speculative_lease.name}' starting {next_lease_start_date}."
                )

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
        if "vacancy_loss" not in final_df.columns:
            final_df["vacancy_loss"] = 0.0

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
