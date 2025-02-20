from typing import Annotated, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import Field, field_validator
from pyxirr import xirr

from ..core._types import FloatBetween0And1, PositiveFloat
from ..utils._utils import equity_multiple
from ._model import Model
from ._project import Project

########################
######### DEAL #########
########################


class Partner(Model):
    name: str
    kind: Literal["GP", "LP"]
    share: FloatBetween0And1  # percentage of total equity

class WaterfallTier(Model):
    tier_hurdle_rate: PositiveFloat
    metric: Literal["IRR", "EM"] = "IRR"
    # FIXME: handle EM-based promotes throughout
    promote_rate: FloatBetween0And1

class Promote(Model):
    # different kinds of promotes:
    # - none (pari passu, no GP promote)
    # - waterfall (tiered promotes)
    # - carry (e.g., simple 20% after pref)
    kind: Literal["waterfall", "carry"]

class WaterfallPromote(Promote):
    kind: Literal["waterfall"] = "waterfall"
    pref_hurdle_rate: PositiveFloat
    tiers: list[WaterfallTier]
    final_promote_rate: FloatBetween0And1

    @property
    def all_tiers(self):
        sorted_tiers = sorted(self.tiers, key=lambda x: x.tier_hurdle_rate)
        tier_list = [(self.pref_hurdle_rate, 0.0)]
        tier_list.extend((t.tier_hurdle_rate, t.promote_rate) for t in sorted_tiers)
        return tier_list, self.final_promote_rate

class CarryPromote(Promote):
    kind: Literal["carry"] = "carry"
    pref_hurdle_rate: PositiveFloat
    promote_rate: FloatBetween0And1

    @property
    def all_tiers(self):
        # one pref tier @0 promote, then final tier infinite
        tier_list = [(self.pref_hurdle_rate, 0.0)]
        return tier_list, self.promote_rate

