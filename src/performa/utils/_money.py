from typing import Union

import numpy as np
import pandas as pd


class Money:
    """
    A class to represent monetary values with precision.
    Internally stores the value in cents (as integers) to avoid floating-point errors.
    """

    __slots__ = ("cents",)

    def __init__(self, dollars: Union[int, float, str]):
        """Initialize a Money object with a value in dollars."""
        # Convert dollars to cents using banker's rounding
        amount = float(dollars)
        cents = amount * 100
        self.cents = int(round(cents))  # Banker's rounding

    @classmethod
    def from_cents(cls, cents: int) -> "Money":
        """Create a Money object from a cent value."""
        obj = cls.__new__(cls)
        obj.cents = cents
        return obj

    def to_dollars(self) -> float:
        """Convert the internal cents representation to dollars."""
        return self.cents / 100

    def __repr__(self) -> str:
        """Return a string representation of the monetary value."""
        return f"${self.to_dollars():.2f}"

    def __int__(self) -> int:
        """Convert the Money object to an integer (dollars)."""
        return int(self.to_dollars())

    def __float__(self) -> float:
        """Convert the Money object to a float (dollars)."""
        return self.to_dollars()

    def __neg__(self) -> "Money":
        """Return the negation of the Money object."""
        return Money.from_cents(-self.cents)

    # Arithmetic operations with banker's rounding
    def __add__(self, other: Union["Money", int, float]) -> "Money":
        """Add another Money object or a numeric value to this Money object."""
        if isinstance(other, Money):
            total_cents = self.cents + other.cents
        else:
            other_cents = int(round(float(other) * 100))
            total_cents = self.cents + other_cents
        return Money.from_cents(total_cents)

    def __radd__(self, other: Union[int, float]) -> "Money":
        return self.__add__(other)

    def __sub__(self, other: Union["Money", int, float]) -> "Money":
        """Subtract another Money object or a numeric value from this Money object."""
        if isinstance(other, Money):
            total_cents = self.cents - other.cents
        else:
            other_cents = int(round(float(other) * 100))
            total_cents = self.cents - other_cents
        return Money.from_cents(total_cents)

    def __rsub__(self, other: Union[int, float]) -> "Money":
        if isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            total_cents = other_cents - self.cents
            return Money.from_cents(total_cents)
        else:
            return NotImplemented

    def __mul__(self, other: Union[int, float]) -> "Money":
        """Multiply this Money object by a scalar value."""
        if isinstance(other, (int, float)):
            result = self.cents * other
            result_cents = int(round(result))  # Banker's rounding
            return Money.from_cents(result_cents)
        else:
            return NotImplemented

    def __rmul__(self, other: Union[int, float]) -> "Money":
        return self.__mul__(other)

    def __truediv__(self, other: Union[int, float]) -> "Money":
        """Divide this Money object by a scalar value."""
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("division by zero")
            result = self.cents / other
            result_cents = int(round(result))  # Banker's rounding
            return Money.from_cents(result_cents)
        else:
            return NotImplemented

    def __floordiv__(self, other: Union[int, float]) -> "Money":
        """Perform floor division."""
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("division by zero")
            result_cents = self.cents // other
            return Money.from_cents(int(result_cents))
        else:
            return NotImplemented

    # Comparison methods
    def __eq__(self, other: Union["Money", int, float]) -> bool:
        if isinstance(other, Money):
            return self.cents == other.cents
        else:
            other_cents = int(round(float(other) * 100))
            return self.cents == other_cents

    def __ne__(self, other: Union["Money", int, float]) -> bool:
        return not self == other

    def __lt__(self, other: Union["Money", int, float]) -> bool:
        if isinstance(other, Money):
            return self.cents < other.cents
        else:
            other_cents = int(round(float(other) * 100))
            return self.cents < other_cents

    def __le__(self, other: Union["Money", int, float]) -> bool:
        return self < other or self == other

    def __gt__(self, other: Union["Money", int, float]) -> bool:
        if isinstance(other, Money):
            return self.cents > other.cents
        else:
            other_cents = int(round(float(other) * 100))
            return self.cents > other_cents

    def __ge__(self, other: Union["Money", int, float]) -> bool:
        return self > other or self == other


