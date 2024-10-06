"""
This module provides custom decimal data types for use with pandas.

It defines DecimalDtype and DecimalExtensionArray classes which allow for
precise decimal arithmetic and storage in pandas DataFrames and Series.
"""

import decimal
import re
from typing import Any, Sequence, Union

import numpy as np
import pandas as pd
import pyarrow as pa
from pandas.api.extensions import (
    ExtensionArray,
    ExtensionDtype,
    register_extension_dtype,
)


@register_extension_dtype
class DecimalDtype(ExtensionDtype):
    """A custom dtype for Decimal objects in pandas.

    This dtype represents decimal numbers with a specified scale.
    It allows for precise decimal arithmetic and storage in pandas DataFrames and Series.

    Attributes:
        name (str): The name of the dtype.
        type (type): The underlying Python type (decimal.Decimal).
        _metadata (tuple): A tuple containing the attributes that should be considered when comparing two instances.
    """

    type: decimal.Decimal
    _match = re.compile(r"decimal\[(\d+)\]")

    base = np.dtype("O")
    _metadata = ("scale",)

    def __new__(cls, scale=0):
        """Create a new instance of DecimalDtype.

        Args:
            scale (int, optional): The scale (number of decimal places) for the dtype. Defaults to 0.

        Returns:
            DecimalDtype: A new instance of DecimalDtype.
        """
        instance = object.__new__(DecimalDtype)
        instance.scale = scale
        return instance

    def __reduce__(self):
        """Reduce the DecimalDtype instance for pickling.

        Returns:
            tuple: A tuple containing the class and its arguments for reconstruction.
        """
        return type(self), (self.scale,)

    def __eq__(self, other):
        """Check if this DecimalDtype is equal to another object.

        Args:
            other (Any): The object to compare with.

        Returns:
            bool: True if the objects are equal, False otherwise.
        """
        if isinstance(other, str):
            try:
                other = self.construct_from_string(other)
            except TypeError:
                return False
        return isinstance(other, DecimalDtype) and other.scale == self.scale

    def __hash__(self):
        """Compute the hash value for this DecimalDtype.

        Returns:
            int: The hash value.
        """
        return hash((type(self), self.scale))

    @property
    def name(self) -> str:
        """Get the name of the dtype.

        Returns:
            str: The name of the dtype, including the scale.
        """
        return f"decimal[{self.scale}]"

    @property
    def type(self) -> decimal.Decimal:
        """Get the type represented by this dtype.

        Returns:
            type: The decimal.Decimal type.
        """
        return decimal.Decimal

    @property
    def kind(self) -> str:
        """The kind of data represented by this dtype.

        Returns:
            str: Returns 'i' for integer, as we're storing the data as scaled integers internally.

        See Also:
            numpy.dtype.kind
        """
        return "i"

    @property
    def na_value(self) -> object:
        """The NA (missing) value for this dtype.

        Returns:
            float: Returns np.nan as the NA value.
        """
        return np.nan

    @property
    def _is_numeric(self) -> bool:
        """Check if this dtype is numeric.

        Returns:
            bool: Always returns True for DecimalDtype.
        """
        return True

    @property
    def _is_boolean(self) -> bool:
        """Check if this dtype is boolean.

        Returns:
            bool: Always returns False for DecimalDtype.
        """
        return False

    @classmethod
    def construct_from_string(cls, string: str) -> "DecimalDtype":
        """Construct an instance from a string.

        Parameters
        ----------
        string : str

        Returns
        -------
        DecimalDtype instance
        """
        if not isinstance(string, str):
            raise TypeError(
                f"'construct_from_string' expects a string, got {type(string)}"
            )

        if string == "decimal":
            return cls()
        out = re.match(cls._match, string)
        if not out:
            raise TypeError(f"Could not construct decimal dtype from {string}")
        return cls(int(out.groups()[0]))

    @classmethod
    def construct_array_type(cls) -> "DecimalExtensionArray":
        """Construct the array type associated with this dtype.

        Returns:
            Type[DecimalExtensionArray]: The DecimalExtensionArray class.
        """
        return DecimalExtensionArray

    def __from_arrow__(
        self, array: Union[pa.Array, pa.ChunkedArray]
    ) -> "DecimalExtensionArray":
        """Construct a DecimalExtensionArray from an Arrow array.

        Args:
            array (Union[pa.Array, pa.ChunkedArray]): The Arrow array to convert.

        Returns:
            DecimalExtensionArray: A new DecimalExtensionArray instance.

        Raises:
            TypeError: If the Arrow array type is not compatible with DecimalDtype.
        """
        if isinstance(array, pa.ChunkedArray):
            array = array.combine_chunks()

        if pa.types.is_decimal(array.type):
            return DecimalExtensionArray(
                array.to_numpy(zero_copy_only=False) / 10**self.scale,
                dtype=self,
            )
        raise TypeError(f"Cannot convert pyarrow type {array.type} to {type(self)}")

    def __repr__(self) -> str:
        """Return a string representation of the DecimalDtype.

        Returns:
            str: A string representation of the DecimalDtype.
        """
        return f"DecimalDtype(scale={self.scale})"


