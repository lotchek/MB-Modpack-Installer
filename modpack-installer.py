#!/usr/bin/env python3
# ============================================================
# MemoryBound Modpack Installer
# Version: 0.1.3
# Author: Lotchek
# E-Mail: xsoraaaaas@gmail.com
# Date: 2025-10
# ------------------------------------------------------------
# Simple modpack installer for Minecraft using Flet for the UI.
# It will download and install all mods needed to join the server 
# and optionally some extra mods for enhanced gameplay.
# ------------------------------------------------------------
# Dependencies:
#   - flet
#   - flet-desktop
#   - requests
#   - pillow
#   - json
#   - hashlib
#
# Usage:
#   python flet run modpack-installer.py
# ============================================================

import os
import time
import sys
import json
import base64
import re
import shutil
import subprocess
from xml.parsers.expat import errors
import requests
import traceback
import flet as ft
from io import BytesIO
from PIL import Image
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
import hashlib
import json
import requests

DEFAULT_TARGET = os.path.abspath(".minecraft")
REPO_URL = "https://raw.githubusercontent.com/lotchek/MB-Modpack-Installer/main/"

# ---------- Resource Fetcher ----------
def fetch_resources(relative_path: str) -> dict:
    url = f"{REPO_URL}{relative_path}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching resource '{relative_path}': {e}")
        raise

# ---------- Theming ----------
def create_theme() -> ft.Theme:

    mat_theme = fetch_resources("data/material-theme.json")
    scheme = mat_theme["schemes"]["dark"]

    theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=scheme["primary"],
            on_primary=scheme["onPrimary"],
            primary_container=scheme.get("primaryContainer"),
            on_primary_container=scheme.get("onPrimaryContainer"),
            secondary=scheme["secondary"],
            on_secondary=scheme["onSecondary"],
            secondary_container=scheme.get("secondaryContainer"),
            on_secondary_container=scheme.get("onSecondaryContainer"),
            tertiary=scheme.get("tertiary"),
            on_tertiary=scheme.get("onTertiary"),
            tertiary_container=scheme.get("tertiaryContainer"),
            on_tertiary_container=scheme.get("onTertiaryContainer"),
            error=scheme["error"],
            on_error=scheme["onError"],
            error_container=scheme.get("errorContainer"),
            on_error_container=scheme.get("onErrorContainer"),
            background=scheme["background"],
            on_background=scheme["onBackground"],
            surface=scheme["surface"],
            on_surface=scheme["onSurface"],
            surface_variant=scheme.get("surfaceVariant"),
            on_surface_variant=scheme.get("onSurfaceVariant"),
            outline=scheme.get("outline"),
            shadow=scheme.get("shadow"),
            inverse_surface=scheme.get("inverseSurface"),
            inverse_primary=scheme.get("inversePrimary"),
        ),

        visual_density=ft.VisualDensity.COMFORTABLE,

        # --- Notification Banner ---
        snackbar_theme=ft.SnackBarTheme(
            behavior=ft.SnackBarBehavior.FLOATING,
            action_text_color=scheme["primary"],
            shape=ft.RoundedRectangleBorder(radius=8),
            show_close_icon=True,
        ),

        # --- Scrollbar Theme ---
        scrollbar_theme=ft.ScrollbarTheme(
            thumb_visibility=False,
            track_visibility=False,
            thumb_color=ft.Colors.TRANSPARENT,
            track_border_color=ft.Colors.TRANSPARENT
        ),

        # --- Buttons ---
        elevated_button_theme = ft.ElevatedButtonTheme(
            enable_feedback=True,
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD) 
        ),

        # --- Page Transitions ---
        page_transitions = ft.PageTransitionsTheme(
            linux=ft.PageTransitionTheme.NONE,
            windows=ft.PageTransitionTheme.NONE
        ),
    )
    return theme

def set_theme(page: ft.Page, theme: ft.Theme):
    page.theme = theme
    page.update()

