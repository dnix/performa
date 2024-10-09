from ..utils.types import FloatBetween0And1, PositiveInt
from ._model import Model

# %%
#############################
######### FINANCING #########
#############################


class ConstructionFinancing(Model):
    """Class for a generic financing line item"""

    # TODO: consider multiple financing types and interactions (construction, mezzanine, permanent, etc.)
    # TODO: construction: pass target LTC for traditional construction loan with LTC cap, have fallover mezzanine loan

    # FIXME: fixed rate vs floating rate options

    interest_rate: FloatBetween0And1
    fee_rate: FloatBetween0And1  # TODO: should this be a dollar amount?
    # ltc_ratio: FloatBetween0And1  # FIXME: use a loan-to-cost ratio in debt sizing and mezzanine rollover; loan + mezz ltc = debt-to-equity ratio


class PermanentFinancing(Model):
    interest_rate: FloatBetween0And1
    fee_rate: FloatBetween0And1  # TODO: should this be a dollar amount?
    ltv_ratio: FloatBetween0And1 = 0.75  # TODO: add warnings for DSCR
    amortization: PositiveInt = 30  # term in years
