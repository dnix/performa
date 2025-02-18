from datetime import date
from typing import Optional

from ..utils._model import Model
from ..utils._types import FloatBetween0And1, PositiveFloat
from ._enums import AssetUseEnum, LeaseTypeEnum
from ._revenue import MarketProfile


class Tenant(Model):
    """
    Individual tenant record representing a lease agreement.

    Attributes:
        id: Unique identifier
        name: Tenant name
        suite: Suite/unit identifier
        leased_area: Square footage leased
        percent_of_building: Percentage of total building area
        use_type: Type of use (office, retail, etc)
        lease_start: Start date of current lease
        lease_end: End date of current lease
        current_base_rent: Current annual/monthly rent
        rent_type: Type of lease (gross, net, etc)
        expense_base_year: Base year for expense stops
        renewal_probability: Likelihood of renewal
        market_profile: Applicable market assumptions
    """

    # Identity
    id: str
    name: str
    suite: str

    # Space
    leased_area: PositiveFloat  # sq ft
    percent_of_building: FloatBetween0And1

    # Use
    use_type: AssetUseEnum

    # Current Lease Terms
    lease_start: date
    lease_end: date
    current_base_rent: PositiveFloat  # annual or monthly
    rent_type: LeaseTypeEnum  # gross, net, modified gross
    expense_base_year: Optional[int] = None

    # Renewal Terms
    renewal_probability: FloatBetween0And1
    market_profile: MarketProfile  # reference to applicable market assumptions
