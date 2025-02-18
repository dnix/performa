from typing import Annotated, Union

from pydantic import Field

from ._expense import CapExItem, ExpenseItem
from ._revenue import Lease, RentEscalation, VacantSuite

# Revenue types
AnyRentItem = Union[Lease, VacantSuite]
AnyEscalation = RentEscalation

# Expense types
AnyExpenseItem = Annotated[
    Union[ExpenseItem, CapExItem], Field(discriminator="category")
]
