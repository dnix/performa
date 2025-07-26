# Copyright 2024-2025 David Gordon Nix
# SPDX-License-Identifier: Apache-2.0

import numpy as np
import pandas as pd


def equity_multiple(cash_flows: pd.Series) -> float:
    """Compute equity multiple from cash flows"""
    invested = cash_flows.where(cash_flows < 0, 0).sum()
    returned = cash_flows.where(cash_flows > 0, 0).sum()
    if invested == 0:
        return np.inf
    return returned / abs(invested)

# TODO: put static methods in this helper file, if re-used across classes
