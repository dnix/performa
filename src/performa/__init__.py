"""
Performa - Open-Source Real Estate Financial Modeling Framework

Building blocks for sophisticated real estate analysis, from simple property
valuations to complex development projects and institutional-grade deal structuring.
"""

import logging

# Add a NullHandler to the root logger to prevent "No handlers could be found" warnings
# when the library is used in applications that don't configure logging.
# This follows the logging best practice for libraries as described in the Python
# logging documentation. Applications using this library can configure their own
# logging handlers as needed.
logging.getLogger(__name__).addHandler(logging.NullHandler())