# ---------- File Handlers ----------
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def unique_path(dirpath: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    counter = 1
    out_path = os.path.join(dirpath, filename)
    while os.path.exists(out_path):
        out_path = os.path.join(dirpath, f"{base}_{counter}{ext}")
        counter += 1
    return out_path


def get_filename(cd: str | None) -> str | None:
    if not cd:
        return None
    
    fname = re.findall('filename=(.+)', cd)
    if len(fname) == 0:
        fname = re.findall(r"filename\*=UTF-8''(.+)", cd)
        if len(fname) == 0:
            return None
        return unquote(fname[0])
        
    return fname[0].strip('"')

 # ----- Checksum verification -----
def verify_checksum(file_path: str, expected_checksum: str) -> bool:
    if not expected_checksum:
        return True  
        
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
        
    return sha256_hash.hexdigest().lower() == expected_checksum.lower()
    
# ---------- Size & Progress fetchers ----------
def format_size(n: float) -> str:
    if n is None:
        return "0 B"
    n = float(n)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while n >= 1024.0 and i < len(units) - 1:
        n /= 1024.0
        i += 1
    return f"{n:.2f} {units[i]}"

def format_progress_line(name: str, downloaded: int, total: int, start_time: float) -> str:
    elapsed = time.time() - start_time
    speed = downloaded / elapsed if elapsed > 0 else 0
    total_known = total > 0
    percent = (downloaded / total * 100) if total_known else 0
    remaining = (total - downloaded) / speed if speed > 0 and total_known else 0

    size_str = (
        f"{format_size(downloaded)}/{format_size(total)}"
        if total_known else f"{format_size(downloaded)}/?"
    )
    remain_str = f"{remaining:.1f}s left" if total_known and speed > 0 else "--.-s left"
    return f"{percent:5.1f}%  -  {size_str}  -  {format_size(speed)}/s  -  {remain_str}"

# ---------- Download Handler----------
def generic_download(url: str, target_dir: str, progress_callback=None, line_id=None, checksum: str | None = None) -> str:
    ensure_dir(target_dir)
    r = requests.get(url, stream=True, timeout=(5, 60))
    r.raise_for_status()
    fname = get_filename(r.headers.get("Content-Disposition"))
    if not fname:
        fname = os.path.basename(url.split("?")[0]) or "deleteme.bin"
    out_path = unique_path(target_dir, fname)
    total_size = int(r.headers.get("Content-Length", 0)) if r.headers.get("Content-Length") else 0
    downloaded = 0
    start_time = time.time()
    last_emit = 0.0
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(8192):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if progress_callback and (now - last_emit) >= 0.2:
                progress_callback(format_progress_line(fname, downloaded, total_size, start_time), line_id)
                last_emit = now
    elapsed = time.time() - start_time
    final_size = total_size if total_size > 0 else os.path.getsize(out_path)
    if progress_callback:
        progress_callback(f"100.00%  -  {format_size(final_size)}  -  {elapsed:.1f}s total", line_id)
    
    # Verify checksum
    if progress_callback:
        progress_callback(f"Verifying {fname}...", line_id)
    
    if not verify_checksum(out_path, checksum):
        os.remove(out_path)
        raise ValueError(f"Checksum mismatch for {fname}")

    if progress_callback:
        progress_callback("Download complete", line_id)
        
    return out_path

def gdrive_download(url: str, target_dir: str, progress_callback=None, line_id=None, checksum: str | None = None) -> str:
    ensure_dir(target_dir)
    session = requests.Session()
    r = session.get(url, stream=True, timeout=(5, 60))
    r.raise_for_status()
    if "text/html" in r.headers.get("Content-Type", "").lower():
        html = r.text
        m = re.search(r"confirm=([0-9A-Za-z_]+)", html)
        if not m:
            raise RuntimeError("Google Drive confirmation token not found")
        token = m.group(1)
        url = f"{url}&confirm={token}" if "&" in url else f"{url}?confirm={token}"
        r = session.get(url, stream=True, timeout=(5, 60))
        r.raise_for_status()
    fname = get_filename(r.headers.get("Content-Disposition")) or "deleteme.bin"
    out_path = unique_path(target_dir, fname)
    total_size = int(r.headers.get("Content-Length", 0)) if r.headers.get("Content-Length") else 0
    downloaded = 0
    start_time = time.time()
    last_emit = 0.0
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if progress_callback and (now - last_emit) >= 0.2:
                progress_callback(format_progress_line(fname, downloaded, total_size, start_time), line_id)
                last_emit = now
    elapsed = time.time() - start_time
    final_size = total_size if total_size > 0 else os.path.getsize(out_path)
    if progress_callback:
        progress_callback(f"100.00%  -  {format_size(final_size)}  -  {elapsed:.1f}s total", line_id)
    
    # Verify checksum
    if progress_callback:
        progress_callback(f"Verifying {fname}...", line_id)
        
    if not verify_checksum(out_path, checksum):
        os.remove(out_path)
        raise ValueError(f"Checksum mismatch for {fname}")

    if progress_callback:
        progress_callback("Download complete", line_id)
        
    return out_path

def download_method(url: str, target_dir: str, progress_callback=None, line_id=None, checksum: str | None = None) -> str:
    if "drive.google.com" in url:
        return gdrive_download(url, target_dir, progress_callback, line_id, checksum)
    else:
        return generic_download(url, target_dir, progress_callback, line_id, checksum)

# ---------- Package parser ----------
def load_manifest() -> dict:
    return fetch_resources("data/packages.json")

# ---------- UI ----------
class InstallerApp:
    def __init__(self, page: ft.Page, manifest: dict, theme: ft.Theme):
        self.page = page
        self.manifest = manifest
        self.checkboxes: list[tuple[ft.Checkbox, dict]] = []
        self.target_path = DEFAULT_TARGET
        self.select_all_state = False

        # ----- Status manager -----
        self._status_lock = threading.Lock()
        self.status_data: dict[str, str] = {}
        self.status_controls: dict[str, ft.Text] = {}
        self.total_downloads: int = 0
        self.completed_downloads: int = 0
        self._stop_flag = threading.Event()
        self._executor = None

        # ----- Page settings -----
        page.title = "MemoryBound Modpack Installer"
        page.window.width = 900
        page.window.height = 600
        page.window.resizable = True
        page.window.min_width = 720
        page.window.min_height = 500
        page.scroll = None
        page.window.on_event = self.on_window_event

        # ----- Path picker -----
        self.dir_picker = ft.FilePicker(on_result=self.on_dir_picked)
        page.overlay.append(self.dir_picker)

        # ----- Path field -----
        self.path_field = ft.TextField(
            height=40, value=DEFAULT_TARGET, text_size=12, expand=True,
        )
        self.path_label = ft.Text("Select your .minecraft directory (or custom)", size=12, weight=ft.FontWeight.BOLD)
        path_row = ft.Column([
            self.path_label,
            ft.Row([
                self.path_field,
                ft.Container(ft.ElevatedButton("Set Folder", on_click=self.pick_dir, height=40),
                             alignment=ft.alignment.center),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=2, alignment=ft.MainAxisAlignment.START)

        # ----- Console -----
        self.console_list = ft.ListView(expand=True, spacing=4)
        console_tab = ft.Tab(text="Console", content=ft.Container(content=self.console_list, expand=True))

        # ----- Tabs -----
        self.tabs = ft.Tabs(selected_index=0, expand=True, tabs=[
            ft.Tab(text="Look and Feel", content=self.build_category_tab("Look and Feel")),
            ft.Tab(text="Shaders", content=self.build_category_tab("Shaders")),
            ft.Tab(text="Requirements", content=self.build_requirements_tab()),
            console_tab,
        ])

        # ----- ProgressBar + Buttons -----
        self.progress = ft.ProgressBar(height=10, width=200, value=0,
                                       expand=True)
        self.select_all_btn = ft.ElevatedButton("Select all", on_click=self.toggle_select_all)
        self.install_btn = ft.ElevatedButton("Install", on_click=self.install)
        btn_row = ft.Row([self.select_all_btn, self.progress, self.install_btn],
                         alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # ----- Main layout -----
        page.add(ft.Column([path_row, self.tabs, btn_row], expand=True, spacing=15))

        # ----- Updater thread -----
        self.page.run_thread(self._ui_updater)
    
    # ----- Window event handler -----
    def on_window_event(self, e):
        if e.data == "close":
            self.cleanup_and_exit()
    
    # ----- Window kill event -----
    def cleanup_and_exit(self):
        self._stop_flag.set()
        if self._executor:
            try:
                self._executor.shutdown(wait=False)
                self.page.open(ft.SnackBar(
                    ft.Text("Stopping Operation...", color=ft.Colors.RED),
                    open=True
                ))
            except Exception as e:
                print(f"Error shutting down executor: {e}")
        
        try:
            if self.page and self.page.window.visible:
                self.page.window.destroy() 
        except Exception as e:
            print(f"Error during shutdown: {e}")
        
        print("Forcing application exit")
        os._exit(0)

    # ----- UI updater -----
    def _ui_updater(self):
        last_applied: dict[str, str] = {}
        while not self._stop_flag.is_set():
            with self._status_lock:
                items = list(self.status_data.items())
                total = self.total_downloads
                done = self.completed_downloads

            # Sort by index prefix
            def sort_key(item):
                lid, _ = item
                try:
                    idx = int(lid.split(":", 1)[0])
                except Exception:
                    idx = 0
                return idx

            items.sort(key=sort_key)

            for lid, msg in items:
                txt = self.status_controls.get(lid)
                if txt and last_applied.get(lid) != msg:
                    txt.value = msg
                    txt.update()
                    last_applied[lid] = msg

            prog = (done / total) if total > 0 else 0.0
            if self.progress.value != prog:
                self.progress.value = prog
                self.progress.update()

            self.page.update()
            
            if self._stop_flag.wait(timeout=0.2):
                break

    # ----- Path selection -----
    def pick_dir(self, e):
        self.dir_picker.get_directory_path(dialog_title="Select your .minecraft directory (or custom)")

    def on_dir_picked(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.path_field.value = e.path
            self.page.update()

    # ----- Requirements Tab -----
    def build_requirements_tab(self):
        
        req_items = [it for it in self.manifest["items"] if it.get("tag") == "base"]
        categories = {}
        for it in req_items:
            cat = it.get("category", "Other")
            categories.setdefault(cat, []).append(it)

        columns = []
        for cat, items in categories.items():
            col = ft.Column(
                [
                    ft.Text(cat, weight=ft.FontWeight.BOLD, size=16),
                    *[
                        ft.TextButton(
                            text=it["name"],
                            url=it.get("homepage") or it.get("url") or "",
                            style=ft.ButtonStyle(
                                shape=ft.RoundedRectangleBorder(radius=0),
                                padding=0,
                                text_style=ft.TextStyle(size=14, weight=ft.FontWeight.NORMAL)
                            )
                        )
                        for it in items
                    ]
                ],
                spacing=8
            )
            columns.append(col)

        description = ft.Text(
            "These mods are required to join the server.",
            size=12,
            text_align=ft.TextAlign.LEFT,
            selectable=False,
            max_lines=4,
            overflow=ft.TextOverflow.CLIP,
            style=ft.TextStyle(height=1.5),
            
        )

        def build_wrapped_rows(columns, max_per_row=2):
            rows = []
            for i in range(0, len(columns), max_per_row):
                rows.append(
                    ft.Row(
                    columns[i:i+max_per_row],
                    spacing=40,
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
            return rows

        return ft.Container(
            content=ft.Column(
            [
                description,
                *build_wrapped_rows(columns, max_per_row=4)
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.START,
            ),
            expand=True,
            padding=10,
            margin=ft.margin.only(top=10),
        )

    # ----- Mods Tab-----
    def build_category_tab(self, category: str, include_optional: bool = True):
        base_items = [it for it in self.manifest["items"] if it.get("tag") == "base" and it.get("category") == category]
        opt_items = [it for it in self.manifest["items"] if it.get("tag") == "optional" and it.get("category") == category]
        controls: list[ft.Control] = []
        if base_items:
            controls.append(ft.Text("Required Mods:", weight=ft.FontWeight.BOLD, size=20))
            for it in base_items:
                controls.append(self.render_item(it, with_checkbox=False))
        if include_optional and opt_items:
            controls.append(ft.Text("Optional Mods:", weight=ft.FontWeight.BOLD, size=20))
            for it in opt_items:
                chk = ft.Checkbox(label=it["name"])
                self.checkboxes.append((chk, it))
                controls.append(self.render_item(it, checkbox=chk))
        return ft.Container(content=ft.ListView(controls=controls, spacing=12), expand=True, margin=10)

    def render_item(self, it: dict, with_checkbox: bool = True, checkbox: ft.Checkbox | None = None):
        desc = (it.get("desc") or "").strip()
        imgs = it.get("images") or []
        name_link = ft.TextButton(
            text=it["name"], url=it.get("homepage") or it.get("url") or "",
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=0), padding=0,
                                 text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD)))
        row_controls = [name_link]
        if checkbox:
            checkbox.label = ""
            row_controls.append(ft.Container(content=checkbox, alignment=ft.alignment.center_right, expand=False))
        title = ft.Row(row_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER)
        img_controls: list[ft.Control] = []
        img_placeholders = []
        for _ in imgs:
            placeholder = ft.Image(src="", width=220)
            img_controls.append(placeholder)
            img_placeholders.append(placeholder)

        # change function to convert every image to png except gifs
        # images aren't loading conistently, need to debug more
        def load_images_async():
            for idx, u in enumerate(imgs):
                try:
                    r = requests.get(u, timeout=10)
                    r.raise_for_status()
                    content_type = r.headers.get("Content-Type", "").lower()
                    if u.lower().endswith(".gif") or "gif" in content_type:
                        img_placeholders[idx].src = u
                    else:
                        pil_img = Image.open(BytesIO(r.content))
                        pil_img.thumbnail((300, 280))
                        buf = BytesIO()
                        pil_img.save(buf, format="PNG")
                        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        img_placeholders[idx].src_base64 = b64
                    img_placeholders[idx].update()
                except Exception as e:
                    img_placeholders[idx].src = ""
                    img_placeholders[idx].src_base64 = None
                # --- DEBUG ---
                #   img_placeholders[idx].content = ft.Text(f"[Image failed: {u} ({e})]",
                #                                           color=ft.Colors.RED, size=12)
                    img_placeholders[idx].update()
        self.page.run_thread(load_images_async)
        return ft.Container(content=ft.Column([title,
                                               ft.Text(desc, selectable=True, size=14),
                                               ft.Row(img_controls, scroll=ft.ScrollMode.AUTO)], spacing=8),
                            border=ft.border.all(1), padding=14, border_radius=20)

    # ----- Select all toggle -----
    def toggle_select_all(self, e):
        self.select_all_state = not self.select_all_state
        for chk, _ in self.checkboxes:
            chk.value = self.select_all_state
        self.select_all_btn.text = "Remove selection" if self.select_all_state else "Select all"
        self.page.update()

    # ----- Install -----
    def install(self, e):
        self.target_path = self.path_field.value.strip() if self.path_field.value else DEFAULT_TARGET
        all_items = [it for it in self.manifest["items"] if it.get("tag") == "base"]
        all_items += [it for chk, it in self.checkboxes if chk.value]

        errors = []
        total = len(all_items)

        self.status_controls: dict[str, ft.Text] = {}
        self.status_data: dict[str, str] = {}
        self._status_lock = __import__("threading").Lock()
        self.completed_downloads = 0
        self.total_downloads = total

        def progress_callback(info: str, line_id: str):
            with self._status_lock:
                self.status_data[line_id] = info

        self._executor = ThreadPoolExecutor(max_workers=4)
        ex = self._executor
        try:
            futures = {}
            for idx, it in enumerate(all_items, start=1):
                url = it.get("download_url") or it.get("url")
                line_id = f"{idx}:{it['name']}"

                name_txt = ft.Text(f"[{it['name']}]", size=12, weight=ft.FontWeight.BOLD)
                status_txt = ft.Text("", size=12)

                row = ft.Column([name_txt, status_txt], spacing=2)
                self.console_list.controls.append(row)
                self.status_controls[line_id] = status_txt

                if not url:
                    msg = f"Error  -  missing download_url"
                    status_txt.value = msg
                    status_txt.color = ft.Colors.RED
                    status_txt.update()
                    errors.append(f"missing url: {it['name']}")
                    continue

                game_dir = os.path.join(self.target_path, it.get("gamepath", ""))
                ensure_dir(game_dir)

                def worker(item=it, lid=line_id, href=url, gdir=game_dir):
                    try:
                        checksum = item.get("hash")
                        download_method(href, gdir, progress_callback, lid, checksum) 
                    except Exception as exc:
                        with self._status_lock:
                            self.status_data[lid] = f"Error  -  {exc}"
                            self.status_controls[lid].color = ft.Colors.RED
                    finally:
                        with self._status_lock:
                            self.completed_downloads += 1

                futures[ex.submit(worker)] = (it, line_id)

            while True:
                with self._status_lock:
                    for lid, msg in list(self.status_data.items()):
                        txt = self.status_controls.get(lid)
                        if txt:
                            txt.value = msg
                            txt.update()

                    self.progress.value = (
                        self.completed_downloads / self.total_downloads
                        if self.total_downloads else 1
                    )
                    self.progress.update()

                    if self.completed_downloads >= self.total_downloads:
                        break

                self.page.update()
                time.sleep(0.2)
        finally:
            
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None

        self.install_btn.text = "Re-Install"
        self.page.update()

        self.page.open(ft.SnackBar(
            ft.Text("Finished with errors" if errors else "All done!",
                    color=ft.Colors.RED if errors else ft.Colors.GREEN),
            open=True
        ))

        self.page.update()
    
# ---------- Flet instance ----------
def main(page: ft.Page):
    try:
        page.window.prevent_close = True
        theme = create_theme()
        set_theme(page, theme)
        manifest = load_manifest() 
        InstallerApp(page, manifest, theme)
        
    except Exception as e:
        print("Fatal startup error:", e)
        traceback.print_exc()
        raise

if __name__ == "__main__":
    if not os.environ.get("FLET_APP_CHILD"):
        ft.app(target=main)
