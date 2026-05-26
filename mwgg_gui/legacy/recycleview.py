"""Legacy RecycleView selectable row widgets used by world client kvs.

The Universal Tracker's ``Tracker.kv`` (and the Manual world's
``Manual.kv``) refer to these by bare class name through the kivy Factory:

* ``viewclass: 'SelectableLabel'`` for the row widget
* ``SelectableRecycleBoxLayout:`` as the recycle view's layout manager

They originally lived in the legacy ``kvui.py`` next to the GameManager.
Importing this module is enough to register them with the Factory.
"""
from __future__ import annotations

from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.properties import BooleanProperty
from kivy.core.text.markup import MarkupLabel
from kivy.core.clipboard import Clipboard
from kivy.app import App
from kivy.lang import Builder

# TooltipLabel in the new gui surfaces as HintListItemLabel.
from mwgg_gui.overrides.expansionlist import HintListItemLabel as TooltipLabel


# Style rule so SelectableLabel rows render kivy markup ([color=...], [u], ...)
# from the moment they're instantiated, before any text is assigned by data —
# without this, the initial paint happens with markup=False and the [color=...]
# tags render as literal text.
Builder.load_string('''
<SelectableLabel>:
    markup: True
''')


class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior, RecycleBoxLayout):
    """Selectable + focusable box layout backing legacy world recycle views."""


class SelectableLabel(RecycleDataViewBehavior, TooltipLabel):
    """Row widget for legacy world recycle views.

    Behavior mirrors the original ``kvui.SelectableLabel``:

    * Renders kivy markup (``[color=...]``, ``[u]``...) so colored tracker
      output displays correctly.
    * On touch: copies the visible text (markup stripped) to the clipboard.
    * On touch: best-effort autofills the launcher's bottom-bar command input
      via ``Utils.get_input_text_from_response`` if both
      ``app.console_text_input`` (new MultiMDApp) or ``app.textinput``
      (legacy GameManager) are present, plus
      ``app.last_autofillable_command``.
    """
    index = None
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # World kv rules ship tracker rows with [color=...] markup; if markup
        # parsing is off, the raw tags render as literal text.
        self.markup = True
        # ListItemTooltip's kv creates an MDTooltipPlain child that's hooked up
        # as self._tooltip by MDTooltip.add_widget. The popup also needs
        # markup parsing or every tooltip renders literal [color=...] tags.
        tooltip = getattr(self, "_tooltip", None)
        if tooltip is not None and hasattr(tooltip, "markup"):
            tooltip.markup = True

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def on_size(self, instance_label, size):
        super().on_size(instance_label, size)
        if self.parent:
            self.width = self.parent.width

    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos):
            if self.selected:
                self.parent.clear_selection()
                return True
            # Strip kivy markup tags for the clipboard copy.
            temp = MarkupLabel(text=self.text).markup
            text = "".join(part for part in temp if not part.startswith("["))
            Clipboard.copy(
                text.replace("&amp;", "&").replace("&bl;", "[").replace("&br;", "]")
            )
            # Best-effort autofill into whichever text input the running app
            # exposes. New MultiMDApp uses `console_text_input`; the legacy
            # GameManager used `textinput`. Skip silently if neither is set.
            app = App.get_running_app()
            cmdinput = getattr(app, "console_text_input", None) or getattr(app, "textinput", None)
            last_cmd = getattr(app, "last_autofillable_command", None)
            if cmdinput is not None and not getattr(cmdinput, "text", ""):
                try:
                    from Utils import get_input_text_from_response
                    input_text = get_input_text_from_response(text, last_cmd)
                    if input_text is not None:
                        cmdinput.text = input_text
                except Exception:
                    pass
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        self.selected = is_selected