class Deal(Model):
    project: Project
    partners: list[Partner]
    promote: Optional[Annotated[Union[WaterfallPromote, CarryPromote], Field(..., discriminator="kind")]] = None
    time_basis: Optional[Literal["monthly", "annual"]] = None

    @property
    def project_net_cf(self) -> pd.Series:
        project_df = self.project.levered_cash_flow.copy()
        if self.time_basis == "annual":
            project_df = self.project.convert_to_annual(project_df)
        if isinstance(project_df.index, pd.PeriodIndex):
            project_df.index = project_df.index.to_timestamp()
        return project_df["Levered Cash Flow"]

    @property
    def project_irr(self) -> float:
        return xirr(self.project_net_cf)

    @property
    def project_equity_multiple(self) -> float:
        return equity_multiple(self.project_net_cf)
    
    @property
    def is_promoted_deal(self) -> bool:
        return self.promote is not None

    def _calculate_distributions(self) -> pd.DataFrame:
        """Calculate distributions for all partners"""
        
        net_cf = self.project_net_cf
        periods = net_cf.index
        partner_names = [p.name for p in self.partners]
        n_periods = len(periods)
        n_partners = len(self.partners)

        # Precompute partner arrays
        partner_shares = np.array([p.share for p in self.partners])
        gp_mask = np.array([p.kind == "GP" for p in self.partners])
        gp_shares_total = partner_shares[gp_mask].sum() or 1e-9

        # allocate memory for partner flows
        partner_flows = np.zeros((n_periods, n_partners))

        # Set up tiers
        if self.is_promoted_deal:
            tiers, final_promote_rate = self.promote.all_tiers
        else:
            tiers = []
            final_promote_rate = 0.0

        current_tier_index = 0

        # Pre-extract dates for IRR calculation
        date_array = pd.to_datetime(periods).to_pydatetime()

        def current_irr(flows: np.ndarray, up_to_idx: int) -> Optional[float]:
            cf = flows[:up_to_idx+1].sum(axis=1)
            # Need both neg and pos flows for IRR to be meaningful
            if not (np.any(cf < 0) and np.any(cf > 0)):
                return None
            s = pd.Series(cf, index=date_array[:up_to_idx+1])
            return xirr(s)

        def allocate_cf_at_rate(cf_amount: float, promote_rate: float) -> np.ndarray:
            # Vectorized distribution at given promote_rate
            base_dist = cf_amount * partner_shares * (1 - promote_rate)
            promote_amount = cf_amount * promote_rate
            base_dist[gp_mask] += promote_amount * (partner_shares[gp_mask] / gp_shares_total)
            return base_dist

        def test_allocation(flows: np.ndarray, period_idx: int, cf_amount: float, promote_rate: float) -> float:
            # Test allocating entire cf_amount at this tier rate
            test_flows = flows.copy()
            dist_array = allocate_cf_at_rate(cf_amount, promote_rate)
            test_flows[period_idx, :] += dist_array
            irr = current_irr(test_flows, period_idx)
            # If IRR can't be calculated, treat as very low return
            return irr if irr is not None else float('-inf')

        def solve_for_x(flows: np.ndarray, period_idx: int, cf_amount: float, promote_rate: float, hurdle_rate: float) -> float:
            # Binary search within this period's CF
            low, high = 0.0, cf_amount
            for _ in range(30):
                mid = (low + high) / 2
                test_flows = flows.copy()
                dist_array = allocate_cf_at_rate(mid, promote_rate)
                test_flows[period_idx, :] += dist_array
                irr_val = current_irr(test_flows, period_idx)
                if irr_val < hurdle_rate:
                    low = mid
                else:
                    high = mid
            return (low + high) / 2

        # Iterate over each period
        # TODO: handle EM-based tiers if implemented
        for period_idx, period in enumerate(periods):
            cf_value = net_cf.iloc[period_idx]
            if cf_value < 0:
                # Negative CF: Equity contribution once
                partner_flows[period_idx, :] += cf_value * partner_shares
            elif cf_value > 0:
                remaining_cf = cf_value
                while remaining_cf > 1e-9:
                    # If no more tiers left, use final promote
                    if current_tier_index < len(tiers):
                        hurdle_rate, promote_rate = tiers[current_tier_index]
                    else:
                        hurdle_rate = np.inf
                        promote_rate = final_promote_rate

                    # Test allocating all remaining_cf
                    test_irr_val = test_allocation(partner_flows, period_idx, remaining_cf, promote_rate)
                    if test_irr_val < hurdle_rate:
                        # Allocate all at this tier
                        partner_flows[period_idx, :] += allocate_cf_at_rate(remaining_cf, promote_rate)
                        remaining_cf = 0.0
                    else:
                        # surpasses hurdle mid-allocation
                        x = solve_for_x(partner_flows, period_idx, remaining_cf, promote_rate, hurdle_rate)
                        partner_flows[period_idx, :] += allocate_cf_at_rate(x, promote_rate)
                        remaining_cf -= x
                        # Move to next tier
                        current_tier_index += 1

        # Convert to DataFrame at the end
        dist = pd.DataFrame(partner_flows, index=periods, columns=partner_names)
        return dist

    @property
    def partner_irrs(self) -> pd.Series:
        dist = self._calculate_distributions()
        irr_values = {p.name: xirr(dist[p.name]) for p in self.partners}
        return pd.Series(irr_values, name="IRR")

    @property
    def partner_equity_multiples(self) -> pd.Series:
        dist = self._calculate_distributions()
        em_values = {p.name: equity_multiple(dist[p.name]) for p in self.partners}
        return pd.Series(em_values, name="Equity Multiple")

    @property
    def partner_cash_flows(self) -> pd.DataFrame:
        return self._calculate_distributions()

    @property
    def partner_summary(self) -> pd.DataFrame:
        """Returns a summary DataFrame with partner details and returns.
        
        Returns:
            DataFrame with columns: Kind, Share, IRR, Equity Multiple, Investment, Profit, Cash
        """
        cash_flows = self.partner_cash_flows
        df = pd.DataFrame({
            'Kind': [p.kind for p in self.partners],
            'Share': [p.share for p in self.partners],
            'IRR': self.partner_irrs,
            'Equity Multiple': self.partner_equity_multiples,
            'Investment': cash_flows.where(cash_flows < 0, 0).sum(axis=0).abs(),
            'Profit': cash_flows.sum(axis=0),
            'Cash': cash_flows.where(cash_flows > 0, 0).sum(axis=0)
        }, index=[p.name for p in self.partners])
        
        return df

    @property
    def project_summary(self) -> pd.DataFrame:
        """Returns a summary DataFrame with project-level returns.
        
        Returns:
            DataFrame with columns: IRR, Equity Multiple, Investment, Profit, Cash
        """
        return pd.DataFrame({
            'IRR': [self.project_irr],
            'Equity Multiple': [self.project_equity_multiple],
            'Investment': [self.project.total_investment],
            'Profit': [self.project.total_profit],
            'Cash': [self.project.total_distributions]
        }, index=['Project'])

    ####################
    #### VALIDATORS ####
    ####################
    @field_validator("time_basis", mode="before")
    def infer_time_basis(cls, v, values):
        # If user didn't provide time_basis, infer it from project's levered_cash_flow frequency
        if v is not None:
            return v  # user specified

        project = values.get("project")
        if project is None:
            # Can't infer without project
            return "monthly"

        df = project.levered_cash_flow
        if isinstance(df.index, pd.PeriodIndex):
            freq = df.index.freqstr or pd.infer_freq(df.index.to_timestamp())
        else:
            freq = pd.infer_freq(df.index)

        # Determine monthly or annual from freq
        # Common monthly freq: 'M', annual freq: 'A' or 'Y'
        if freq is not None:
            freq = freq.upper()
            if freq.startswith('A') or freq.startswith('Y'):
                return "annual"
            elif freq.startswith('M'):
                return "monthly"
            else:
                # If unclear, default to monthly
                return "monthly"
        else:
            # No frequency inferred, default to monthly
            return "monthly"
