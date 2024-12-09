from typing import Annotated, Literal, Optional, Union

import numpy as np
import pandas as pd
from pydantic import Field, field_validator
from pyxirr import xirr

from ..utils._types import FloatBetween0And1, PositiveFloat
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
        return self.equity_multiple(self.project_net_cf)
    
    @property
    def is_promoted_deal(self) -> bool:
        return self.promote is not None

    def _calculate_distributions(self) -> pd.DataFrame:
        net_cf = self.project_net_cf
        partner_names = [p.name for p in self.partners]
        dist = pd.DataFrame(index=net_cf.index, columns=partner_names, data=0.0)

        # Set up tiers
        if self.is_promoted_deal:
            tiers, final_promote_rate = self.promote.all_tiers
        else:
            tiers = []
            final_promote_rate = 0.0
        current_tier_index = 0

        def current_irr(allocation: pd.DataFrame, up_to) -> float:
            cf = allocation.loc[:up_to].sum(axis=1)
            # Need both neg and pos
            if not (cf.lt(0).any() and cf.gt(0).any()):
                return -9999.0
            return xirr(cf)

        def distribute_at_rate(cf_amount: float, promote_rate: float, period) -> pd.DataFrame:
            df_add = pd.DataFrame(index=[period], columns=partner_names, data=0.0)
            gp_names = [p.name for p in self.partners if p.kind == "GP"]
            total_gp_share = sum(p.share for p in self.partners if p.kind == "GP") or 1e-9
            base_share = (1 - promote_rate)
            for p_obj in self.partners:
                df_add.at[period, p_obj.name] = cf_amount * p_obj.share * base_share
            promote_amount = cf_amount * promote_rate
            for g in gp_names:
                gp_share = next(pr.share for pr in self.partners if pr.name == g)
                df_add.at[period, g] += promote_amount * (gp_share / total_gp_share)
            return df_add

        def solve_for_x(dist_state: pd.DataFrame, cf_amount: float, promote_rate: float, hurdle_rate: float, period) -> float:
            # Binary search within this period's CF
            low, high = 0.0, cf_amount
            for _ in range(30):
                mid = (low + high) / 2
                test_dist = dist_state.copy()
                dist_mid = distribute_at_rate(mid, promote_rate, period)
                for col in dist_mid.columns:
                    test_dist.at[period, col] += dist_mid.at[period, col]
                irr_val = current_irr(test_dist, period)
                if irr_val < hurdle_rate:
                    low = mid
                else:
                    high = mid
            return (low + high) / 2

        # Iterate by period
        for period in net_cf.index:
            month_cf = net_cf.loc[period]
            if month_cf < 0:
                # Negative CF: Equity contribution once
                for p in self.partners:
                    dist.at[period, p.name] += month_cf * p.share
            elif month_cf > 0:
                remaining_cf = month_cf
                while remaining_cf > 1e-9:
                    # If no more tiers left, use final promote
                    if current_tier_index < len(tiers):
                        hurdle_rate, promote_rate = tiers[current_tier_index]
                    else:
                        hurdle_rate = np.inf
                        promote_rate = final_promote_rate

                    # Test allocating all remaining_cf
                    test_dist = dist.copy()
                    dist_all = distribute_at_rate(remaining_cf, promote_rate, period)
                    for col in dist_all.columns:
                        test_dist.at[period, col] += dist_all.at[period, col]

                    test_irr = current_irr(test_dist, period)

                    if test_irr < hurdle_rate:
                        # Allocate all at this tier
                        dist = test_dist
                        remaining_cf = 0.0
                    else:
                        # We surpass the hurdle
                        # Find exact fraction x
                        x = solve_for_x(dist, remaining_cf, promote_rate, hurdle_rate, period)
                        dist_x = distribute_at_rate(x, promote_rate, period)
                        for col in dist_x.columns:
                            dist.at[period, col] += dist_x.at[period, col]
                        remaining_cf -= x
                        # Move to next tier
                        current_tier_index += 1

                        # If we still have leftover CF after hitting hurdle exactly,
                        # we continue while loop at next tier

        return dist

    @property
    def partner_irrs(self) -> pd.Series:
        dist = self._calculate_distributions()
        irr_values = {p.name: xirr(dist[p.name]) for p in self.partners}
        return pd.Series(irr_values, name="IRR")

    @property
    def partner_equity_multiples(self) -> pd.Series:
        dist = self._calculate_distributions()
        em_values = {p.name: self.equity_multiple(dist[p.name]) for p in self.partners}
        return pd.Series(em_values, name="Equity Multiple")

    @staticmethod
    def equity_multiple(cash_flows: pd.Series) -> float:
        invested = cash_flows.where(cash_flows < 0, 0).sum()
        returned = cash_flows.where(cash_flows > 0, 0).sum()
        if invested == 0:
            return np.inf
        return returned / abs(invested)

    @property
    def partner_cash_flows(self) -> pd.DataFrame:
        return self._calculate_distributions()


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
            freq = df.index.freqstr or pd.infer_freq(df.index)
        else:
            # If TimestampIndex, try infer_freq
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