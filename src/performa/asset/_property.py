from datetime import date
from typing import List, Optional

from pydantic import model_validator

from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat
from ._enums import AssetTypeEnum
from ._expense import CapitalExpenses, OperatingExpenses
from ._recovery import ExpensePool, RecoveryMethod
from ._revenue import MarketProfile, MiscIncome, RentRoll, Tenant
from ._settings import (
    ModelSettings,
    PercentageRentSettings,
    RecoverySettings,
    RolloverSettings,
    VacancySettings,
)


class Floor(Model):
    """Building floor details"""

    number: int
    area: PositiveFloat
    tenants: List[Tenant]


class Address(Model):
    """Street address of the property"""

    street: str
    city: str
    state: str
    zip_code: str
    country: str


class Property(Model):
    """
    Core asset/property class representing an income-producing real estate asset.

    Attributes:
        id: Unique identifier.
        name: Property name.
        description: Optional description.
        external_id: External property identifier (from Argus).
        entity_id: External entity identifier (from Argus).
        address: Street address.
        city: City where the property is located.
        state: State where the property is located.
        zip_code: Postal code of the property.
        country: Country where the property is located.
        property_type: Type of asset (e.g., Office, Retail, Industrial, Multifamily, Hotel, Mixed Use).
        year_built: Construction year.
        gross_area: Total building area in square feet.
        net_rentable_area: Leasable area in square feet.
        rent_roll: Current tenancy and lease details.
        operating_expenses: Property operating expenses.
        capital_expenses: Major capital improvements/investments.
        market_profile: Market leasing assumptions.
        valuation_date: Date of analysis.
        analysis_start_date: Start of the projection period.
        analysis_period_months: Length of the projection in months.
        floors: List of floors in the property.
        model_settings: Settings for the financial model.
        vacancy_settings: Vacancy settings for the asset.
        percentage_rent_settings: PercentageRentSettings
        recovery_settings: RecoverySettings
        rollover_settings: RolloverSettings
        misc_income: List[MiscIncome]
        recovery_methods: List[RecoveryMethod]
        expense_pools: List[ExpensePool]
    """

    # Identity
    id: str
    name: str
    description: Optional[str] = None

    # New fields for enhanced mapping to Argus
    external_id: Optional[str] = None
    entity_id: Optional[str] = None
    address: Address

    # Physical Characteristics
    property_type: AssetTypeEnum
    year_built: int
    gross_area: PositiveFloat  # sq ft
    net_rentable_area: PositiveFloat  # sq ft

    # Components
    rent_roll: RentRoll
    market_profile: MarketProfile

    # Analysis Settings
    valuation_date: date
    analysis_start_date: date
    analysis_period_months: int = 120  # typical 10-year analysis

    # Additional Attributes
    floors: List[Floor]

    # New settings
    model_settings: ModelSettings
    vacancy_settings: VacancySettings
    percentage_rent_settings: PercentageRentSettings
    recovery_settings: RecoverySettings
    rollover_settings: RolloverSettings

    # Enhanced components
    misc_income: List[MiscIncome]
    operating_expenses: OperatingExpenses
    capital_expenses: CapitalExpenses
    recovery_methods: List[RecoveryMethod]
    expense_pools: List[ExpensePool]

    @model_validator(mode="after")
    def validate_areas(self) -> "Property":
        """Validate that NRA doesn't exceed GBA"""
        if self.net_rentable_area > self.gross_area:
            raise ValueError(
                f"Net rentable area ({self.net_rentable_area:,.0f} SF) "
                f"cannot exceed gross area ({self.gross_area:,.0f} SF)"
            )
        return self

    @property
    def vacant_area(self) -> PositiveFloat:
        """Calculate total vacant area"""
        return self.net_rentable_area - self.rent_roll.total_occupied_area

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """Calculate current occupancy rate"""
        return self.rent_roll.total_occupied_area / self.net_rentable_area
