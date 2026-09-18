"""Main application window for continuous screen capture and collage."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from app.clipboard_win import copy_image_to_clipboard
from app.collage import build_collage
from app.long_snip import long_snip
from app.snip_overlay import snip

THUMB_MAX = 180


class MainWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("螢幕連續擷取")
        self.root.minsize(420, 360)
        self.root.geometry("640x520")

        self._captures: list[Image.Image] = []
        self._thumb_photos: list[ImageTk.PhotoImage] = []
        self._columns = tk.IntVar(value=2)
        self._status = tk.StringVar(value="按 + 框選截圖，按 ~ 捲動長截圖")

        self._build_toolbar()
        self._build_gallery()
        self._build_status()

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        add_btn = ttk.Button(bar, text="+", width=4, command=self._on_add)
        add_btn.pack(side=tk.LEFT)

        long_btn = ttk.Button(bar, text="~", width=4, command=self._on_long_add)
        long_btn.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(bar, text="每列").pack(side=tk.LEFT, padx=(12, 4))
        spin = ttk.Spinbox(
            bar,
            from_=1,
            to=6,
            width=4,
            textvariable=self._columns,
            command=self._refresh_gallery,
        )
        spin.pack(side=tk.LEFT)
        spin.bind("<Return>", lambda _e: self._refresh_gallery())
        spin.bind("<FocusOut>", lambda _e: self._refresh_gallery())

        copy_btn = ttk.Button(bar, text="COPY", command=self._on_copy)
        copy_btn.pack(side=tk.LEFT, padx=(12, 0))

    def _build_gallery(self) -> None:
        wrap = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(wrap, highlightthickness=0, bg="#F5F5F5")
        scrollbar = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._gallery = ttk.Frame(self._canvas)
        self._gallery_window = self._canvas.create_window(
            (0, 0), window=self._gallery, anchor=tk.NW
        )

        self._gallery.bind("<Configure>", self._on_gallery_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _build_status(self) -> None:
        status = ttk.Label(
            self.root, textvariable=self._status, padding=(10, 6), anchor=tk.W
        )
        status.pack(side=tk.BOTTOM, fill=tk.X)

    def _on_gallery_configure(self, _event: tk.Event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._gallery_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def _get_columns(self) -> int:
        try:
            value = int(self._columns.get())
        except (tk.TclError, ValueError, TypeError):
            value = 2
        return max(1, min(6, value))

    def _on_add(self) -> None:
        self._begin(snip, "已取消框選")

    def _on_long_add(self) -> None:
        self._begin(long_snip, "已取消長截圖")

    def _begin(
        self, grab: Callable[[tk.Misc], Image.Image | None], cancelled: str
    ) -> None:
        self.root.withdraw()
        self.root.update_idletasks()
        # Brief delay so the main window is fully hidden before capture.
        self.root.after(120, lambda: self._capture(grab, cancelled))

    def _capture(
        self, grab: Callable[[tk.Misc], Image.Image | None], cancelled: str
    ) -> None:
        try:
            image = grab(self.root)
        finally:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        if image is None:
            self._status.set(cancelled)
            return

        self._captures.append(image)
        self._refresh_gallery()
        self._status.set(f"已擷取 {len(self._captures)} 張")

    def _on_copy(self) -> None:
        if not self._captures:
            self._status.set("尚無截圖可複製")
            messagebox.showinfo("COPY", "請先擷取至少一張截圖。")
            return

        columns = self._get_columns()
        try:
            collage = build_collage(self._captures, columns)
            copy_image_to_clipboard(collage)
        except Exception as exc:  # noqa: BLE001 - surface to user
            messagebox.showerror("COPY 失敗", str(exc))
            self._status.set("複製失敗")
            return

        self._status.set(f"已將 {len(self._captures)} 張拼成一圖並複製到剪貼簿")

    def _delete_capture(self, index: int) -> None:
        if 0 <= index < len(self._captures):
            del self._captures[index]
            self._refresh_gallery()
            count = len(self._captures)
            self._status.set(f"已刪除，剩餘 {count} 張" if count else "尚無截圖")

    def _make_thumbnail(self, image: Image.Image) -> ImageTk.PhotoImage:
        thumb = image.copy()
        thumb.thumbnail((THUMB_MAX, THUMB_MAX), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(thumb)

    def _refresh_gallery(self) -> None:
        for child in self._gallery.winfo_children():
            child.destroy()
        self._thumb_photos.clear()

        columns = self._get_columns()
        for index, image in enumerate(self._captures):
            row, col = divmod(index, columns)
            cell = ttk.Frame(self._gallery, padding=6)
            cell.grid(row=row, column=col, sticky=tk.NW)

            photo = self._make_thumbnail(image)
            self._thumb_photos.append(photo)

            holder = tk.Frame(cell, bg="#E8E8E8", bd=1, relief=tk.SOLID)
            holder.pack()

            label = tk.Label(holder, image=photo, bg="#E8E8E8")
            label.pack()

            delete_btn = tk.Button(
                holder,
                text="×",
                font=("Segoe UI", 9, "bold"),
                fg="#B00020",
                bg="#FFFFFF",
                activeforeground="#FFFFFF",
                activebackground="#B00020",
                bd=0,
                padx=4,
                pady=0,
                cursor="hand2",
                command=lambda i=index: self._delete_capture(i),
            )
            delete_btn.place(relx=1.0, rely=0.0, anchor=tk.NE, x=-2, y=2)

        for col in range(columns):
            self._gallery.columnconfigure(col, weight=1)

        self._canvas.configure(scrollregion=self._canvas.bbox("all"))


def run_app() -> None:
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    MainWindow(root)
    root.mainloop()
