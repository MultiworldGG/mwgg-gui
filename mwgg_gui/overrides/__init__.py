from __future__ import annotations

from kivy.lang import Builder

from .colorpicker import (
    MWColorPicker,
)

from .expansionlist import (
    GameListPanel,
    GameListItem,
    GameListItemLongText,
    GameListItemShortText,
    GameTrailingPressedIconButton,
    SlotListItemHeader,
    SlotListItem,
    HintListDropdown,
    HintListItem,
    HintListItemLabel,
    IconBadge,
)

from .markuptextfield import (
    MarkupTextField,
    MarkupTextFieldCutCopyPaste,
)

# `InnerMDScreen` is intentionally NOT re-exported here. It depends on
# `mwgg_gui.components.mw_theme.AutoAdjustHeightBehavior`, and mw_theme
# imports from this package during its own init — re-exporting here
# would create a circular import. Import it from the submodule:
#     from mwgg_gui.overrides.innermdscreen import InnerMDScreen

from .fa_icons import (
    md_icons,
)

# Importing this module patches kivy.core.image.ImageLoader to recognize
# `ap:` and `ap:zip:` URL schemes that world client kvs (Universal Tracker
# et al.) feed AsyncImage. Side effect on import.
from .imageloader import (
    ApAsyncImage,
    register_url_scheme,
)