class MoneyDtype(pd.api.extensions.ExtensionDtype):
    """
    A custom dtype for Money objects in pandas.
    """

    name = "money"
    type = Money
    kind = "O"
    na_value = pd.NA

    @property
    def _is_numeric(self):
        return True

    @property
    def _is_boolean(self):
        return False

    @classmethod
    def construct_array_type(cls):
        return MoneyArray


class MoneyArray(pd.api.extensions.ExtensionArray):
    """
    A custom array class for storing Money objects in pandas DataFrames.
    """

    def __init__(self, values, mask=None):
        """Initialize the MoneyArray with a list of values."""
        if isinstance(values, MoneyArray):
            self._data = values._data.copy()
            self._mask = values._mask.copy()
        else:
            values = np.asarray(values)

            if mask is None:
                mask = pd.isna(values)
            else:
                mask = np.asarray(mask)

            if np.issubdtype(values.dtype, np.integer):
                # Values are in cents
                self._data = values.astype(int)
            else:
                # Values are in dollars, convert to cents
                self._data = np.where(
                    mask, 0, np.round(values.astype(float) * 100).astype(int)
                )
            self._mask = mask

    @classmethod
    def _from_sequence(cls, scalars, dtype=None, copy=False):
        """Create a MoneyArray from a sequence of values."""
        return cls(scalars)

    @classmethod
    def _from_factorized(cls, values, original):
        """Create a MoneyArray from factorized values."""
        return cls(values)

    def __getitem__(self, item):
        """Get a Money object at the specified index."""
        if isinstance(item, (int, np.integer)):
            if self._mask[item]:
                return pd.NA
            return Money.from_cents(self._data[item])
        else:
            return MoneyArray(self._data[item], mask=self._mask[item])

    def __len__(self):
        """Get the length of the MoneyArray."""
        return len(self._data)

    def __repr__(self):
        """Return a string representation of the MoneyArray."""
        money_list = [
            pd.NA if mask else Money.from_cents(cents)
            for cents, mask in zip(self._data, self._mask)
        ]
        money_str = ", ".join(str(money) for money in money_list)
        return f"MoneyArray([{money_str}])"

    def __array__(self, dtype=None):
        """Return the array representation."""
        return self.to_numpy(dtype=dtype)

    def to_numpy(self, dtype=None, copy=False, na_value=pd.api.extensions.no_default):
        """Convert the MoneyArray to a numpy array of float values."""
        data = self._data.astype(float) / 100
        if na_value is pd.api.extensions.no_default:
            na_value = np.nan
        data[self._mask] = na_value
        return data

    @property
    def dtype(self):
        """Get the dtype of the MoneyArray."""
        return MoneyDtype()

    @property
    def nbytes(self):
        """Get the number of bytes occupied by the MoneyArray."""
        return self._data.nbytes + self._mask.nbytes

    def isna(self):
        """Check for NA values in the MoneyArray."""
        return self._mask

    def take(self, indices, allow_fill=False, fill_value=None):
        """Take elements from the MoneyArray at the given indices."""
        data = self._data.take(indices)
        mask = self._mask.take(indices)

        if allow_fill:
            fill_value = pd.NA if fill_value is None else fill_value
            fill_mask = indices == -1
            data[fill_mask] = 0
            mask[fill_mask] = True

        return MoneyArray(data, mask=mask)

    def copy(self):
        """Create a copy of the MoneyArray."""
        return MoneyArray(self._data.copy(), mask=self._mask.copy())

    def _concat_same_type(self, to_concat):
        """Concatenate multiple MoneyArrays."""
        data = np.concatenate([x._data for x in to_concat])
        mask = np.concatenate([x._mask for x in to_concat])
        return MoneyArray(data, mask=mask)

    def astype(self, dtype, copy=True):
        """Convert the MoneyArray to another dtype."""
        if pd.api.types.is_dtype_equal(dtype, MoneyDtype()):
            return self.copy() if copy else self
        elif pd.api.types.is_float_dtype(dtype):
            return self.to_numpy(dtype=float, copy=copy)
        elif pd.api.types.is_integer_dtype(dtype):
            data = self._data.copy() if copy else self._data
            data[self._mask] = 0  # or use a sentinel value
            return data
        else:
            return np.array(
                [
                    float(cents) / 100 if not mask else pd.NA
                    for cents, mask in zip(self._data, self._mask)
                ],
                dtype=dtype,
                copy=copy,
            )

    def _formatter(self, boxed=False):
        def format_item(item, mask):
            if mask:
                return "NaN"
            return str(Money.from_cents(item))

        return format_item

    # Arithmetic operations with banker's rounding
    def __add__(self, other):
        if isinstance(other, MoneyArray):
            result_data = self._data + other._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result_data = self._data + other.cents
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result_data = self._data + other_cents
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        return MoneyArray(result_data, mask=result_mask)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if isinstance(other, MoneyArray):
            result_data = self._data - other._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result_data = self._data - other.cents
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result_data = self._data - other_cents
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        return MoneyArray(result_data, mask=result_mask)

    def __rsub__(self, other):
        if isinstance(other, MoneyArray):
            result_data = other._data - self._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result_data = other.cents - self._data
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result_data = other_cents - self._data
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        return MoneyArray(result_data, mask=result_mask)

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            result = self._data * other
            result_data = np.round(result).astype(int)  # Banker's rounding
            result_mask = self._mask.copy()
            return MoneyArray(result_data, mask=result_mask)
        else:
            return NotImplemented

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            if other == 0:
                raise ZeroDivisionError("division by zero")
            result = self._data / other
            result_data = np.round(result).astype(int)  # Banker's rounding
            result_mask = self._mask.copy()
            return MoneyArray(result_data, mask=result_mask)
        elif isinstance(other, Money):
            # Return array of floats (ratios)
            with np.errstate(divide="ignore", invalid="ignore"):
                result_data = self._data / other.cents
                result_data[self._mask] = np.nan
            return result_data
        elif isinstance(other, MoneyArray):
            # Element-wise division, return array of floats
            with np.errstate(divide="ignore", invalid="ignore"):
                result_data = np.true_divide(self._data, other._data)
                result_mask = self._mask | other._mask
                result_data[result_mask] = np.nan
            return result_data
        else:
            return NotImplemented

    def __rtruediv__(self, other):
        if isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            with np.errstate(divide="ignore", invalid="ignore"):
                result_data = np.true_divide(other_cents, self._data)
                result_data[self._mask] = np.nan
            return result_data
        else:
            return NotImplemented

    def __neg__(self):
        """Return the negation of the MoneyArray."""
        return MoneyArray(-self._data, mask=self._mask.copy())

    # Comparison methods
    def __eq__(self, other):
        """Define equality comparison for MoneyArray."""
        if isinstance(other, MoneyArray):
            result = self._data == other._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result = self._data == other.cents
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result = self._data == other_cents
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        result[result_mask] = False
        return result

    def __ne__(self, other):
        return ~(self == other)

    def __lt__(self, other):
        if isinstance(other, MoneyArray):
            result = self._data < other._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result = self._data < other.cents
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result = self._data < other_cents
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        result[result_mask] = False
        return result

    def __le__(self, other):
        return (self < other) | (self == other)

    def __gt__(self, other):
        if isinstance(other, MoneyArray):
            result = self._data > other._data
            result_mask = self._mask | other._mask
        elif isinstance(other, Money):
            result = self._data > other.cents
            result_mask = self._mask.copy()
        elif isinstance(other, (int, float)):
            other_cents = int(round(float(other) * 100))
            result = self._data > other_cents
            result_mask = self._mask.copy()
        else:
            return NotImplemented
        result[result_mask] = False
        return result

    def __ge__(self, other):
        return (self > other) | (self == other)

    # Aggregation methods
    def sum(self, skipna=True):
        """Return the sum of the array elements as a Money instance."""
        return self._reduce("sum", skipna=skipna)

    def mean(self, skipna=True):
        """Return the mean of the array elements as a float."""
        return self._reduce("mean", skipna=skipna)

    def min(self, skipna=True):
        """Return the minimum value as a Money instance."""
        return self._reduce("min", skipna=skipna)

    def max(self, skipna=True):
        """Return the maximum value as a Money instance."""
        return self._reduce("max", skipna=skipna)

    def std(self, skipna=True):
        """Return the standard deviation of the array elements as a float."""
        return self._reduce("std", skipna=skipna)

    def var(self, skipna=True):
        """Return the variance of the array elements as a float."""
        return self._reduce("var", skipna=skipna)

    def _reduce(self, name, skipna=True):
        # Map the reduction name to a numpy function
        reduction_map = {
            "sum": np.sum,
            "mean": np.mean,
            "min": np.min,
            "max": np.max,
            "prod": np.prod,
            "std": np.std,
            "var": np.var,
        }

        if name in reduction_map:
            func = reduction_map[name]
            data = self._data

            if skipna:
                data = data[~self._mask]

            if len(data) == 0:
                return pd.NA

            result = func(data)

            if name in ["sum", "min", "max", "prod"]:
                # Return a Money instance
                return Money.from_cents(int(result))
            elif name in ["mean", "std", "var"]:
                # Return as float (in dollars)
                return result / 100
            else:
                raise NotImplementedError(f"Reduction '{name}' not implemented.")
        else:
            raise NotImplementedError(f"Reduction '{name}' not implemented.")

    # Implement __array_ufunc__
    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Handle NumPy ufuncs."""
        # Extract the underlying data
        args = []
        masks = []
        for x in inputs:
            if isinstance(x, MoneyArray):
                args.append(x._data)
                masks.append(x._mask)
            else:
                args.append(x)
                masks.append(None)

        if method == "__call__":
            result = getattr(ufunc, method)(*args, **kwargs)
            if isinstance(result, tuple):
                return tuple(
                    MoneyArray(res) if res.dtype.kind in ("i", "u") else res
                    for res in result
                )
            else:
                if isinstance(result, np.ndarray) and result.dtype.kind in ("i", "u"):
                    # Combine masks
                    result_mask = np.logical_or.reduce(
                        [m for m in masks if m is not None]
                    )
                    return MoneyArray(result, mask=result_mask)
                else:
                    # Return as is (e.g., float array)
                    return result
        else:
            # For other methods like 'reduce', 'accumulate', etc.
            return NotImplemented

    # Implement __array_function__
    def __array_function__(self, func, types, args, kwargs):
        """Handle NumPy array functions."""
        if func not in HANDLED_FUNCTIONS:
            return NotImplemented

        # Helper function to recursively unwrap MoneyArray instances
        def unwrap(x):
            if isinstance(x, MoneyArray):
                return x._data
            elif isinstance(x, (list, tuple)):
                return [unwrap(i) for i in x]
            else:
                return x

        # Recursively unwrap args
        args = tuple(unwrap(arg) for arg in args)
        result = func(*args, **kwargs)

        if isinstance(result, np.ndarray):
            if result.dtype.kind in ("i", "u"):  # Integer or unsigned integer
                return MoneyArray(result)
            else:
                return result / 100  # Convert cents to dollars if necessary
        elif isinstance(result, (int, np.integer)):
            return Money.from_cents(int(result))
        elif isinstance(result, (float, np.floating)):
            return result / 100
        else:
            return result


# Set of functions to handle in __array_function__
HANDLED_FUNCTIONS = {
    np.concatenate,
    np.mean,
    np.sum,
    np.min,
    np.max,
    np.std,
    np.var,
}


@pd.api.extensions.register_series_accessor("money")
@pd.api.extensions.register_dataframe_accessor("money")
class MoneyAccessor:
    def __init__(self, pandas_obj):
        self._obj = pandas_obj

    @property
    def dollars(self):
        return self._obj.astype(float)

    @property
    def cents(self):
        return (self._obj * 100).astype(int)

    def format(self, decimals=2):
        return self._obj.apply(lambda x: f"${x:.{decimals}f}")


if __name__ == "__main__":
    # Test Money class
    m1 = Money(10.99)
    m2 = Money(25.50)
    print(f"m1: {m1}")
    print(f"m2: {m2}")
    print(f"m1 + m2: {m1 + m2}")
    print(f"m1 + m2 == 36.49: {m1 + m2 == 36.49}")

    # Test arithmetic operations with rounding
    m3 = Money(1.00)
    result_div = m3 / 3
    print(f"Result of {m3} divided by 3: {result_div}")

    # Test with dictionary input
    data = {
        "Price": [10.99, 25.50, 5.75],
    }
    df = pd.DataFrame(data, dtype="money")
    print("\nDataFrame with Money dtype (from dict):")
    print(df)
    print("\nDataFrame info:")
    print(df.info())

    # Test with list input
    data = [10.99, 25.50, 5.75]
    df = pd.DataFrame(data, dtype="money")
    print("\nDataFrame with Money dtype (from list):")
    print(df)
    print("\nDataFrame info:")
    print(df.info())

    # Test mixed data types
    mixed_data = {
        "Item": ["Product A", "Product B", "Product C"],
        "Price": [10.99, 25.50, 5.75],
    }
    df_mixed = pd.DataFrame(mixed_data)
    df_mixed["Price"] = df_mixed["Price"].astype("money")
    print("\nDataFrame with mixed types:")
    print(df_mixed)
    print("\nDataFrame info:")
    print(df_mixed.info())

    # Additional test to check internal representation
    print("\nInternal representation of Price column:")
    print(df_mixed["Price"].array._data)

    # Test arithmetic operations on MoneyArray
    data1 = [10.99, 25.50, 5.75]
    data2 = [5.00, 15.25, 2.25]
    money_array1 = MoneyArray(data1)
    money_array2 = MoneyArray(data2)

    # Addition
    result_add = money_array1 + money_array2
    print("\nAddition result:", result_add)

    # Subtraction
    result_sub = money_array1 - money_array2
    print("Subtraction result:", result_sub)

    # Multiplication
    result_mul = money_array1 * 2
    print("Multiplication result:", result_mul)

    # Division
    result_div = money_array1 / 3
    print("Division result:", result_div)

    # Test aggregation methods
    total = money_array1.sum()
    average = money_array1.mean()
    print(f"\nTotal of money_array1: {total}")
    print(f"Average of money_array1: ${average:.2f}")

    # Test MoneyArray with numpy ufuncs
    print("\nTest ufunc support:")
    money_array = MoneyArray([10.00, 20.00, 30.00, None])
    print("Original MoneyArray:", money_array)

    # Addition using np.add
    result_add = np.add(money_array, 5.00)
    print("np.add result:", result_add)

    # Multiplication using np.multiply
    result_mul = np.multiply(money_array, 2)
    print("np.multiply result:", result_mul)

    # Test numpy functions
    concatenated = np.concatenate([money_array, result_add])
    print("Concatenated MoneyArray:", concatenated)

    mean_value = np.mean(money_array)
    print(f"Mean value: ${mean_value:.2f}")
