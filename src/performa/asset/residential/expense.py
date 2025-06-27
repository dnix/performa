from __future__ import annotations

from typing import List
from uuid import UUID, uuid4

from pydantic import Field

from ...common.base import CapExItemBase, OpExItemBase
from ...common.primitives import Model


class ResidentialOpExItem(OpExItemBase):
    """
    Residential-specific operating expense.
    
    Inherits all functionality from OpExItemBase for now, but provides
    type safety and clear semantic distinction for residential properties.
    Future enhancements may include residential-specific features like
    utility billing back to tenants (RUBS).
    """
    pass


class ResidentialCapExItem(CapExItemBase):
    """
    Residential-specific capital expense.
    
    Commonly used for maintenance reserves, building improvements,
    and unit renovation projects.
    """
    pass


class ResidentialExpenses(Model):
    """
    Container for all residential property expenses.
    """
    uid: UUID = Field(default_factory=uuid4, description="Unique identifier for this expense container")
    operating_expenses: List[ResidentialOpExItem] = Field(default_factory=list)
    capital_expenses: List[ResidentialCapExItem] = Field(default_factory=list) 