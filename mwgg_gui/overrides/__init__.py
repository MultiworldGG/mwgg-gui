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

# Screens intentionally NOT re-exported here: it imports from
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

from .hoverlabel import (
    HoverLabel,
    SimpleHoverLabel
)

# Import side effect: ports the upstream ripple FBO fix onto KivyMD 2.0.0.
from .ripple import (
    patch_ripple_fbo,
)

# Import side effect: guards MDTooltip.display_tooltip against text-less
# rich tooltips, which crash on KivyMD 2.0.0.
from .tooltip import (
    patch_rich_tooltip_display,
)
