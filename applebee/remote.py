"""Read a weather matrix in byte ranges, so a run costs only the cells it touches.

The matrices are ``(n_cells, n_days)`` float32 in C order, so **one cell's whole
time series is one contiguous run of bytes** -- 8,764 of them for six years. A
single location can therefore be simulated from two ranged reads against exactly
the files the local runs memory-map, with no second copy of the data kept in a
different shape.

That is what makes a hosted point forecast cheap. The Northeast weather is
1.7 GB, but answering "what does the model predict at this orchard" touches
18 KB of it::

    grid = load_matrices_remote("https://bucket.s3.amazonaws.com/weather/northeast",
                                "northeast_tmean")
    grid.series(col, row, "2015-05-07", 20)     # the same call as a local grid

:class:`RemoteMatrix` stands in for the memory-mapped array inside a
:class:`~applebee.weather.WeatherGrid`, so nothing downstream knows the
difference. Reads go through a :class:`Ranges` reader, of which there are two:
:class:`HttpRanges` for S3 or any server honouring ``Range``, and
:class:`FileRanges` for a local path -- which is what the tests use, so none of
this needs a network to verify.
"""

from __future__ import annotations

import io
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from .weather import WeatherGrid

# The .npy header is padded to a 64-byte boundary and is far smaller than this
# for any matrix we write; one probe read therefore always contains all of it.
HEADER_PROBE_BYTES = 4096

# Rows are 8.8 KB for six years, so a few thousand cached rows is tens of MB --
# enough to hold a fan-out worker's whole block without a second request.
DEFAULT_ROW_CACHE = 4096


class RangeNotHonoured(RuntimeError):
    """The server answered with the whole object instead of the range asked for.

    Raised rather than accepted: a 200 where a 206 was expected means the reader
    would silently mistake the head of the file for the row it wanted.
    """


class Ranges(Protocol):
    """Somewhere bytes can be read from by offset."""

    def read(self, offset: int, length: int) -> bytes: ...

    def read_all(self) -> bytes: ...


