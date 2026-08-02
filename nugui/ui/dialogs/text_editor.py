import tkinter as tk
from tkinter import ttk, messagebox
from nugui.ui.dialogs.base import BaseDialog
from nugui.models.elements import TextAnnotation

# Common fonts offered in the picker (Tk falls back gracefully if a family
# is not installed on the host).
FONT_FAMILIES = ["Arial", "Times New Roman", "Courier New",
                 "Verdana", "Calibri", "Helvetica", "Georgia", "Tahoma"]


class TextAnnotationEditor(BaseDialog):
    """FEATURE: create/edit a free-floating text annotation, mirroring the
    abDraw "Add Text" dialog (font, size, bold, italic, alignment).

    Annotation text is cosmetic, so it is NOT validated as an HDL
    identifier - any characters are allowed.
    """

    def __init__(self, parent, annotation: TextAnnotation):
        self.annotation = annotation
        self.font_var = tk.StringVar(value=annotation.font_family)
        self.size_var = tk.IntVar(value=annotation.font_size)
        self.bold_var = tk.BooleanVar(value=annotation.bold)
        self.italic_var = tk.BooleanVar(value=annotation.italic)
        self.align_var = tk.StringVar(value=annotation.align)
        self._initial_text = annotation.text
        super().__init__(parent, title="Add Text")

    def create_widgets(self):
        # Text (Enter = new line, Ctrl+Enter = OK)
        ttk.Label(self.body_frame,
                  text="Text  (Enter = new line, Ctrl+Enter = OK):").grid(
            row=0, column=0, columnspan=4, sticky="w")
        self.txt = tk.Text(self.body_frame, height=5, width=42, wrap="word")
        self.txt.insert("1.0", self._initial_text)
        self.txt.grid(row=1, column=0, columnspan=4, pady=5, sticky="we")
        self.txt.focus_set()
        # Ctrl+Enter confirms; plain Enter stays a newline (Text default)
        self.txt.bind("<Control-Return>", lambda e: (self.on_ok(), "break")[1])

        # Font family
        ttk.Label(self.body_frame, text="Font:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(self.body_frame, textvariable=self.font_var,
                     values=FONT_FAMILIES, state="readonly", width=18).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(6, 0))

        # Size
        ttk.Label(self.body_frame, text="Size:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Spinbox(self.body_frame, from_=6, to=96, textvariable=self.size_var,
                    width=6).grid(row=3, column=1, sticky="w", pady=(6, 0))

        # Bold / Italic
        style_frame = ttk.Frame(self.body_frame)
        style_frame.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Checkbutton(style_frame, text="Bold", variable=self.bold_var).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(style_frame, text="Italic", variable=self.italic_var).pack(side=tk.LEFT)

        # Alignment
        align_frame = ttk.Frame(self.body_frame)
        align_frame.grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(align_frame, text="Align:").pack(side=tk.LEFT, padx=(0, 8))
        for label, value in (("Left", "left"), ("Center", "center"), ("Right", "right")):
            ttk.Radiobutton(align_frame, text=label, value=value,
                            variable=self.align_var).pack(side=tk.LEFT, padx=(0, 10))

    def validate(self):
        if not self.txt.get("1.0", tk.END).strip():
            messagebox.showerror("Error", "Text cannot be empty.", parent=self)
            return False
        return True

    def apply(self):
        self.annotation.text = self.txt.get("1.0", tk.END).rstrip("\n")
        self.annotation.font_family = self.font_var.get() or "Arial"
        try:
            self.annotation.font_size = max(6, int(self.size_var.get()))
        except tk.TclError:
            self.annotation.font_size = 12
        self.annotation.bold = self.bold_var.get()
        self.annotation.italic = self.italic_var.get()
        self.annotation.align = self.align_var.get() or "left"
