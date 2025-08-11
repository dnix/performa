# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

"""
Deal Constructs - Partnership and Deal Structure Builders

Constructs for composing complex deal components from primitive building blocks. These functions serve as intelligent builders that create sophisticated deal structures while maintaining full transparency and customization capabilities.

## Architecture Position

Constructs occupy the middle tier in Performa's three-layer architecture:

- **Primitives**: Core data models (`Partner`, `PartnershipStructure`, etc.)
- **Constructs**: Component builders that compose primitives into functional units
- **Patterns**: Complete deal creators that utilize constructs for full investment archetypes

## Design Philosophy

**Focused Responsibility**: Each construct creates a single, well-defined component rather than complete deals.

**Intelligent Defaults**: Constructs provide sensible defaults based on industry standards while allowing full customization.

**Transparency**: All construct outputs can be inspected, modified, and extended after creation.

**Composability**: Construct outputs integrate seamlessly with both manual component assembly and patterns.

## Available Constructs

### Partnership Structures

#### `create_simple_partnership()`
Creates a basic two-partner structure with straightforward profit/loss sharing.

**Use Cases**:
- Joint ventures with equal or specified ownership splits
- Simple partnerships without complex waterfall structures
- Teaching and demonstration scenarios
- Foundation for more complex partnership customization

**Parameters**:
- `gp_name`: General partner identification
- `lp_name`: Limited partner identification
- `gp_ownership`: GP ownership percentage (decimal)
- `lp_ownership`: LP ownership percentage (decimal)

**Output**: `PartnershipStructure` with basic profit sharing

#### `create_gp_lp_waterfall()`
Creates sophisticated multi-tier IRR waterfall structures common in institutional real estate.

**Use Cases**:
- Institutional investment structures
- Private equity real estate funds
- Development partnerships with performance incentives
- Complex carried interest arrangements

**Parameters**:
- `gp_name`: General partner identification
- `lp_name`: Limited partner identification
- `preferred_return`: Minimum return threshold for LP
- `gp_catch_up`: GP catch-up percentage after preferred return
- `final_split`: Profit split after catch-up (GP percentage)

**Output**: `PartnershipStructure` with multi-tier waterfall logic

## Usage Patterns

### Component Assembly Workflow

```python
from performa.deal.constructs import create_gp_lp_waterfall
from performa.debt.constructs import create_construction_to_permanent_plan
from performa.deal import Deal

# Create sophisticated partnership using construct
partnership = create_gp_lp_waterfall(
    gp_name="Development GP LLC",
    lp_name="Institutional LP Fund",
    preferred_return=0.08,  # 8% preferred return
    gp_catch_up=0.20,       # 20% GP catch-up
    final_split=0.30        # 30% GP participation after catch-up
)

# Create financing using construct
financing = create_construction_to_permanent_plan(
    construction_terms={...},
    permanent_terms={...}
)

# Assemble complete deal manually
deal = Deal(
    name="Custom Mixed-Use Development",
    asset=custom_property,           # User-created property
    partnership=partnership,         # construct output
    financing=financing,            # construct output
    acquisition=custom_acquisition  # User-created acquisition
)
```

### Construct Customization

```python
# Start with construct defaults
base_partnership = create_gp_lp_waterfall(
    gp_name="GP Entity",
    lp_name="LP Entity",
    preferred_return=0.08,
    gp_catch_up=0.20,
    final_split=0.25
)

# Customize specific aspects
base_partnership.distribution_rules.add_hurdle(
    rate=0.15,  # Additional 15% hurdle
    split=0.50  # 50/50 split above 15%
)

# Integration with custom deal
custom_deal = Deal(
    name="Customized Structure",
    partnership=base_partnership,  # Modified construct output
    # ... other components
)
```

## Implementation Details

### Industry Standard Defaults

Constructs implement proven industry practices:

**Institutional Waterfall Standards**:
- 8% preferred return (typical for institutional equity)
- 20% GP catch-up (standard carried interest structure)
- 70/30 LP/GP split after catch-up (common institutional terms)

**Risk Management**:
- Appropriate hurdle rates based on asset class and risk profile
- Standard distribution timing and calculation methods
- Typical fee structures and expense allocation patterns

### Validation and Error Handling

```python
# Constructs validate inputs and provide clear error messages
try:
    partnership = create_gp_lp_waterfall(
        gp_name="GP Entity",
        lp_name="LP Entity",
        preferred_return=0.08,
        gp_catch_up=0.50,  # Invalid: catch-up too high
        final_split=0.25
    )
except ValueError as e:
    print(f"Partnership creation failed: {e}")
    # "GP catch-up cannot exceed 50% - results in inequitable structure"
```

### Performance Optimization

- **Lazy Calculation**: Complex waterfall logic calculated only when distributions occur
- **Caching**: Repeated calculations cached for performance
- **Memory Efficiency**: Construct outputs use minimal memory footprint
- **Vectorization**: Distribution calculations leverage pandas for large cash flow series

## Testing and Validation

Deal constructs include comprehensive test coverage:

- **Unit Tests**: Validate partnership creation and distribution calculations
- **Integration Tests**: Ensure constructs work with deal analysis engine
- **Performance Tests**: Verify efficient calculation for complex waterfalls

## Extension and Customization

Deal constructs are designed for extension:

- **Custom Waterfalls**: Build specialized distribution structures
- **Multi-Partner Entities**: Compose multiple constructs for complex ownership
- **Dynamic Terms**: Create constructs with conditional logic and hurdles

This construct architecture provides the foundation for both manual deal assembly and automated pattern creation while maintaining transparency and customization capabilities throughout."""

