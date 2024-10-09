import pandas as pd

def equity_multiple(cash_flows: pd.Series) -> float:
    """Compute equity multiple from cash flows"""
    return cash_flows[cash_flows > 0].sum() / abs(cash_flows[cash_flows < 0].sum())

# TODO: put static methods in this helper file, if re-used across classes