@dataclass
class HttpRanges:
    """Byte ranges over HTTP -- S3, CloudFront, or any server honouring ``Range``."""

    url: str
    timeout: float = 30.0

    def read(self, offset: int, length: int) -> bytes:
        request = urllib.request.Request(
            self.url, headers={"Range": f"bytes={offset}-{offset + length - 1}"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 206:
                raise RangeNotHonoured(
                    f"{self.url} answered {response.status}, not 206 Partial Content"
                )
            return response.read()

    def read_all(self) -> bytes:
        with urllib.request.urlopen(self.url, timeout=self.timeout) as response:
            return response.read()


@dataclass
class S3Ranges:
    """Byte ranges from a private S3 object, through the Lambda's own role.

    Kept separate from :class:`HttpRanges` because a bucket the platform can
    read but the public cannot is the point: the data is redistributable, but
    paying egress for anyone who wants 1.7 GB of it is not.
    """

    bucket: str
    key: str
    client: object | None = None

    def _s3(self):
        if self.client is None:
            import boto3  # provided by the Lambda runtime

            self.client = boto3.client("s3")
        return self.client

    def read(self, offset: int, length: int) -> bytes:
        response = self._s3().get_object(
            Bucket=self.bucket, Key=self.key,
            Range=f"bytes={offset}-{offset + length - 1}")
        return response["Body"].read()

    def read_all(self) -> bytes:
        return self._s3().get_object(Bucket=self.bucket, Key=self.key)["Body"].read()


@dataclass
class FileRanges:
    """Byte ranges from a local file.

    Present so the remote path can be exercised without a network, and so a
    deployment can point at a local copy without changing anything else.
    """

    path: Path

    def read(self, offset: int, length: int) -> bytes:
        with Path(self.path).open("rb") as handle:
            handle.seek(offset)
            return handle.read(length)

    def read_all(self) -> bytes:
        return Path(self.path).read_bytes()


class RemoteMatrix:
    """A read-only stand-in for a memory-mapped ``.npy``, fetched in ranges.

    Supports the indexing the model and the fan-out worker actually use --
    ``m[i]``, ``m[i, a:b]`` and ``m[rows, a:b]`` -- and refuses anything else
    rather than quietly returning something plausible.

    Attributes:
        shape: ``(n_cells, n_days)``, read from the file's own header.
        dtype: The stored dtype, likewise.
    """

    def __init__(self, ranges: Ranges, *, row_cache: int = DEFAULT_ROW_CACHE):
        self._ranges = ranges
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._cache_limit = row_cache

        header = io.BytesIO(ranges.read(0, HEADER_PROBE_BYTES))
        version = np.lib.format.read_magic(header)
        if version == (1, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_1_0(header)
        elif version == (2, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(header)
        else:
            raise ValueError(f"unsupported .npy version {version}")
        if fortran_order:
            raise ValueError(
                "matrix is Fortran-ordered, so a cell's series is not contiguous; "
                "ranged reads would fetch the whole file"
            )
        if len(shape) != 2:
            raise ValueError(f"expected a 2-D matrix, got shape {shape}")

        self.shape = shape
        self.dtype = dtype
        self.ndim = 2
        self._data_offset = header.tell()
        self._row_bytes = shape[1] * dtype.itemsize

    # -- reading ------------------------------------------------------------

    def read_rows(self, start: int, stop: int) -> np.ndarray:
        """Rows ``start:stop`` in **one** request, because they are contiguous."""
        if not 0 <= start < stop <= self.shape[0]:
            raise IndexError(f"row block {start}:{stop} outside {self.shape[0]} rows")
        raw = self._ranges.read(
            self._data_offset + start * self._row_bytes, (stop - start) * self._row_bytes
        )
        expected = (stop - start) * self._row_bytes
        if len(raw) != expected:
            raise RangeNotHonoured(f"asked for {expected} bytes, got {len(raw)}")
        return np.frombuffer(raw, dtype=self.dtype).reshape(stop - start, self.shape[1])

    def prefetch(self, start: int, stop: int) -> None:
        """Warm the cache for a block of cells, so a worker makes one request."""
        block = self.read_rows(start, stop)
        for offset, row in enumerate(block):
            self._remember(start + offset, row)

    def row(self, index: int) -> np.ndarray:
        index = int(index)
        cached = self._cache.get(index)
        if cached is not None:
            self._cache.move_to_end(index)
            return cached
        row = self.read_rows(index, index + 1)[0]
        self._remember(index, row)
        return row

    def _remember(self, index: int, row: np.ndarray) -> None:
        self._cache[index] = row
        self._cache.move_to_end(index)
        while len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)

    # -- indexing -----------------------------------------------------------

    def __getitem__(self, key):
        if isinstance(key, (int, np.integer)):
            return self.row(key)
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError(
                "index a RemoteMatrix as m[i], m[i, a:b] or m[rows, a:b]; "
                f"got {key!r}"
            )
        rows, columns = key
        if isinstance(columns, slice) and columns.step not in (None, 1):
            raise TypeError("only contiguous column slices are supported")
        if isinstance(rows, (int, np.integer)):
            return self.row(rows)[columns]
        indices = np.asarray(rows).ravel()
        if indices.size and indices.max() - indices.min() + 1 == indices.size:
            # A contiguous run, which is how the fan-out worker asks: one request.
            block = self.read_rows(int(indices.min()), int(indices.max()) + 1)
            return block[indices - indices.min(), columns]
        return np.stack([self.row(i)[columns] for i in indices])

    def __len__(self) -> int:
        return self.shape[0]


def load_matrices_remote(base: str | Path, key: str, *, timeout: float = 30.0,
                         row_cache: int = DEFAULT_ROW_CACHE) -> WeatherGrid:
    """A :class:`~applebee.weather.WeatherGrid` backed by ranged reads.

    ``base`` is an ``s3://bucket/prefix``, a URL prefix, or a local directory. The dates and the cell table are small and are read whole; only
    the matrix is left remote.

    Args:
        base: URL prefix or directory holding ``{key}.values.npy`` and friends.
        key: Matrix name, e.g. ``northeast_tmean``.
        timeout: Seconds, HTTP only.
        row_cache: Cells to keep in memory; ~8.8 KB each for a six-year matrix.
    """
    base_str = str(base)

    def reader(suffix: str) -> Ranges:
        name = f"{key}.{suffix}"
        if base_str.startswith("s3://"):
            bucket, _, prefix = base_str[5:].partition("/")
            return S3Ranges(bucket, f"{prefix.rstrip('/')}/{name}" if prefix else name)
        if base_str.startswith(("http://", "https://")):
            return HttpRanges(f"{base_str.rstrip('/')}/{name}", timeout=timeout)
        return FileRanges(Path(base) / name)

    dates = np.load(io.BytesIO(reader("dates.npy").read_all()))
    cells = pd.read_parquet(io.BytesIO(reader("cells.parquet").read_all()))
    return WeatherGrid(
        values=RemoteMatrix(reader("values.npy"), row_cache=row_cache),
        dates=pd.DatetimeIndex(dates),
        cells=cells,
    )
