# Copyright (c) 2019 Matt Martz <matt@sivel.net>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import annotations

import multiprocessing

# Explicit multiprocessing context using the fork start method
# This exists as a compat layer now that Python3.8 has changed the default
# start method for macOS to ``spawn`` which is incompatible with our
# code base currently
#
# This exists in utils to allow it to be easily imported into various places
# without causing circular import or dependency problems
#
# 'fork' is unavailable on platforms such as Windows (only 'spawn' exists). Fall back to
# the platform default so the package remains importable there. NOTE: the worker pool
# still relies on fork semantics; cross-platform worker execution is handled separately
# (see ansible.executor.process.worker).
try:
    context = multiprocessing.get_context('fork')
except ValueError:
    context = multiprocessing.get_context()
