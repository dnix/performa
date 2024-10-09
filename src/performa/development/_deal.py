from typing import Annotated, Literal, Optional, Union

import pandas as pd
from pydantic import Field
from pyxirr import xirr

from ..utils.types import FloatBetween0And1, PositiveFloat
from ._model import Model
from ._project import Project

########################
######### DEAL #########
########################


class Partner(Model):
    name: str
    kind: Literal["GP", "LP"]
    share: FloatBetween0And1  # percentage of total equity


class Promote(Model):
    # different kinds of promotes:
    # - none (pari passu, no GP promote)
    # - waterfall (tiered promotes)
    # - carry (e.g., simple 20% after pref)
    kind: Literal["waterfall", "carry"]


class WaterfallTier(Model):
    """Class for a waterfall tier"""

    tier_hurdle_rate: PositiveFloat  # tier irr or em hurdle rate
    metric: Literal["IRR", "EM"]  # metric for the promote
    promote_rate: FloatBetween0And1  # promote as a percentage of total profits


class WaterfallPromote(Promote):
    """Class for a waterfall promote"""

    kind: Literal["waterfall"] = "waterfall"
    pref_hurdle_rate: (
        PositiveFloat  # minimum IRR or EM to trigger promote (tier 1); the 'pref'
    )
    tiers: list[WaterfallTier]
    final_promote_rate: FloatBetween0And1  # final tier, how remainder is split after all tiers (usually 50/50)


class CarryPromote(Promote):
    """Class for a GP carry promote"""

    kind: Literal["carry"] = "carry"
    pref_hurdle_rate: PositiveFloat  # minimum IRR or EM to trigger promote; the 'pref'
    promote_rate: FloatBetween0And1  # promote as a percentage of total profits
    # TODO: consider clawbacks and other carry structures


