# Package initialization can be done in submodules as needed.

# Import the custom decimal types to ensure they're registered, but don't expose them
from .utils import decimal as _  # import to register
