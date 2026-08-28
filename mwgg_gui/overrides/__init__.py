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

# `InnerMDScreen` is intentionally NOT re-exported here: it imports from
# mw_theme, which imports this package during its own init -- re-exporting
# would create a circular import. Import it from the submodule instead.

from .fa_icons import (
    md_icons,
)

# Import side effect: patches kivy.core.image.ImageLoader to recognize the
# `ap:` / `ap:zip:` URL schemes world client kvs feed AsyncImage.
from .imageloader import (
    ApAsyncImage,
    register_url_scheme,
)
