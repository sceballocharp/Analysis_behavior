"""Shared GUI typography configured by gui_preferences.json."""
from tkinter import font as tkfont, ttk


DEFAULT_FONTS = {
    "controls": {"family": "Segoe UI", "size": 9, "weight": "normal"},
    "main_title": {"family": "Segoe UI", "size": 14, "weight": "bold"},
    "main_tabs": {"family": "Segoe UI", "size": 12, "weight": "bold"},
    "subtabs": {"family": "Segoe UI", "size": 10, "weight": "bold"},
    "dmts_file_tabs": {"family": "Segoe UI", "size": 10, "weight": "normal"},
    "output": {"family": "Consolas", "size": 10, "weight": "normal"},
    "lever_output": {"family": "Segoe UI", "size": 9, "weight": "normal"},
    "console_title": {"family": "Segoe UI", "size": 13, "weight": "bold"},
    "console_input": {"family": "Consolas", "size": 11, "weight": "normal"},
    "guide_title": {"family": "Segoe UI", "size": 18, "weight": "bold"},
    "guide_heading": {"family": "Segoe UI", "size": 12, "weight": "bold"},
    "guide_body": {"family": "Segoe UI", "size": 11, "weight": "normal"},
    "canvas_buttons": {"family": "DejaVu Sans", "size": 8, "weight": "bold"},
    "canvas_table": {"family": "DejaVu Sans", "size": 9, "weight": "normal"},
    "canvas_message": {"family": "DejaVu Sans", "size": 13, "weight": "normal"},
    "canvas_loading": {"family": "DejaVu Sans", "size": 16, "weight": "bold"},
    "canvas_hint": {"family": "DejaVu Sans", "size": 11, "weight": "normal"},
}


class GuiFonts:
    def __init__(self, preferences):
        configured = preferences.get("fonts", {})
        if not isinstance(configured, dict):
            configured = {}
        self.settings = {}
        for section, defaults in DEFAULT_FONTS.items():
            value = configured.get(section, {})
            if not isinstance(value, dict):
                value = {}
            merged = dict(defaults)
            family = value.get("family")
            if isinstance(family, str) and family.strip():
                merged["family"] = family.strip()
            size = value.get("size")
            if isinstance(size, int) and not isinstance(size, bool) and size > 0:
                merged["size"] = size
            if value.get("weight") in ("normal", "bold"):
                merged["weight"] = value["weight"]
            self.settings[section] = merged

    def tk(self, section):
        value = self.settings[section]
        return value["family"], value["size"], value["weight"]

    def mpl(self, section):
        value = self.settings[section]
        return dict(fontfamily=value["family"], fontsize=value["size"], fontweight=value["weight"])

    def apply(self, root):
        """Configure shared controls and the three notebook title levels."""
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name, root=root).configure(**self.settings["controls"])
        style = ttk.Style(root)
        style.configure("TNotebook.Tab", font=self.tk("subtabs"))
        style.configure("Main.TNotebook.Tab", font=self.tk("main_tabs"), padding=(16, 8))
        style.configure("DmtsFile.TNotebook.Tab", font=self.tk("dmts_file_tabs"))
        style.configure("Treeview", rowheight=max(20, tkfont.nametofont("TkDefaultFont", root=root).metrics("linespace") + 4))
