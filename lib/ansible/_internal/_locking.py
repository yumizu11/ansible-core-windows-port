from __future__ import annotations

import contextlib
import os
import typing as t


if os.name == 'nt':
    import msvcrt

    def _lock_file(file: t.IO) -> None:
        # msvcrt.locking locks a byte range starting at the current file position.
        # Lock a single byte at offset 0 as a whole-file advisory lock; all callers
        # of named_mutex lock the same region, so this is mutually consistent.
        # LK_LOCK gives up after ~10s, so retry to provide blocking semantics.
        file.seek(0)
        while True:
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue

    def _unlock_file(file: t.IO) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(file: t.IO) -> None:
        fcntl.flock(file, fcntl.LOCK_EX)

    def _unlock_file(file: t.IO) -> None:
        fcntl.flock(file, fcntl.LOCK_UN)


@contextlib.contextmanager
def named_mutex(path: str) -> t.Iterator[None]:
    """
    Lightweight context manager wrapper over a file-based advisory lock to provide IPC locking via a shared filename.
    Entering the context manager blocks until the lock is acquired.
    The lock file will be created automatically, but creation of the parent directory and deletion of the lockfile are the caller's responsibility.
    """
    with open(path, 'a') as file:
        _lock_file(file)

        try:
            yield
        finally:
            _unlock_file(file)