class DecimalExtensionArray(ExtensionArray):
    """A custom array type for storing Decimal values in pandas.

    This array type allows for precise decimal arithmetic and storage in pandas
    DataFrames and Series. It internally stores the data as integers and scales
    them based on the number of decimal places specified in the dtype.

    Attributes:
        _dtype (DecimalDtype): The dtype of the array.
        _data (np.ndarray): The underlying integer array (int64).
    """

    _dtype: DecimalDtype
    _data: np.ndarray  # integer array (int64)

    def __init__(
        self,
        values: Union[Sequence[Any], np.ndarray],
        dtype: DecimalDtype = None,
        copy: bool = False,
    ) -> None:
        """Initialize a new DecimalExtensionArray.

        Args:
            values (Union[Sequence[Any], np.ndarray]): The input values to store in the array.
            dtype (DecimalDtype, optional): The dtype for the array. If not provided, a default DecimalDtype is used.
            copy (bool, optional): Whether to copy the input data. Defaults to False.

        Raises:
            ValueError: If the input values are not numeric.
        """
        if dtype is None:
            dtype = DecimalDtype()
        self._dtype = dtype

        values = np.asarray(values)
        if values.dtype.kind not in "iuf":
            raise ValueError("Values must be numeric")

        self._data = np.round(values * 10**dtype.scale).astype("int64")

        if copy:
            self._data = self._data.copy()

    @classmethod
    def _from_sequence(
        cls: "DecimalExtensionArray",
        scalars: Sequence[Any],
        *,
        dtype: DecimalDtype = None,
        copy: bool = False,
    ) -> "DecimalExtensionArray":
        """Construct a DecimalExtensionArray from a sequence of scalars.

        Args:
            scalars (Sequence[Any]): The input sequence of values.
            dtype (DecimalDtype, optional): The dtype for the array. If not provided, a default DecimalDtype is used.
            copy (bool, optional): Whether to copy the input data. Defaults to False.

        Returns:
            DecimalExtensionArray: A new DecimalExtensionArray instance.
        """
        return cls(scalars, dtype=dtype, copy=copy)

    @classmethod
    def _from_factorized(
        cls: "DecimalExtensionArray",
        values: np.ndarray,
        original: "DecimalExtensionArray",
    ) -> "DecimalExtensionArray":
        """Reconstruct a DecimalExtensionArray from factorized values.

        Args:
            values (np.ndarray): The factorized values.
            original (DecimalExtensionArray): The original array that was factorized.

        Returns:
            DecimalExtensionArray: A new DecimalExtensionArray instance.
        """
        return cls(values, dtype=original.dtype)

    def __getitem__(
        self, item: Union[int, slice, np.ndarray]
    ) -> Union[decimal.Decimal, "DecimalExtensionArray"]:
        if isinstance(item, (int, np.integer)):
            return decimal.Decimal(self._data[item]) / 10**self._dtype.scale
        elif isinstance(item, slice):
            return type(self)(
                self._data[item] / 10**self._dtype.scale, dtype=self.dtype
            )
        elif isinstance(item, np.ndarray):
            if item.dtype == bool:
                return type(self)(
                    self._data[item] / 10**self._dtype.scale, dtype=self.dtype
                )
            return type(self)(
                self._data[item] / 10**self._dtype.scale, dtype=self.dtype
            )
        else:
            raise TypeError(f"Invalid index type: {type(item)}")

    def __setitem__(self, key: Union[int, slice, np.ndarray], value: Any) -> None:
        value = np.asarray(value) * 10**self.dtype.scale
        self._data[key] = np.round(value).astype("int64")

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        for value in self._data:
            yield decimal.Decimal(value) / 10**self._dtype.scale

    @property
    def dtype(self) -> DecimalDtype:
        return self._dtype

    @property
    def nbytes(self) -> int:
        return self._data.nbytes

    def isna(self) -> np.ndarray:
        return np.isnan(self._data)

    def take(
        self, indices: Sequence[int], allow_fill: bool = False, fill_value: Any = None
    ) -> "DecimalExtensionArray":
        if isinstance(indices, list):
            indices = np.array(indices)

        if indices.max() >= len(self) or indices.min() < -len(self):
            raise IndexError("Index out of bounds")

        data = self._data.take(indices)
        if allow_fill and fill_value is not None:
            if isinstance(fill_value, (int, float, decimal.Decimal)):
                fill_value = np.round(fill_value * 10**self._dtype.scale).astype(
                    "int64"
                )
            elif isinstance(fill_value, DecimalExtensionArray):
                fill_value = fill_value._data
            else:
                raise TypeError(f"Invalid fill value type: {type(fill_value)}")
            data[indices == -1] = fill_value
        return type(self)(data / 10**self._dtype.scale, dtype=self.dtype)

    def copy(self) -> "DecimalExtensionArray":
        return type(self)(self._data.copy(), dtype=self.dtype)

    @classmethod
    def _concat_same_type(
        cls: "DecimalExtensionArray", to_concat: Sequence["DecimalExtensionArray"]
    ) -> "DecimalExtensionArray":
        dtypes = {arr.dtype for arr in to_concat}
        if len(dtypes) > 1:
            raise ValueError("Cannot concat DecimalArrays with different dtypes")
        dtype = dtypes.pop()
        data = np.concatenate([arr._data for arr in to_concat])
        return cls(data / 10**dtype.scale, dtype=dtype)

    def astype(self, dtype, copy=True):
        if isinstance(dtype, DecimalDtype):
            if copy:
                return self.copy()
            return self
        return super().astype(dtype, copy)

    def _reduce(self, name, skipna=True, **kwargs):
        data = self._data
        if skipna:
            data = data[~np.isnan(data)]

        op = getattr(data, name)
        result = op(**kwargs)
        return decimal.Decimal(result) / 10**self._dtype.scale

    def factorize(self, na_sentinel=-1):
        codes, uniques = pd.factorize(self._data, na_sentinel=na_sentinel)
        uniques = DecimalExtensionArray(
            uniques / 10**self._dtype.scale, dtype=self.dtype
        )
        return codes, uniques

    def __add__(self, other):
        return self._arithmetic_op(other, np.add)

    def __radd__(self, other):
        return self._arithmetic_op(other, np.add, reverse=True)

    def __sub__(self, other):
        return self._arithmetic_op(other, np.subtract)

    def __rsub__(self, other):
        return self._arithmetic_op(other, np.subtract, reverse=True)

    def __mul__(self, other):
        return self._arithmetic_op(other, np.multiply)

    def __rmul__(self, other):
        return self._arithmetic_op(other, np.multiply, reverse=True)

    def __truediv__(self, other):
        return self._arithmetic_op(other, np.true_divide)

    def __rtruediv__(self, other):
        return self._arithmetic_op(other, np.true_divide, reverse=True)

    def __floordiv__(self, other):
        return self._arithmetic_op(other, np.floor_divide)

    def __rfloordiv__(self, other):
        return self._arithmetic_op(other, np.floor_divide, reverse=True)

    def __mod__(self, other):
        return self._arithmetic_op(other, np.mod)

    def __rmod__(self, other):
        return self._arithmetic_op(other, np.mod, reverse=True)

    def __pow__(self, other):
        return self._arithmetic_op(other, np.power)

    def __rpow__(self, other):
        return self._arithmetic_op(other, np.power, reverse=True)

    def _arithmetic_op(self, other, op, reverse=False):
        """Perform arithmetic operations between DecimalExtensionArrays or with scalars.

        Args:
            other (Union[DecimalExtensionArray, decimal.Decimal, Any]): The other operand.
            op (Callable): The arithmetic operation to perform.
            reverse (bool, optional): If True, reverse the order of operations. Defaults to False.

        Returns:
            DecimalExtensionArray: The result of the arithmetic operation.
        """
        if isinstance(other, (DecimalExtensionArray, decimal.Decimal)):
            other_array = (
                other._data
                if isinstance(other, DecimalExtensionArray)
                else np.array([other]) * 10**self.dtype.scale
            )
            if reverse:
                result = op(other_array, self._data)
            else:
                result = op(self._data, other_array)
            return type(self)(result / 10**self.dtype.scale, dtype=self.dtype)
        return NotImplemented

    def __eq__(self, other):
        return self._comparison_op(other, np.equal)

    def __ne__(self, other):
        return self._comparison_op(other, np.not_equal)

    def __lt__(self, other):
        return self._comparison_op(other, np.less)

    def __le__(self, other):
        return self._comparison_op(other, np.less_equal)

    def __gt__(self, other):
        return self._comparison_op(other, np.greater)

    def __ge__(self, other):
        return self._comparison_op(other, np.greater_equal)

    def _comparison_op(self, other, op):
        """Perform comparison operations between DecimalExtensionArrays or with scalars.

        Args:
            other (Union[DecimalExtensionArray, decimal.Decimal, Any]): The other operand.
            op (Callable): The comparison operation to perform.

        Returns:
            np.ndarray: A boolean array with the result of the comparison.
        """
        if isinstance(other, (DecimalExtensionArray, decimal.Decimal)):
            other_array = (
                other._data
                if isinstance(other, DecimalExtensionArray)
                else np.array([other]) * 10**self.dtype.scale
            )
            return op(self._data, other_array)
        return NotImplemented

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Support NumPy universal functions (ufuncs) on DecimalExtensionArray.

        Args:
            ufunc (callable): The ufunc to apply.
            method (str): The ufunc method to call.
            *inputs: The input arrays or scalars.
            **kwargs: Additional keyword arguments to pass to the ufunc.

        Returns:
            DecimalExtensionArray or NotImplemented: The result of applying the ufunc, or NotImplemented if not supported.
        """
        if method == "__call__":
            scalars = []
            for x in inputs:
                if isinstance(x, DecimalExtensionArray):
                    scalars.append(x._data)
                elif isinstance(x, (int, float, decimal.Decimal)):
                    scalars.append(np.array([x]) * 10**self.dtype.scale)
                else:
                    return NotImplemented
            result = getattr(ufunc, method)(*scalars, **kwargs)
            return type(self)(result / 10**self.dtype.scale, dtype=self.dtype)
        return NotImplemented

    def unique(self):
        """Return unique values of DecimalExtensionArray."""
        unique_data = np.unique(self._data)
        return type(self)(unique_data / 10**self._dtype.scale, dtype=self.dtype)

    def fillna(self, value=None, method=None, limit=None):
        """Fill NA/NaN values using the specified method."""
        if method is not None:
            raise NotImplementedError("fillna with a method is not supported")

        if isinstance(value, (int, float, decimal.Decimal)):
            value = int(value * 10**self._dtype.scale)
        elif isinstance(value, DecimalExtensionArray):
            value = value._data

        filled_data = np.where(np.isnan(self._data), value, self._data)
        return type(self)(filled_data / 10**self._dtype.scale, dtype=self.dtype)

    def dropna(self):
        """Return DecimalExtensionArray without NA/NaN values."""
        valid_mask = ~np.isnan(self._data)
        return type(self)(
            self._data[valid_mask] / 10**self._dtype.scale, dtype=self.dtype
        )

    def argsort(self, ascending=True, kind="quicksort", *args, **kwargs):
        """Return the indices that would sort this array."""
        return np.argsort(self._data, kind=kind, *args, **kwargs)

    def searchsorted(self, value, side="left", sorter=None):
        """Find indices where elements should be inserted to maintain order."""
        if isinstance(value, (int, float, decimal.Decimal)):
            value = int(value * 10**self._dtype.scale)
        elif isinstance(value, DecimalExtensionArray):
            value = value._data
        return self._data.searchsorted(value, side=side, sorter=sorter)

    # Update the __array_function__ method in DecimalExtensionArray
    def __array_function__(self, func, types, args, kwargs):
        if func not in HANDLED_FUNCTIONS:
            return NotImplemented
        if not all(issubclass(t, DecimalExtensionArray) for t in types):
            return NotImplemented
        return HANDLED_FUNCTIONS[func](*args, **kwargs)

    def _formatter(self, boxed=False):
        """
        Formatting function for scalar values.

        This is used in the default '__repr__' and '__str__' implementations.
        """

        def formatter(x):
            if pd.isna(x):
                return "NaN"
            return f"{x:.{self._dtype.scale}f}"

        return formatter


# Array function handling

HANDLED_FUNCTIONS = {}


def implements(numpy_function):
    """Register an __array_function__ implementation for DecimalExtensionArray objects."""

    def decorator(func):
        HANDLED_FUNCTIONS[numpy_function] = func
        return func

    return decorator


@implements(np.sum)
def sum(array, axis=None, dtype=None, out=None, keepdims=False):
    if isinstance(array, DecimalExtensionArray):
        result = np.sum(array._data, axis=axis, dtype=dtype, out=out, keepdims=keepdims)
        return DecimalExtensionArray(result / 10**array.dtype.scale, dtype=array.dtype)
    return NotImplemented


@implements(np.mean)
def mean(array, axis=None, dtype=None, out=None, keepdims=False):
    if isinstance(array, DecimalExtensionArray):
        result = np.mean(
            array._data, axis=axis, dtype=dtype, out=out, keepdims=keepdims
        )
        return result / 10**array.dtype.scale
    return NotImplemented


@implements(np.min)
def min(array, axis=None, out=None, keepdims=False):
    if isinstance(array, DecimalExtensionArray):
        result = np.min(array._data, axis=axis, out=out, keepdims=keepdims)
        return DecimalExtensionArray(result / 10**array.dtype.scale, dtype=array.dtype)
    return NotImplemented


@implements(np.max)
def max(array, axis=None, out=None, keepdims=False):
    if isinstance(array, DecimalExtensionArray):
        result = np.max(array._data, axis=axis, out=out, keepdims=keepdims)
        return DecimalExtensionArray(result / 10**array.dtype.scale, dtype=array.dtype)
    return NotImplemented


@implements(np.cumsum)
def cumsum(array, axis=None, dtype=None, out=None):
    if isinstance(array, DecimalExtensionArray):
        result = np.cumsum(array._data, axis=axis, dtype=dtype, out=out)
        return DecimalExtensionArray(result / 10**array.dtype.scale, dtype=array.dtype)
    return NotImplemented


@implements(np.round)
def round(array, decimals=0, out=None):
    if isinstance(array, DecimalExtensionArray):
        result = np.round(
            array._data / 10**array.dtype.scale, decimals=decimals, out=out
        )
        return DecimalExtensionArray(result * 10**array.dtype.scale, dtype=array.dtype)
    return NotImplemented


@implements(np.concatenate)
def concatenate(arrays, axis=0, out=None):
    if all(isinstance(arr, DecimalExtensionArray) for arr in arrays):
        dtypes = {arr.dtype for arr in arrays}
        if len(dtypes) > 1:
            raise ValueError("Cannot concatenate DecimalArrays with different dtypes")
        dtype = dtypes.pop()
        data = np.concatenate([arr._data for arr in arrays], axis=axis, out=out)
        return DecimalExtensionArray(data / 10**dtype.scale, dtype=dtype)
    return NotImplemented
