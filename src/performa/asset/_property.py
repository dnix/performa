import logging
import uuid
from typing import Dict, List, Optional

from pydantic import Field, model_validator

from ..core._enums import AssetTypeEnum
from ..core._model import Model
from ..core._types import FloatBetween0And1, PositiveFloat, PositiveInt
from ._expense import Expenses
from ._lease import Tenant
from ._losses import Losses
from ._misc_income import MiscIncome
from ._rent_roll import RentRoll

logger = logging.getLogger(__name__)


class PropertyFloor(Model):
    """Building floor details"""

    number: int
    area: PositiveFloat
    tenants: List[Tenant]


class PropertySuite(Model):
    """Building suite details
    
    Attributes:
        suite_id: Unique identifier for the suite
        area: Rentable area in square feet
        tenant: Current tenant, or None if vacant
    """

    suite_id: str
    area: PositiveFloat
    tenant: Optional[Tenant] = None  # Make tenant optional to handle vacant suites

    @property
    def is_vacant(self) -> bool:
        """Check if the suite is currently vacant"""
        return self.tenant is None


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

    """

    # Identity
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    description: Optional[str] = None
    external_id: Optional[str] = None
    address: Optional[Address] = None
    year_built: Optional[PositiveInt] = None

    # Physical Characteristics
    property_type: AssetTypeEnum
    gross_area: PositiveFloat  # sq ft
    net_rentable_area: PositiveFloat  # sq ft

    # Revenue Sources
    rent_roll: RentRoll
    miscellaneous_income: Optional[List[MiscIncome]] = None

    # Expenses
    expenses: Expenses

    # Structural Losses (i.e., vacancy, credit)
    losses: Losses
    
    @property
    def suites(self) -> List[PropertySuite]:
        """List of all suites in the property from both leased and vacant spaces.
        
        Returns:
            List of PropertySuite objects
        """
        # Convert leased spaces to PropertySuite objects
        leased_suites = [
            PropertySuite(
                suite_id=lease.suite,
                area=lease.area,
                tenant=lease.tenant
            ) for lease in self.rent_roll.leases
        ]
        
        # Convert vacant spaces to PropertySuite objects
        vacant_suites = [
            PropertySuite(
                suite_id=suite.suite_id,
                area=suite.area,
                tenant=None
            ) for suite in self.rent_roll.vacant_suites
        ]
        
        return leased_suites + vacant_suites

    @property
    def floors(self) -> List[PropertyFloor]:
        """List all floors in the property from leased spaces.
        
        Returns:
            List of PropertyFloor objects grouped by floor number
        """
        # Create a dictionary to group tenants by floor
        floor_tenants: Dict[str, List[Tenant]] = {}
        floor_areas: Dict[str, float] = {}
        
        # Group leases by floor
        for lease in self.rent_roll.leases:
            if lease.floor:  # Only process leases with floor information
                if lease.floor not in floor_tenants:
                    floor_tenants[lease.floor] = []
                    floor_areas[lease.floor] = 0
                floor_tenants[lease.floor].append(lease.tenant)
                floor_areas[lease.floor] += lease.area
        
        # Convert to PropertyFloor objects
        return [
            PropertyFloor(
                number=int(floor_num) if floor_num.isdigit() else 0,  # Default to 0 if not numeric
                area=floor_areas[floor_num],
                tenants=tenants
            )
            for floor_num, tenants in floor_tenants.items()
        ]

    @property
    def vacant_area(self) -> PositiveFloat:
        """Calculate total vacant area"""
        return self.net_rentable_area - self.rent_roll.total_occupied_area

    @property
    def occupancy_rate(self) -> FloatBetween0And1:
        """Calculate current occupancy rate"""
        return self.rent_roll.total_occupied_area / self.net_rentable_area

    @model_validator(mode="after")
    def validate_areas(self) -> "Property":
        """Validate that NRA doesn't exceed GBA"""
        if self.net_rentable_area > self.gross_area:
            raise ValueError(
                f"Net rentable area ({self.net_rentable_area:,.0f} SF) "
                f"cannot exceed gross area ({self.gross_area:,.0f} SF)"
            )
        return self
