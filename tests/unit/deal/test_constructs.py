# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import pytest

from performa.deal import (
    PartnershipStructure,
    create_gp_lp_waterfall,
)


def test_create_gp_lp_waterfall_basic():
    partnership: PartnershipStructure = create_gp_lp_waterfall(
        gp_share=0.25,
        lp_share=0.75,
        pref_return=0.08,
        promote_tiers=[(0.12, 0.20), (0.15, 0.30)],
        final_promote_rate=0.35,
    )

    # Structure
    assert partnership.distribution_method == "waterfall"
    assert len(partnership.partners) == 2

    gp = partnership.get_partner_by_name("GP")
    lp = partnership.get_partner_by_name("LP")
    assert gp is not None and abs(gp.share - 0.25) < 1e-9
    assert lp is not None and abs(lp.share - 0.75) < 1e-9

    # Promote structure
    assert partnership.promote is not None
    tiers, final_rate = partnership.promote.all_tiers
    # Pref tier + two tiers
    assert len(tiers) == 3
    assert final_rate == 0.35


def test_create_gp_lp_waterfall_invalid_shares_raises():
    with pytest.raises(ValueError):
        create_gp_lp_waterfall(
            gp_share=0.40,  # sums to 1.10
            lp_share=0.70,
            pref_return=0.08,
            promote_tiers=[(0.12, 0.20)],
            final_promote_rate=0.25,
        )
