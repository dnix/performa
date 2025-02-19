from typing import Annotated, Union

from pydantic import Field

from ._expense import CapExItem, ExpenseItem
from ._revenue import Lease, RentEscalation, VacantSuite

# Revenue types

#: Alias for any appropriate rental item (lease or vacant suite).
AnyRentItem = Union[Lease, VacantSuite]

#: Alias for the escalation strategy in revenue modeling.
AnyEscalation = RentEscalation

# Expense types

#: Type alias for any expense item (operating or capital), using 'category' as the discriminator.
AnyExpenseItem = Annotated[
    Union[ExpenseItem, CapExItem], Field(discriminator="category")
]
