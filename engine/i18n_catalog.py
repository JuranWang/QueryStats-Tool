"""English translations, keyed by the Chinese source string passed to ``t()``.

Split into fragments per area so parallel edits don't collide; ``EN`` is the merged view.
"""

from __future__ import annotations

from .i18n_catalog_app import EN_APP
from .i18n_catalog_misc import EN_MISC

EN: dict[str, str] = {**EN_APP, **EN_MISC}