class Deal(Model):
    """Class for a generic deal"""

    project: Project
    partners: list[Partner]
    promote: Optional[
        Annotated[
            Union[WaterfallPromote, CarryPromote], Field(..., discriminator="kind")
        ]
    ]  # there can also be no GP promote, just pari passu
    # param for running calculations on monthly or annual basis
    time_basis: Literal["monthly", "annual"] = "monthly"

    # TODO: add property-level GP fees (mgmt/deal fees, acquisition/disposition fees, etc.)

    @property
    def project_net_cf(self) -> pd.Series:
        """Compute project net cash flow"""
        # TODO: correct for property-level GP fees
        # get unlevered cash flow df from project
        project_df = self.project.levered_cash_flow
        # if time_basis is annual, convert to annual
        if self.time_basis == "annual":
            project_df = Project.convert_to_annual(project_df)
        # set index to timestamp for pyxirr
        project_df.set_index(project_df.index.to_timestamp(), inplace=True)
        # get net cash flow column as Series
        project_net_cf = project_df["Levered Cash Flow"]
        return project_net_cf

    @property
    def project_equity_cf(self) -> pd.Series:
        """Compute project equity cash flow"""
        return (
            self.project_net_cf[self.project_net_cf < 0]
            .reindex(self.project.project_timeline)
            .fillna(0)
        )

    @property
    def project_irr(self) -> float:
        """Compute project IRR"""
        return xirr(self.project_net_cf)

    @property
    def partner_irrs(self) -> dict[str, float]:
        """Compute partner IRRs"""
        partner_df = self.calculate_distributions()
        partner_irrs = {
            partner: xirr(partner_df[partner]) for partner in partner_df.columns
        }
        return partner_irrs

    @property
    def project_equity_multiple(self) -> float:
        """Compute project equity multiple"""
        return Deal.equity_multiple(self.project_net_cf)

    @property
    def partner_equity_multiples(self) -> dict[str, float]:
        """Compute partner Equity Multiples"""
        partner_df = self.calculate_distributions()
        partner_equity_multiples = {
            partner: Deal.equity_multiple(partner_df[partner])
            for partner in partner_df.columns
        }
        return partner_equity_multiples

    @property
    def distributions(self) -> pd.DataFrame:
        """Calculate and return distributions based on the promote structure."""
        if self.promote.kind == "carry":
            return self._distribute_carry_promote()
        elif self.promote.kind == "waterfall":
            distributions_df, _ = self._distribute_waterfall_promote()
            # TODO: handle partner tiers return gracefully (maybe in another details method?)
            return distributions_df
        else:
            return self._distribute_pari_passu()

    def _distribute_carry_promote(self) -> pd.DataFrame:
        """Distribute cash flows with carry promote structure."""
        equity_cf = self.project_equity_cf
        lp_share = sum(p.share for p in self.partners if p.kind == "LP")
        gp_share = 1 - lp_share
        promote_rate = self.promote.promote_rate
        pref_rate = self.promote.pref_hurdle_rate

        # Calculate accrued preferred return interest
        pref_accrued = self._accrue_interest(equity_cf, pref_rate, self.time_basis)
        pref_distribution = pref_accrued.clip(upper=self.project_net_cf)

        # Distribute preferred return first
        remaining_cf = self.project_net_cf - pref_distribution.sum(axis=1)

        # Initialize distributions for each partner
        distributions = {
            partner.name: pd.Series(0, index=self.project_net_cf.index)
            for partner in self.partners
        }

        # Allocate preferred distributions
        for partner in self.partners:
            if partner.kind == "LP":
                distributions[partner.name] += pref_distribution * partner.share
            else:
                distributions[partner.name] += pref_distribution * gp_share

        # Distribute remaining cash flows
        lp_remaining_cf = remaining_cf * lp_share
        gp_carry = remaining_cf * promote_rate
        gp_remaining_cf = remaining_cf * gp_share + gp_carry
        lp_remaining_cf -= gp_carry

        # Allocate remaining cash flows
        for partner in self.partners:
            if partner.kind == "LP":
                distributions[partner.name] += lp_remaining_cf * partner.share
            else:
                distributions[partner.name] += gp_remaining_cf

        # Return distributions
        distributions_df = pd.DataFrame(distributions)
        return distributions_df

    # TODO: this is a european waterfall, how would an american style work? support both? https://www.adventuresincre.com/watch-me-build-american-style-real-estate-equity-waterfall/
    # TODO: catchup provision in (european) waterfall
    # TODO: lookback/clawback provision in (american) waterfall
    # TODO: if both IRR and EMx are used, manage this

    # FIXME: disaggregate GP coinvestment return from promote return

    def _distribute_waterfall_promote(self) -> pd.DataFrame:
        """Distribute cash flows with waterfall promote structure."""
        equity_cf = self.project_equity_cf
        net_cf = self.project_net_cf
        lp_share = sum(p.share for p in self.partners if p.kind == "LP")
        gp_share = 1 - lp_share
        remaining_cf = net_cf.copy()
        distributions = {
            partner.name: pd.Series(0, index=net_cf.index) for partner in self.partners
        }
        tier_distributions = {
            f"{partner.name}_Tier_{i+1}": pd.Series(0, index=net_cf.index)
            for i in range(len(self.promote.tiers) + 1)
            for partner in self.partners
        }

        # PREF (Tier 1)
        pref_rate = self.promote.pref_hurdle_rate
        # Calculate the accrued preferred return interest
        pref_accrued = self._accrue_interest(equity_cf, pref_rate, self.time_basis)
        # Distribute preferred return based on the accrued interest
        pref_distribution = pref_accrued.clip(upper=remaining_cf)
        for partner in self.partners:
            share = partner.share if partner.kind == "LP" else gp_share
            # Allocate the preferred distribution to each partner
            tier_distributions[f"{partner.name}_Tier_1"] = pref_distribution * share
            distributions[partner.name] += pref_distribution * share
        remaining_cf -= pref_distribution.sum(axis=1)

        # SUBSEQUENT TIERS
        for i, tier in enumerate(self.promote.tiers):
            tier_rate = tier.tier_hurdle_rate
            promote_rate = tier.promote_rate
            # Calculate the accrued return for the current tier
            accrued_return = self._accrue_interest(
                equity_cf, tier_rate, self.time_basis
            )
            required_return = accrued_return - pref_accrued
            # Distribute the return required for the current tier
            tier_distribution = required_return.clip(upper=remaining_cf)
            lp_share_after_promote = lp_share * (1 - promote_rate)
            gp_share_after_promote = 1 - lp_share_after_promote
            for partner in self.partners:
                if partner.kind == "LP":
                    # Allocate the tier distribution to each LP partner
                    tier_distributions[f"{partner.name}_Tier_{i+2}"] = (
                        tier_distribution * lp_share_after_promote
                    )
                    distributions[partner.name] += (
                        tier_distribution * lp_share_after_promote
                    )
                else:
                    # Allocate the tier distribution to the GP partner
                    tier_distributions[f"{partner.name}_Tier_{i+2}"] = (
                        tier_distribution * gp_share_after_promote
                    )
                    distributions[partner.name] += (
                        tier_distribution * gp_share_after_promote
                    )
            remaining_cf -= tier_distribution.sum(axis=1)
            pref_accrued += tier_distribution

        # FINAL PROMOTE
        final_promote_rate = self.promote.final_promote_rate
        for partner in self.partners:
            if partner.kind == "LP":
                # Allocate the final promote distribution to each LP partner
                tier_distributions[f"{partner.name}_Final"] = (
                    remaining_cf * lp_share * (1 - final_promote_rate)
                )
                distributions[partner.name] += (
                    remaining_cf * lp_share * (1 - final_promote_rate)
                )
            else:
                # Allocate the final promote distribution to the GP partner
                tier_distributions[f"{partner.name}_Final"] = remaining_cf * (
                    1 - lp_share * (1 - final_promote_rate)
                )
                distributions[partner.name] += remaining_cf * (
                    1 - lp_share * (1 - final_promote_rate)
                )

        # RETURN DISTRIBUTIONS
        distributions_df = pd.DataFrame(distributions)
        tier_distributions_df = pd.DataFrame(tier_distributions)
        return distributions_df, tier_distributions_df

    def _distribute_pari_passu(self) -> pd.DataFrame:
        """
        Assigns equity and distributes returns pari passu, without any promotes.
        """
        distributions = {
            partner.name: self.project_net_cf * partner.share
            for partner in self.partners
        }
        distributions_df = pd.DataFrame(distributions)
        return distributions_df

    @staticmethod
    def _accrue_interest(
        equity_cf: pd.Series, rate: float, time_basis: str
    ) -> pd.Series:
        """Accrue interest on equity cash flows using capital account logic."""
        periods = 12 if time_basis == "monthly" else 1
        accrued = pd.Series(0, index=equity_cf.index)
        capital_account = pd.Series(0, index=equity_cf.index)
        # Loop through each period to adjust capital account and compute interest
        for i in range(1, len(equity_cf)):
            # Adjust capital account based on previous balance, equity contribution, and distribution
            capital_account.iloc[i] = capital_account.iloc[i - 1] + equity_cf.iloc[i]
            # Calculate accrued interest on adjusted capital account balance
            accrued.iloc[i] = capital_account.iloc[i] * (
                (1 + rate / periods) ** (1 / periods) - 1
            )
        return accrued

    #####################
    # HELPERS/UTILITIES #
    #####################

    @staticmethod
    def equity_multiple(cash_flows: pd.Series) -> float:
        """Compute equity multiple from cash flows"""
        return cash_flows[cash_flows > 0].sum() / abs(cash_flows[cash_flows < 0].sum())

    # FIXME: bring back validators updating to new fields
    # @model_validator(mode="before")
    # def validate_partners(self):
    #     """Validate the partner structure"""
    #     # check that there is at least one GP and one LP
    #     if len([partner for partner in self.partners if partner.kind == "GP"]) != 1:
    #         raise ValueError("At least one (and only one) GP partner is required")
    #     if not any(partner.kind == "LP" for partner in self.partners):
    #         raise ValueError("At least one LP partner is required")
    #     # check that partner shares sum to 1.0
    #     if sum(partner.share for partner in self.partners) != 1.0:
    #         raise ValueError("Partner shares must sum to 1.0")
    #     return self

    # @model_validator(mode="before")
    # def validate_promote(self):
    #     """Validate the promote structure"""
    #     if self.promote.kind == "waterfall":
    #         # check that only metric is consistent across tiers (only IRR or EM)
    #         if any(tier.metric != self.promote.tiers[0].metric for tier in self.promote.tiers):
    #             raise ValueError("All tiers must use the same metric (IRR or EM)")
    #         # check that all tiers are higher than the hurdle
    #         if any(tier.tier_hurdle < self.promote.hurdle for tier in self.promote.tiers):
    #             raise ValueError("All tiers must be higher than the hurdle")
    #     return self
