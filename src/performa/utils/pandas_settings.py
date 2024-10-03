import pandas as pd

from .money import Money, MoneyDtype


class PandasSettings:
    @staticmethod
    def apply_custom_settings():
        """Apply custom pandas settings."""
        # Set the display format for floating-point numbers
        pd.set_option(
            "display.float_format",
            lambda x: f"${x:.2f}" if isinstance(x, (float, Money)) else str(x),
        )
        # Register the MoneyDtype with pandas
        pd.api.extensions.register_extension_dtype(MoneyDtype)
        # NOTE: see money.py for more Money related configuration

    @staticmethod
    def reset_settings():
        """Reset pandas settings to default values."""
        pd.reset_option("all")
