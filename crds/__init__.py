from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

# ============================================================================

import os
import os.path
import sys
import importlib

# ============================================================================

__version__ = "7.1.0"  
__rationale__ = "JWST Build 7.1 Development, bestrefs --sync-references fix"

# ============================================================================

from crds.core import config   # module

from crds.core.heavy_client import getreferences, getrecommendations
from crds.core.heavy_client import get_symbolic_mapping, get_pickled_mapping
from crds.core.rmap import get_cached_mapping, asmapping
from crds.core.config import locate_mapping, locate_file

from crds.core import exceptions
from crds.core.exceptions import *
from crds.core.constants import ALL_OBSERVATORIES, INSTRUMENT_KEYWORDS

from crds.client import api
from crds.client import get_default_context

# ============================================================================

'''This code section supports moving modules from the root crds namespace into 
sub-packages while still supporting the original CRDS package external interface.
This allows the code to be partitioned without changing external imports.  This
is made more difficult by the inapplicability of namespace packages because this
__init__ is not empty.

The strategy employed here is to implement core packages normally in crds.core,
then alias them into the top level crds namespace using importlib.import_module()
and sys.modules to make it appear as if each core package has already been imported
and belongs to the top level namespace.
'''
def alias_subpackage_module(subpkg, modules):
    """Alias each module from `modules` of `subpkg` to appear in this
    namespace.
    """
    for module in modules:
        globals()[module] = importlib.import_module(subpkg + "." + module)
        sys.modules["crds." + module] = sys.modules[subpkg + "." + module]

CORE_MODULES = [
    "pysh",
    "python23",
    "exceptions",
    "log",
    "config",
    "constants",
    "utils",
    "timestamp",
    "custom_dict",
    "selectors",
    "mapping_verifier",
    "reftypes",
    "substitutions",
    "rmap",
    "heavy_client",
    "cmdline",
    "naming",
    "git_version",
]

# e.g. make crds.rmap importable same as crds.core.rmap reorganized code
alias_subpackage_module("crds.core", CORE_MODULES)

# ============================================================================

# e.g. python -m crds.newcontext now called as python -m crds.refactoring.newcontext

REFACTORING_MODULES = [
    "checksum",
    "newcontext",
    "refactor",
    "refactor2",
]

# e.g. make crds.rmap importable same as crds.core.rmap reorganized code
alias_subpackage_module("crds.refactoring", REFACTORING_MODULES)

# ============================================================================

# e.g. python -m crds.uniqname now called as -m crds.refactoring.uniqname

MISC_MODULES = [
    "datalvl",               # external interface with pipelines
    "query_affected",        # external interface with pipelines
    "uniqname",              # external interface with submitters

    "check_archive",         # misc utility
    "sql",                   # prototype convenience wrapper
]

# e.g. make crds.rmap importable same as crds.core.rmap reorganized code
alias_subpackage_module("crds.misc", MISC_MODULES)

# ============================================================================

URL = os.environ.get("CRDS_SERVER_URL", "https://crds-serverless-mode.stsci.edu")
api.set_crds_server(URL)