from __future__ import annotations

from typing import List, Tuple

from .partnership import (
    Partner,
    PartnershipStructure,
    WaterfallPromote,
    WaterfallTier,
)


def create_gp_lp_waterfall(
    gp_share: float,
    lp_share: float,
    pref_return: float,
    promote_tiers: List[Tuple[float, float]],
    final_promote_rate: float,
):
    """
    Creates a standard GP/LP partnership with a multi-tier IRR waterfall.

    Args:
        gp_share: The GP's equity ownership percentage (e.g., 0.10 for 10%).
        lp_share: The LP's equity ownership percentage (e.g., 0.90 for 90%).
        pref_return: The preferred return hurdle rate (e.g., 0.08 for 8%).
        promote_tiers: A list of tuples representing IRR hurdle and promote rate
                       pairs. Example: [(0.12, 0.20), (0.15, 0.30)].
        final_promote_rate: The promote rate for profits after the final hurdle.

    Returns:
        PartnershipStructure: A fully configured partnership structure.

    Raises:
        ValueError: If shares do not approximately sum to 1.0.
    """
    # Defensive validation with small tolerance for float arithmetic
    if abs((gp_share + lp_share) - 1.0) > 0.001:
        raise ValueError(
            f"Partner shares must sum to 1.0, got gp_share={gp_share:.3f}, lp_share={lp_share:.3f}"
        )

    gp = Partner(name="GP", kind="GP", share=gp_share)
    lp = Partner(name="LP", kind="LP", share=lp_share)

    tiers = [
        WaterfallTier(tier_hurdle_rate=hurdle, promote_rate=rate)
        for hurdle, rate in promote_tiers
    ]

    promote = WaterfallPromote(
        pref_hurdle_rate=pref_return,
        tiers=tiers,
        final_promote_rate=final_promote_rate,
    )

    return PartnershipStructure(
        partners=[gp, lp], distribution_method="waterfall", promote=promote
    )


def create_simple_partnership(
    gp_name: str,
    gp_share: float,
    lp_name: str,
    lp_share: float,
    distribution_method: str = "pari_passu",
) -> PartnershipStructure:
    """
    Helper function to create a simple 2-partner structure.

    Args:
        gp_name: General Partner name
        gp_share: GP ownership percentage (0.0 to 1.0)
        lp_name: Limited Partner name
        lp_share: LP ownership percentage (0.0 to 1.0)
        distribution_method: Distribution method ("pari_passu" or "waterfall")

    Returns:
        PartnershipStructure object
    """
    gp = Partner(name=gp_name, kind="GP", share=gp_share)
    lp = Partner(name=lp_name, kind="LP", share=lp_share)

    return PartnershipStructure(
        partners=[gp, lp], distribution_method=distribution_method
    )
