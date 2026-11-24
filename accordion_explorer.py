import os
import sys
import json
import time
import shutil
import ctypes
import zipfile
import threading
import subprocess
from ctypes import wintypes

try:
    from PySide6.QtCore import Qt, QUrl, QMimeData, QPoint, QSize, QFileInfo, QTimer, QRect, QEvent, Signal, QObject
    from PySide6.QtGui import (
        QDrag,
        QAction,
        QActionGroup,
        QKeySequence,
        QShortcut,
        QIcon,
        QColor,
        QPainter,
        QPixmap,
        QPen,
        QFont,
        QImageReader,
        QImage,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QSplitter,
        QTreeWidget,
        QTreeWidgetItem,
        QListWidget,
        QListWidgetItem,
        QStackedWidget,
        QHeaderView,
        QPushButton,
        QLineEdit,
        QLabel,
        QMenu,
        QFileDialog,
        QInputDialog,
        QMessageBox,
        QScrollArea,
        QFrame,
        QFileIconProvider,
        QAbstractItemView,
        QToolButton,
        QPlainTextEdit,
        QSizePolicy,
        QDialog,
        QCheckBox,
        QComboBox,
        QSlider,
        QColorDialog,
    )
except ImportError:
    print("\n[!] PySide6 is required.")
    print("    Run this command once in Command Prompt:\n")
    print("        py -m pip install PySide6\n")
    sys.exit(1)


ROLE_PATH = Qt.UserRole + 1
ROLE_IS_DIR = Qt.UserRole + 2

IMAGE_THUMB_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff"}
VIDEO_THUMB_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v", ".flv", ".ts", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".rtf", ".csv"}
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".json", ".cpp", ".c", ".h", ".rs", ".java", ".cs", ".ps1", ".sh", ".sql", ".xml", ".yaml", ".yml"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}


# ---------------------------------------------------------------------------
# Native Windows Helpers (Dark Titlebar, Recycle Bin, Properties, MCI Audio)
# ---------------------------------------------------------------------------

def enable_windows_dark_titlebar(window):
    if os.name != "nt":
        return
    try:
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass



class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("rgrc", wintypes.RECT * 3),
        ("lppos", ctypes.c_void_p),
    ]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


def enable_windows_native_snap_frame(window):
    """Enable WS_THICKFRAME | WS_CAPTION + DWM shadow so Windows 11 Aero Snap & Snap Layouts work natively."""
    if os.name != "nt":
        return
    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi

        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_SYSMENU = 0x00080000

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME | WS_CAPTION | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        # Extend 1px DWM frame into client area to restore native Windows 11 border shadow & animations
        margins = MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

        # Trigger WM_NCCALCSIZE recalculation
        SWP_FRAMECHANGED = 0x0020
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)
    except Exception:
        pass


def send_to_recycle_bin(paths):
    """Send files/folders to the Windows Recycle Bin safely (undoable)."""
    if os.name != "nt":
        for p in paths:
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        return True

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_SILENT = 0x0004

    double_null_paths = "\0".join(os.path.normpath(p) for p in paths) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = double_null_paths
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return res == 0 and not op.fAnyOperationsAborted


def empty_windows_recycle_bin(parent=None):
    """Empty the Windows Recycle Bin using SHEmptyRecycleBinW."""
    if os.name != "nt":
        return
    try:
        hwnd = int(parent.winId()) if parent else None
        # SHERB_NOCONFIRMATION = 0x1, SHERB_NOPROGRESSUI = 0x2, SHERB_NOSOUND = 0x4
        ctypes.windll.shell32.SHEmptyRecycleBinW(hwnd, None, 0x00000001 | 0x00000004)
    except Exception as e:
        if parent:
            QMessageBox.warning(parent, "Recycle Bin", str(e))


def show_windows_properties(path):
    """Open the native Windows Properties dialog for a file or folder."""
    if os.name != "nt":
        return
    try:
        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD),
                ("hIcon", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        SEE_MASK_INVOKEIDLIST = 0x0000000C
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        sei.fMask = SEE_MASK_INVOKEIDLIST
        sei.lpVerb = "properties"
        sei.lpFile = os.path.normpath(path)
        sei.nShow = 1
        ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    except Exception:
        pass


class WindowsMciAudioPlayer:
    """Zero-dependency Windows MCI audio player for instant in-pane playback."""

    def __init__(self):
        self.alias = "acc_finder_audio"
        self.is_open = False
        self.is_playing = False
        self.duration_ms = 0

    def _send(self, cmd):
        if os.name != "nt":
            return ""
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.winmm.mciSendStringW(cmd, buf, 255, None)
        return buf.value

    def load(self, path):
        self.close()
        if os.name != "nt" or not os.path.exists(path):
            return False
        norm = os.path.normpath(path)
        self._send(f'open "{norm}" type mpegvideo alias {self.alias}')
        self._send(f"set {self.alias} time format milliseconds")
        length_str = self._send(f"status {self.alias} length")
        try:
            self.duration_ms = int(length_str)
            self.is_open = self.duration_ms > 0
        except ValueError:
            self.duration_ms = 0
            self.is_open = False
        return self.is_open

    def play(self):
        if not self.is_open:
            return
        self._send(f"play {self.alias}")
        self.is_playing = True

    def pause(self):
        if not self.is_open:
            return
        self._send(f"pause {self.alias}")
        self.is_playing = False

    def seek(self, pos_ms):
        if not self.is_open:
            return
        pos_ms = max(0, min(self.duration_ms, int(pos_ms)))
        if self.is_playing:
            self._send(f"play {self.alias} from {pos_ms}")
        else:
            self._send(f"seek {self.alias} to {pos_ms}")

    def position_ms(self):
        if not self.is_open:
            return 0
        val = self._send(f"status {self.alias} position")
        try:
            return int(val)
        except ValueError:
            return 0

    def mode(self):
        if not self.is_open:
            return "stopped"
        return self._send(f"status {self.alias} mode").lower()

    def close(self):
        if self.is_open:
            self._send(f"close {self.alias}")
        self.is_open = False
        self.is_playing = False
        self.duration_ms = 0


# ---------------------------------------------------------------------------
# Crisp Monochrome Vector Line Icons (Matches Windows 11 Fluent Toolbar)
# ---------------------------------------------------------------------------

def make_fluent_icon(kind, color_hex="#E5E5E5", accent_hex="#60CDFF", size=16):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color_hex), 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)

    if kind == "new_circle":
        p.drawEllipse(2, 2, 12, 12)
        p.drawLine(8, 5, 8, 11)
        p.drawLine(5, 8, 11, 8)
    elif kind == "cut":
        p.drawEllipse(2, 10, 4, 4)
        p.drawEllipse(10, 10, 4, 4)
        p.drawLine(5, 11, 12, 3)
        p.drawLine(11, 11, 4, 3)
    elif kind == "copy":
        p.drawRoundedRect(5, 2, 8, 9, 1.5, 1.5)
        p.drawLine(3, 5, 3, 13)
        p.drawLine(3, 13, 10, 13)
    elif kind == "paste":
        p.drawRoundedRect(3, 3, 10, 11, 1.5, 1.5)
        p.drawRoundedRect(6, 1, 4, 3, 1, 1)
    elif kind == "rename":
        p.drawLine(3, 13, 6, 13)
        p.drawLine(6, 13, 13, 6)
        p.drawLine(13, 6, 10, 3)
        p.drawLine(10, 3, 3, 10)
        p.drawLine(3, 10, 3, 13)
    elif kind == "delete":
        p.drawLine(3, 4, 13, 4)
        p.drawLine(6, 2, 10, 2)
        p.drawRoundedRect(4, 4, 8, 10, 1.5, 1.5)
        p.drawLine(6, 7, 6, 11)
        p.drawLine(10, 7, 10, 11)
    elif kind == "sort":
        p.drawLine(5, 3, 5, 13)
        p.drawLine(5, 3, 2, 6)
        p.drawLine(5, 3, 8, 6)
        p.drawLine(11, 13, 11, 3)
        p.drawLine(11, 13, 8, 10)
        p.drawLine(11, 13, 14, 10)
    elif kind == "view":
        for y in (4, 8, 12):
            p.drawEllipse(2, y - 1, 2, 2)
            p.drawLine(6, y, 14, y)
    elif kind == "details_pane":
        p.drawRoundedRect(2, 3, 12, 10, 2, 2)
        p.drawLine(9, 3, 9, 13)
        p.setPen(QPen(QColor(accent_hex), 1.35, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(11, 6, 12, 6)
        p.drawLine(11, 8, 12, 8)
        p.drawLine(11, 10, 12, 10)
    elif kind == "split_pane":
        p.drawRoundedRect(2, 3, 12, 10, 2, 2)
        p.drawLine(8, 3, 8, 13)
    elif kind == "nav_back":
        p.drawLine(12, 8, 4, 8)
        p.drawLine(4, 8, 8, 4)
        p.drawLine(4, 8, 8, 12)
    elif kind == "nav_fwd":
        p.drawLine(4, 8, 12, 8)
        p.drawLine(12, 8, 8, 4)
        p.drawLine(12, 8, 8, 12)
    elif kind == "nav_up":
        p.drawLine(8, 13, 8, 4)
        p.drawLine(8, 4, 4, 8)
        p.drawLine(8, 4, 12, 8)
    elif kind == "nav_refresh":
        p.drawArc(3, 3, 10, 10, 45 * 16, 290 * 16)
        p.drawLine(11, 3, 13, 6)
        p.drawLine(11, 3, 8, 4)
    elif kind == "win_min":
        p.drawLine(3, 8, 13, 8)
    elif kind == "win_max":
        p.drawRoundedRect(3, 3, 10, 10, 1.5, 1.5)
    elif kind == "win_restore":
        p.drawRect(5, 3, 8, 8)
        p.drawLine(3, 5, 3, 13)
        p.drawLine(3, 13, 11, 13)
    elif kind == "win_close":
        p.drawLine(4, 4, 12, 12)
        p.drawLine(12, 4, 4, 12)
    elif kind == "pin":
        p.drawLine(5, 3, 11, 3)
        p.drawLine(6, 3, 5, 8)
        p.drawLine(10, 3, 11, 8)
        p.drawLine(3, 8, 13, 8)
        p.drawLine(8, 8, 8, 14)
    elif kind == "browse":
        p.drawRoundedRect(2, 4, 12, 9, 1.5, 1.5)
        p.drawLine(2, 6, 7, 6)
        p.drawLine(7, 6, 9, 4)
    elif kind == "select_all":
        p.drawRoundedRect(2, 2, 12, 12, 2, 2)
        p.drawLine(5, 8, 7, 10)
        p.drawLine(7, 10, 11, 6)
    elif kind == "invert":
        p.drawRoundedRect(2, 2, 12, 12, 2, 2)
        p.drawLine(2, 14, 14, 2)
    elif kind == "terminal":
        p.drawRoundedRect(2, 3, 12, 10, 2, 2)
        p.drawLine(5, 6, 7, 8)
        p.drawLine(7, 8, 5, 10)
        p.drawLine(8, 10, 11, 10)
    elif kind == "properties":
        p.drawEllipse(2, 2, 12, 12)
        p.drawLine(8, 7, 8, 11)
        p.drawEllipse(8, 4, 1, 1)
    elif kind == "undo":
        p.drawLine(4, 6, 11, 6)
        p.drawLine(4, 6, 7, 3)
        p.drawLine(4, 6, 7, 9)
        p.drawArc(7, 6, 6, 6, 90 * 16, -180 * 16)
    elif kind == "redo":
        p.drawLine(12, 6, 5, 6)
        p.drawLine(12, 6, 9, 3)
        p.drawLine(12, 6, 9, 9)
        p.drawArc(3, 6, 6, 6, 90 * 16, 180 * 16)
    elif kind == "recycle":
        p.drawLine(3, 4, 13, 4)
        p.drawLine(6, 2, 10, 2)
        p.drawRoundedRect(4, 4, 8, 10, 1.5, 1.5)
        p.drawLine(6, 7, 6, 11)
        p.drawLine(8, 7, 8, 11)
        p.drawLine(10, 7, 10, 11)

    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Native Windows Shell Thumbnail Extractor (Pictures, Videos, PDFs)
# ---------------------------------------------------------------------------

def _extract_windows_shell_thumbnail(path, size_px=128):
    """Extract native Windows Explorer thumbnail (videos, images, PDFs, Office docs) via IShellItemImageFactory."""
    if os.name != "nt":
        return None
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        gdi32 = ctypes.windll.gdi32

        ole32.CoInitialize(None)

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def make_guid(s):
            import uuid
            u = uuid.UUID(s)
            d4 = (ctypes.c_ubyte * 8)(*u.bytes[8:])
            return GUID(u.time_low, u.time_mid, u.time_hi_version, d4)

        IID_IShellItemImageFactory = make_guid("bcc18b79-ba16-442f-80c4-8a59c30c463b")

        class SIZE(ctypes.Structure):
            _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

        class BITMAP(ctypes.Structure):
            _fields_ = [
                ("bmType", ctypes.c_long),
                ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", ctypes.c_ushort),
                ("bmBitsPixel", ctypes.c_ushort),
                ("bmBits", ctypes.c_void_p),
            ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        shell32.SHCreateItemFromParsingName.argtypes = [
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHCreateItemFromParsingName.restype = ctypes.HRESULT

        factory_ptr = ctypes.c_void_p()
        hr = shell32.SHCreateItemFromParsingName(
            os.path.normpath(path),
            None,
            ctypes.byref(IID_IShellItemImageFactory),
            ctypes.byref(factory_ptr),
        )
        if hr != 0 or not factory_ptr.value:
            return None

        vtable = ctypes.cast(factory_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        GetImageProto = ctypes.WINFUNCTYPE(
            ctypes.HRESULT,
            ctypes.c_void_p,
            SIZE,
            ctypes.c_int,
            ctypes.POINTER(wintypes.HBITMAP),
        )
        ReleaseProto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)

        get_image = GetImageProto(vtable[3])
        release_fn = ReleaseProto(vtable[2])

        hbitmap = wintypes.HBITMAP()
        hr_img = get_image(factory_ptr, SIZE(size_px, size_px), 0x08 | 0x01, ctypes.byref(hbitmap))
        release_fn(factory_ptr)

        if hr_img != 0 or not hbitmap.value:
            return None

        try:
            bm = BITMAP()
            if gdi32.GetObjectW(hbitmap, ctypes.sizeof(bm), ctypes.byref(bm)) == 0:
                return None
            w, h = bm.bmWidth, bm.bmHeight
            if w <= 0 or h <= 0:
                return None

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf = ctypes.create_string_buffer(w * h * 4)
            hdc = ctypes.windll.user32.GetDC(None)
            lines = gdi32.GetDIBits(hdc, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)
            ctypes.windll.user32.ReleaseDC(None, hdc)
            if lines == 0:
                return None

            img = QImage(buf.raw, w, h, w * 4, QImage.Format_ARGB32).copy()
            return img if not img.isNull() else None
        finally:
            gdi32.DeleteObject(hbitmap)
    except Exception:
        return None


def build_framed_thumbnail(img, box_size=128, is_video=False):
    pm = QPixmap(box_size, box_size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    scaled = img.scaled(box_size - 6, box_size - 6, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (box_size - scaled.width()) // 2
    y = (box_size - scaled.height()) // 2

    p.setBrush(QColor("#141414"))
    p.setPen(QPen(QColor("#333333"), 1))
    p.drawRoundedRect(x - 2, y - 2, scaled.width() + 4, scaled.height() + 4, 6, 6)
    p.drawImage(x, y, scaled)

    if is_video:
        badge_r = max(11, box_size // 8)
        cx = x + scaled.width() - badge_r - 4
        cy = y + scaled.height() - badge_r - 4
        p.setBrush(QColor(0, 0, 0, 185))
        p.setPen(QPen(QColor("#FFFFFF"), 1.2))
        p.drawEllipse(cx - badge_r, cy - badge_r, badge_r * 2, badge_r * 2)

        tri_r = max(4, badge_r // 2)
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(Qt.NoPen)
        pts = [
            QPoint(cx - tri_r // 2, cy - tri_r),
            QPoint(cx - tri_r // 2, cy + tri_r),
            QPoint(cx + tri_r, cy),
        ]
        p.drawPolygon(pts)

    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
# Icon, Drag Badge & 3-Way File Conflict Dialog (Replace / Skip / Keep Both)
# ---------------------------------------------------------------------------

def make_composite_icon(base_icon, chevron_state=None):
    w, h = 36, 20
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)

    if chevron_state == "closed":
        pen = QPen(QColor("#A0A0A0"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(4, 6, 8, 10)
        painter.drawLine(8, 10, 4, 14)
    elif chevron_state == "open":
        pen = QPen(QColor("#E6E6E6"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(2, 8, 6, 12)
        painter.drawLine(6, 12, 10, 8)

    if not base_icon.isNull():
        base_icon.paint(painter, 15, 1, 18, 18)

    painter.end()
    return QIcon(pm)



FOLDER_COLOR_PRESETS = [
    ("Default Yellow", None),
    ("Red", "#EF4444"),
    ("Orange", "#F97316"),
    ("Gold", "#EAB308"),
    ("Green", "#22C55E"),
    ("Teal", "#14B8A6"),
    ("Blue", "#3B82F6"),
    ("Indigo", "#6366F1"),
    ("Purple", "#A855F7"),
    ("Pink", "#EC4899"),
    ("Gray", "#94A3B8"),
]


def make_colored_folder_icon(hex_color, size=32):
    """Render a sleek Windows 11 style folder icon tinted to the chosen hex color."""
    base = QColor(hex_color)
    tab_col = base.darker(122)
    back_col = base.darker(112)
    front_top = base.lighter(115)
    front_mid = base
    front_bot = base.darker(115)

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)

    s = size / 32.0
    # Top tab
    p.setPen(Qt.NoPen)
    p.setBrush(tab_col)
    p.drawRoundedRect(int(2 * s), int(5 * s), int(12 * s), int(6 * s), 2 * s, 2 * s)
    # Back plate
    p.setBrush(back_col)
    p.drawRoundedRect(int(2 * s), int(7 * s), int(28 * s), int(19 * s), 3 * s, 3 * s)
    # Subtle inner highlight strip
    p.setBrush(front_top)
    p.drawRoundedRect(int(2 * s), int(10 * s), int(28 * s), int(4 * s), 2 * s, 2 * s)
    # Main front body
    p.setBrush(front_mid)
    p.drawRoundedRect(int(2 * s), int(11 * s), int(28 * s), int(16 * s), 3 * s, 3 * s)
    # Bottom edge shading
    p.setBrush(front_bot)
    p.drawRoundedRect(int(3 * s), int(24 * s), int(26 * s), int(3 * s), 1.5 * s, 1.5 * s)

    p.end()
    return QIcon(pm)


def make_color_swatch_icon(hex_color, size=14):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(hex_color))
    p.setPen(QPen(QColor("#555555"), 1))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def make_badge_icon(bg_hex, letter_text):
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setBrush(QColor(bg_hex))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 1, 16, 16, 4, 4)
    p.setPen(QColor("#FFFFFF"))
    p.setFont(QFont("Segoe UI", 8, QFont.Bold))
    p.drawText(pm.rect(), Qt.AlignCenter, letter_text)
    p.end()
    return QIcon(pm)


def make_drag_pixmap(paths):
    if len(paths) == 1:
        text = os.path.basename(paths[0].rstrip("\\/")) or paths[0]
        if len(text) > 32:
            text = text[:31] + "…"
        prefix = "📁 " if os.path.isdir(paths[0]) else "📄 "
        label = prefix + text
    else:
        label = f"📦 {len(paths)} items"

    font = QFont("Segoe UI", 9)
    pm = QPixmap(260, 30)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setFont(font)
    fm = p.fontMetrics()
    box_w = min(252, fm.horizontalAdvance(label) + 24)

    p.setBrush(QColor(35, 35, 35, 235))
    p.setPen(QPen(QColor("#60CDFF"), 1.2))
    p.drawRoundedRect(1, 1, box_w, 26, 6, 6)
    p.setPen(QColor("#F3F3F3"))
    p.drawText(12, 19, label)
    p.end()
    return pm.copy(0, 0, box_w + 3, 29)


class ConflictResolutionDialog(QDialog):
    """Windows 11 style 3-way conflict dialog: Replace, Skip, or Keep Both."""

    def __init__(self, parent, filename, dest_dir, remaining_count=1):
        super().__init__(parent)
        self.setWindowTitle("Replace or Skip Files")
        self.setModal(True)
        self.setFixedWidth(440)
        self.choice = "skip"
        self.apply_all = False

        self.setStyleSheet(
            "QDialog { background-color: #202020; color: #F3F3F3; font-family: 'Segoe UI', sans-serif; }"
            "QLabel { color: #E5E5E5; background: transparent; }"
            "QPushButton { background-color: #2D2D2D; color: #F3F3F3; border: 1px solid #3D3D3D; "
            "border-radius: 5px; padding: 7px 14px; font-size: 12px; }"
            "QPushButton:hover { background-color: #3A3A3A; border-color: #60CDFF; }"
            "QPushButton#PrimaryBtn { background-color: #0078D4; border: none; font-weight: 600; }"
            "QPushButton#PrimaryBtn:hover { background-color: #1886DC; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        hdr = QLabel(f"The destination already has an item named:\n\"{filename}\"")
        hdr.setWordWrap(True)
        hdr.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFFFFF;")
        layout.addWidget(hdr)

        sub = QLabel(f"Location: {dest_dir}")
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 12px; color: #9E9E9E;")
        layout.addWidget(sub)

        self.chk_all = QCheckBox(f"Do this for all remaining conflicts ({remaining_count})")
        self.chk_all.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        if remaining_count <= 1:
            self.chk_all.hide()
        layout.addWidget(self.chk_all)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_replace = QPushButton("Replace")
        btn_replace.setObjectName("PrimaryBtn")
        btn_replace.clicked.connect(lambda: self._choose("replace"))

        btn_keep = QPushButton("Keep Both")
        btn_keep.clicked.connect(lambda: self._choose("keep_both"))

        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(lambda: self._choose("skip"))

        btn_row.addWidget(btn_replace)
        btn_row.addWidget(btn_keep)
        btn_row.addWidget(btn_skip)
        layout.addLayout(btn_row)

    def _choose(self, action):
        self.choice = action
        self.apply_all = self.chk_all.isChecked()
        self.accept()


def _unique_copy_path(dest_dir, base_name):
    name, ext = os.path.splitext(base_name)
    dst = os.path.join(dest_dir, base_name)
    i = 1
    while os.path.exists(dst):
        suffix = " - Copy" if i == 1 else f" - Copy ({i})"
        dst = os.path.join(dest_dir, f"{name}{suffix}{ext}")
        i += 1
    return dst


def transfer_items(src_paths, dest_dir, copy_mode=False, parent_widget=None, record_undo_cb=None):
    dest_abs = os.path.abspath(dest_dir)
    if not os.path.isdir(dest_abs):
        return False

    changed = False
    moved_pairs = []
    copied_targets = []
    remembered_choice = None

    valid_srcs = [os.path.abspath(s) for s in src_paths if s and os.path.exists(s)]
    for idx, src_abs in enumerate(valid_srcs):
        src_parent = os.path.dirname(src_abs)

        if os.path.isdir(src_abs):
            try:
                if os.path.commonpath([src_abs, dest_abs]) == src_abs:
                    continue
            except ValueError:
                pass

        if not copy_mode and os.path.normcase(src_parent) == os.path.normcase(dest_abs):
            continue

        base = os.path.basename(src_abs)
        dst = os.path.join(dest_abs, base)

        if os.path.exists(dst):
            if copy_mode and os.path.normcase(src_abs) == os.path.normcase(dst):
                dst = _unique_copy_path(dest_abs, base)
            else:
                choice = remembered_choice
                if choice is None:
                    dlg = ConflictResolutionDialog(
                        parent_widget, base, dest_abs, remaining_count=len(valid_srcs) - idx
                    )
                    if dlg.exec() == QDialog.Accepted:
                        choice = dlg.choice
                        if dlg.apply_all:
                            remembered_choice = choice
                    else:
                        choice = "skip"

                if choice == "skip":
                    continue
                elif choice == "keep_both":
                    dst = _unique_copy_path(dest_abs, base)
                elif choice == "replace":
                    try:
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    except Exception as e:
                        QMessageBox.warning(parent_widget, "Transfer Error", f"Could not replace {base}:\n{e}")
                        continue

        try:
            if copy_mode:
                if os.path.isdir(src_abs):
                    shutil.copytree(src_abs, dst)
                else:
                    shutil.copy2(src_abs, dst)
                copied_targets.append((src_abs, dst))
            else:
                shutil.move(src_abs, dst)
                moved_pairs.append((src_abs, dst))
            changed = True
        except Exception as e:
            QMessageBox.warning(parent_widget, "Transfer Error", f"Failed on {base}:\n{e}")

    if record_undo_cb:
        if moved_pairs:
            record_undo_cb({"op": "move", "pairs": moved_pairs})
        if copied_targets:
            record_undo_cb({"op": "copy", "pairs": copied_targets})

    return changed


# ---------------------------------------------------------------------------
# Windows-Style Inline Rename Editor (Slow-Click & F2)
# ---------------------------------------------------------------------------

class InlineRenameOverlay(QLineEdit):
    INVALID_CHARS = set('\\/:*?"<>|')

    def __init__(self, view_widget, item_rect, full_path, is_dir, show_extensions, on_commit_cb):
        super().__init__(view_widget.viewport())
        self.view_widget = view_widget
        self.full_path = full_path
        self.is_dir = is_dir
        self.show_extensions = show_extensions
        self.on_commit_cb = on_commit_cb
        self._finished = False

        old_name = os.path.basename(full_path)
        stem, ext = os.path.splitext(old_name)
        self._hidden_ext = ""
        if not is_dir and not show_extensions and ext and stem:
            display_edit = stem
            self._hidden_ext = ext
        else:
            display_edit = old_name

        self.setText(display_edit)
        self.setGeometry(item_rect)
        self.setStyleSheet(
            "QLineEdit {"
            "  background-color: #1F1F1F;"
            "  color: #FFFFFF;"
            "  border: 1.5px solid #60CDFF;"
            "  border-radius: 4px;"
            "  padding: 1px 5px;"
            "  font-family: 'Segoe UI', sans-serif;"
            "  font-size: 13px;"
            "  selection-background-color: #0078D4;"
            "  selection-color: #FFFFFF;"
            "}"
        )

        if not is_dir and not self._hidden_ext:
            dot_idx = display_edit.rfind(".")
            if dot_idx > 0:
                self.setSelection(0, dot_idx)
            else:
                self.selectAll()
        else:
            self.selectAll()

        self.returnPressed.connect(self._commit)
        self.show()
        self.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not self._finished:
            self._commit()

    def _cancel(self):
        if self._finished:
            return
        self._finished = True
        self.hide()
        self.deleteLater()
        self.view_widget.setFocus()

    def _commit(self):
        if self._finished:
            return
        self._finished = True
        raw_text = self.text().strip()
        self.hide()
        self.deleteLater()
        self.view_widget.setFocus()

        if not raw_text:
            return
        new_name = raw_text + self._hidden_ext
        old_name = os.path.basename(self.full_path)
        if new_name == old_name:
            return
        if any(ch in self.INVALID_CHARS for ch in new_name):
            QMessageBox.warning(
                self.view_widget,
                "Invalid File Name",
                'A file name can\'t contain any of the following characters:\n\\ / : * ? " < > |',
            )
            return

        new_path = os.path.join(os.path.dirname(self.full_path), new_name)
        if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(self.full_path):
            QMessageBox.warning(
                self.view_widget,
                "Rename Error",
                f"There is already a file or folder with the name '{new_name}' in this location.",
            )
            return

        try:
            os.rename(self.full_path, new_path)
            if self.on_commit_cb:
                self.on_commit_cb(self.full_path, new_path)
        except Exception as e:
            QMessageBox.warning(self.view_widget, "Rename Error", str(e))


# ---------------------------------------------------------------------------
# View 1: Accordion Details Tree Widget (Inline Expandable Folders + Drag/Drop)
# ---------------------------------------------------------------------------

class AccordionTreeWidget(QTreeWidget):
    def __init__(self, tab, app):
        super().__init__()
        self.tab = tab
        self.app = app
        self._drag_start_pos = None
        self._press_item = None
        self._press_was_selected = False
        self._press_on_label = False
        self._did_drag = False
        self._drop_target_item = None
        self._active_editor = None
        self._pending_rename_item = None
        self._rename_timer = QTimer(self)
        self._rename_timer.setSingleShot(True)
        self._rename_timer.timeout.connect(self._fire_pending_rename)

        self.setColumnCount(4)
        self.setHeaderLabels(["Name", "Date modified", "Type", "Size"])
        self.setRootIsDecorated(False)
        self.setIndentation(22)
        self.setUniformRowHeights(True)
        self.setIconSize(QSize(36, 20))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAllColumnsShowFocus(True)
        self.setMouseTracking(True)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self.tab.on_header_clicked)
        self.setColumnWidth(1, 170)
        self.setColumnWidth(2, 145)
        self.setColumnWidth(3, 100)

        self.customContextMenuRequested.connect(self.tab.on_context_menu)
        self.itemSelectionChanged.connect(self.app.on_selection_changed)

    def _cancel_pending_rename(self):
        self._rename_timer.stop()
        self._pending_rename_item = None

    def _fire_pending_rename(self):
        item = self._pending_rename_item
        self._pending_rename_item = None
        if item is not None and item.isSelected() and len(self.selectedItems()) == 1:
            self.start_inline_rename(item)

    def start_inline_rename(self, item=None):
        self._cancel_pending_rename()
        if item is None:
            sel = self.selectedItems()
            item = sel[0] if sel else self.currentItem()
        if item is None:
            return
        path = item.data(0, ROLE_PATH)
        if not path or not os.path.exists(path):
            return

        self.scrollToItem(item)
        rect = self.visualItemRect(item)
        col0_width = self.columnWidth(0)
        left_x = rect.left() + 36
        edit_w = max(140, min(col0_width - (left_x - rect.left()) - 6, 460))
        edit_rect = QRect(left_x, rect.top() + 2, edit_w, rect.height() - 4)

        def on_renamed(old_p, new_p):
            self.app.record_undo({"op": "rename", "old": old_p, "new": new_p})
            self.app.refresh_and_select(new_p)

        self._active_editor = InlineRenameOverlay(
            self,
            edit_rect,
            path,
            bool(item.data(0, ROLE_IS_DIR)),
            self.app.show_extensions,
            on_renamed,
        )

    def mousePressEvent(self, event):
        self.app.set_active_pane(self.tab.pane)
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            self._drag_start_pos = pos
            item = self.itemAt(pos)
            self._press_item = item
            self._did_drag = False

            selected = self.selectedItems()
            self._press_was_selected = (
                item is not None
                and len(selected) == 1
                and selected[0] is item
                and item.data(0, ROLE_PATH) is not None
            )
            if item is not None:
                item_rect = self.visualItemRect(item)
                col_at_x = self.columnAt(pos.x())
                self._press_on_label = (col_at_x == 0) and ((pos.x() - item_rect.left()) >= 38)
            else:
                self._press_on_label = False
                self._cancel_pending_rename()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.LeftButton)
            and self._drag_start_pos is not None
            and not self._did_drag
        ):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._did_drag = True
                self._cancel_pending_rename()
                self.perform_os_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and not self._did_drag:
            if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                item = self.itemAt(event.position().toPoint())
                if item is not None and item is self._press_item:
                    if self._press_was_selected and self._press_on_label:
                        self._pending_rename_item = item
                        self._rename_timer.start(QApplication.doubleClickInterval())
                    elif item.data(0, ROLE_IS_DIR):
                        self._cancel_pending_rename()
                        self.tab.toggle_folder(item)
                    else:
                        self._cancel_pending_rename()
                else:
                    self._cancel_pending_rename()
            else:
                self._cancel_pending_rename()
        self._drag_start_pos = None
        self._press_item = None
        self._press_was_selected = False
        self._press_on_label = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._cancel_pending_rename()
            item = self.itemAt(event.position().toPoint())
            if item is not None:
                path = item.data(0, ROLE_PATH)
                if path:
                    if item.data(0, ROLE_IS_DIR):
                        self.tab.load_directory(path, push_history=True)
                    else:
                        self.app.launch_file(path)
                    return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        item = self.currentItem()
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter) and item:
            path = item.data(0, ROLE_PATH)
            if path:
                if item.data(0, ROLE_IS_DIR):
                    self.tab.load_directory(path, push_history=True)
                else:
                    self.app.launch_file(path)
            return
        if key == Qt.Key_Space and item and item.data(0, ROLE_IS_DIR):
            self.tab.toggle_folder(item)
            return
        if key == Qt.Key_Right and item and item.data(0, ROLE_IS_DIR):
            self.tab.toggle_folder(item, force_state=True)
            return
        if key == Qt.Key_Left and item:
            if item.data(0, ROLE_IS_DIR) and item.isExpanded():
                self.tab.toggle_folder(item, force_state=False)
            elif item.parent():
                self.setCurrentItem(item.parent())
            return
        if key == Qt.Key_Backspace:
            self.app.go_up()
            return
        if key == Qt.Key_F2:
            self.app.rename_selected()
            return
        if key == Qt.Key_Delete:
            permanent = bool(event.modifiers() & Qt.ShiftModifier)
            self.app.delete_selected(permanent=permanent)
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.app.cycle_view_mode(-1)
            elif delta < 0:
                self.app.cycle_view_mode(1)
            event.accept()
            return
        super().wheelEvent(event)

    def perform_os_drag(self):
        paths = self.tab.selected_paths()
        if not paths and self._press_item:
            p = self._press_item.data(0, ROLE_PATH)
            if p:
                paths = [p]
        if not paths:
            return

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(make_drag_pixmap(paths))
        drag.setHotSpot(QPoint(12, 14))

        result = drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)
        if result == Qt.MoveAction:
            self.app.refresh_all_panes()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        target_item = self.itemAt(event.position().toPoint())
        self._highlight_drop_target(target_item)
        event.setDropAction(Qt.CopyAction if (event.modifiers() & Qt.ControlModifier) else Qt.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self._highlight_drop_target(None)
        super().dragLeaveEvent(event)

    def _highlight_drop_target(self, item):
        if self._drop_target_item is item:
            return
        if self._drop_target_item is not None:
            try:
                for col in range(4):
                    self._drop_target_item.setBackground(col, QColor(0, 0, 0, 0))
            except RuntimeError:
                pass
        self._drop_target_item = item
        if item is not None and item.data(0, ROLE_IS_DIR):
            for col in range(4):
                item.setBackground(col, QColor("#1E3A5F"))

    def dropEvent(self, event):
        self._highlight_drop_target(None)
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        src_paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not src_paths:
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        if target_item and target_item.data(0, ROLE_PATH):
            if target_item.data(0, ROLE_IS_DIR):
                dest_dir = target_item.data(0, ROLE_PATH)
            else:
                dest_dir = os.path.dirname(target_item.data(0, ROLE_PATH))
        else:
            dest_dir = self.tab.current_root

        copy_mode = bool(event.modifiers() & Qt.ControlModifier)
        changed = transfer_items(
            src_paths, dest_dir, copy_mode=copy_mode, parent_widget=self, record_undo_cb=self.app.record_undo
        )
        event.setDropAction(Qt.CopyAction if copy_mode else Qt.MoveAction)
        event.accept()
        if changed:
            self.app.refresh_all_panes()


# ---------------------------------------------------------------------------
# View 2: Icon / Grid / Tiles / List / Content Widget
# ---------------------------------------------------------------------------

class IconGridListWidget(QListWidget):
    def __init__(self, tab, app):
        super().__init__()
        self.tab = tab
        self.app = app
        self._drag_start_pos = None
        self._press_item = None
        self._press_was_selected = False
        self._did_drag = False
        self._active_editor = None
        self._pending_rename_item = None
        self._rename_timer = QTimer(self)
        self._rename_timer.setSingleShot(True)
        self._rename_timer.timeout.connect(self._fire_pending_rename)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setResizeMode(QListWidget.Adjust)
        self.setUniformItemSizes(False)
        self.setWordWrap(True)
        self.setMouseTracking(True)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

        self.customContextMenuRequested.connect(self.tab.on_icon_context_menu)
        self.itemSelectionChanged.connect(self.app.on_selection_changed)

    def apply_mode(self, mode):
        if mode == "Extra large icons":
            self.setViewMode(QListWidget.IconMode)
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setIconSize(QSize(96, 96))
            self.setGridSize(QSize(136, 146))
        elif mode == "Large icons":
            self.setViewMode(QListWidget.IconMode)
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setIconSize(QSize(64, 64))
            self.setGridSize(QSize(112, 114))
        elif mode == "Medium icons":
            self.setViewMode(QListWidget.IconMode)
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setIconSize(QSize(44, 44))
            self.setGridSize(QSize(96, 92))
        elif mode == "Small icons":
            self.setViewMode(QListWidget.ListMode)
            self.setFlow(QListWidget.TopToBottom)
            self.setWrapping(True)
            self.setIconSize(QSize(18, 18))
            self.setGridSize(QSize(210, 26))
        elif mode == "List":
            self.setViewMode(QListWidget.ListMode)
            self.setFlow(QListWidget.TopToBottom)
            self.setWrapping(True)
            self.setIconSize(QSize(18, 18))
            self.setGridSize(QSize(230, 26))
        elif mode == "Tiles":
            self.setViewMode(QListWidget.ListMode)
            self.setFlow(QListWidget.LeftToRight)
            self.setWrapping(True)
            self.setIconSize(QSize(42, 42))
            self.setGridSize(QSize(250, 58))
        elif mode == "Content":
            self.setViewMode(QListWidget.ListMode)
            self.setFlow(QListWidget.TopToBottom)
            self.setWrapping(False)
            self.setIconSize(QSize(32, 32))
            self.setGridSize(QSize(0, 44))

    def _cancel_pending_rename(self):
        self._rename_timer.stop()
        self._pending_rename_item = None

    def _fire_pending_rename(self):
        item = self._pending_rename_item
        self._pending_rename_item = None
        if item is not None and item.isSelected() and len(self.selectedItems()) == 1:
            self.start_inline_rename(item)

    def start_inline_rename(self, item=None):
        self._cancel_pending_rename()
        if item is None:
            sel = self.selectedItems()
            item = sel[0] if sel else self.currentItem()
        if item is None:
            return
        path = item.data(ROLE_PATH)
        if not path or not os.path.exists(path):
            return

        self.scrollToItem(item)
        rect = self.visualItemRect(item)
        if self.viewMode() == QListWidget.IconMode:
            ico_h = self.iconSize().height()
            edit_rect = QRect(rect.left() + 4, rect.top() + ico_h + 4, max(90, rect.width() - 8), 26)
        else:
            ico_w = self.iconSize().width()
            left_x = rect.left() + ico_w + 8
            edit_rect = QRect(left_x, rect.top() + 2, max(120, rect.width() - ico_w - 14), rect.height() - 4)

        def on_renamed(old_p, new_p):
            self.app.record_undo({"op": "rename", "old": old_p, "new": new_p})
            self.app.refresh_and_select(new_p)

        self._active_editor = InlineRenameOverlay(
            self,
            edit_rect,
            path,
            bool(item.data(ROLE_IS_DIR)),
            self.app.show_extensions,
            on_renamed,
        )

    def mousePressEvent(self, event):
        self.app.set_active_pane(self.tab.pane)
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            self._drag_start_pos = pos
            item = self.itemAt(pos)
            self._press_item = item
            self._did_drag = False
            selected = self.selectedItems()
            self._press_was_selected = (
                item is not None
                and len(selected) == 1
                and selected[0] is item
                and item.data(ROLE_PATH) is not None
            )
            if item is None:
                self._cancel_pending_rename()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.LeftButton)
            and self._drag_start_pos is not None
            and not self._did_drag
        ):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._did_drag = True
                self._cancel_pending_rename()
                self.perform_os_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and not self._did_drag:
            if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                item = self.itemAt(event.position().toPoint())
                if item is not None and item is self._press_item and self._press_was_selected:
                    self._pending_rename_item = item
                    self._rename_timer.start(QApplication.doubleClickInterval())
                else:
                    self._cancel_pending_rename()
            else:
                self._cancel_pending_rename()
        self._drag_start_pos = None
        self._press_item = None
        self._press_was_selected = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._cancel_pending_rename()
            item = self.itemAt(event.position().toPoint())
            if item is not None:
                path = item.data(ROLE_PATH)
                if path:
                    if item.data(ROLE_IS_DIR):
                        self.tab.load_directory(path, push_history=True)
                    else:
                        self.app.launch_file(path)
                    return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        item = self.currentItem()
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter) and item:
            path = item.data(ROLE_PATH)
            if path:
                if item.data(ROLE_IS_DIR):
                    self.tab.load_directory(path, push_history=True)
                else:
                    self.app.launch_file(path)
            return
        if key == Qt.Key_Backspace:
            self.app.go_up()
            return
        if key == Qt.Key_F2:
            self.app.rename_selected()
            return
        if key == Qt.Key_Delete:
            self.app.delete_selected(permanent=bool(event.modifiers() & Qt.ShiftModifier))
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.app.cycle_view_mode(-1)
            elif delta < 0:
                self.app.cycle_view_mode(1)
            event.accept()
            return
        super().wheelEvent(event)

    def perform_os_drag(self):
        paths = self.tab.selected_paths()
        if not paths and self._press_item:
            p = self._press_item.data(ROLE_PATH)
            if p:
                paths = [p]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(make_drag_pixmap(paths))
        drag.setHotSpot(QPoint(12, 14))
        result = drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)
        if result == Qt.MoveAction:
            self.app.refresh_all_panes()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction if (event.modifiers() & Qt.ControlModifier) else Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        src_paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        target_item = self.itemAt(event.position().toPoint())
        if target_item and target_item.data(ROLE_IS_DIR):
            dest_dir = target_item.data(ROLE_PATH)
        else:
            dest_dir = self.tab.current_root
        copy_mode = bool(event.modifiers() & Qt.ControlModifier)
        changed = transfer_items(
            src_paths, dest_dir, copy_mode=copy_mode, parent_widget=self, record_undo_cb=self.app.record_undo
        )
        event.setDropAction(Qt.CopyAction if copy_mode else Qt.MoveAction)
        event.accept()
        if changed:
            self.app.refresh_all_panes()


# ---------------------------------------------------------------------------
# Right-Hand Details & Rich Media Preview Pane (Images, Text, PDF, Audio, Video)
# ---------------------------------------------------------------------------

class DetailsPreviewPane(QFrame):
    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tif", ".tiff"}
    TEXT_EXTS = {
        ".txt", ".md", ".py", ".json", ".html", ".htm", ".css", ".js", ".ts",
        ".tsx", ".jsx", ".csv", ".log", ".ini", ".cfg", ".yaml", ".yml",
        ".xml", ".bat", ".ps1", ".sh", ".sql", ".rs", ".cpp", ".c", ".h",
    }

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.current_path = None
        self.audio_player = WindowsMciAudioPlayer()
        self._audio_timer = QTimer(self)
        self._audio_timer.setInterval(250)
        self._audio_timer.timeout.connect(self._tick_audio_progress)

        self.setObjectName("DetailsPane")
        self.setMinimumWidth(220)
        self.setMaximumWidth(900)
        self._raw_preview_pixmap = None
        self.setStyleSheet(
            "QFrame#DetailsPane { background-color: #1C1C1C; border-left: 1px solid #2A2A2A; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("Details & Preview")
        title.setStyleSheet("color: #CCCCCC; font-size: 12px; font-weight: 600; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch(1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8E8E8E; border-radius: 4px; }"
            "QPushButton:hover { background: #2D2D2D; color: #FFFFFF; }"
        )
        close_btn.clicked.connect(self.app.toggle_details_pane)
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Preview Visual Box
        self.preview_box = QFrame()
        self.preview_box.setMinimumHeight(195)
        self.preview_box.setMaximumHeight(460)
        self.preview_box.setStyleSheet(
            "QFrame { background-color: #141414; border: 1px solid #2A2A2A; border-radius: 8px; }"
        )
        pv_layout = QVBoxLayout(self.preview_box)
        pv_layout.setContentsMargins(8, 8, 8, 8)
        pv_layout.setSpacing(4)

        # Top toolbar inside preview box for copying text content
        self.text_copy_bar = QHBoxLayout()
        self.text_copy_bar.setContentsMargins(0, 0, 0, 0)
        self.text_copy_bar.addStretch(1)

        self.copy_text_btn = QPushButton(" Copy text")
        self.copy_text_btn.setIcon(make_fluent_icon("copy", "#E5E5E5", size=14))
        self.copy_text_btn.setCursor(Qt.PointingHandCursor)
        self.copy_text_btn.setToolTip("Copy full file text to clipboard")
        self.copy_text_btn.setStyleSheet(
            "QPushButton { background-color: #242424; color: #E5E5E5; border: 1px solid #363636; "
            "border-radius: 4px; padding: 3px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: #323232; border-color: #60CDFF; color: #FFFFFF; }"
        )
        self.copy_text_btn.clicked.connect(self._copy_file_text_content)
        self.copy_text_btn.hide()
        self.text_copy_bar.addWidget(self.copy_text_btn)
        pv_layout.addLayout(self.text_copy_bar)

        self.image_preview_lbl = QLabel()
        self.image_preview_lbl.setAlignment(Qt.AlignCenter)
        self.image_preview_lbl.setStyleSheet("background: transparent; border: none;")
        pv_layout.addWidget(self.image_preview_lbl)

        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setStyleSheet(
            "QPlainTextEdit { background-color: #141414; color: #DCDCDC; border: none; "
            "font-family: 'Consolas', 'Cascadia Code', monospace; font-size: 11px; }"
        )
        self.text_preview.hide()
        pv_layout.addWidget(self.text_preview)

        # Embedded Audio Player Controls (Shown for audio files)
        self.audio_bar = QFrame()
        self.audio_bar.setStyleSheet("background: #1B1B1B; border: 1px solid #2E2E2E; border-radius: 6px;")
        ab_layout = QHBoxLayout(self.audio_bar)
        ab_layout.setContentsMargins(8, 6, 8, 6)
        ab_layout.setSpacing(6)

        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFixedSize(28, 26)
        self.play_pause_btn.setStyleSheet(
            "QPushButton { background: #0078D4; color: #FFFFFF; border: none; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1886DC; }"
        )
        self.play_pause_btn.clicked.connect(self._toggle_audio_play)
        ab_layout.addWidget(self.play_pause_btn)

        self.audio_slider = QSlider(Qt.Horizontal)
        self.audio_slider.setRange(0, 1000)
        self.audio_slider.sliderMoved.connect(self._on_audio_seek)
        ab_layout.addWidget(self.audio_slider, 1)

        self.audio_time_lbl = QLabel("0:00")
        self.audio_time_lbl.setStyleSheet("color: #AAAAAA; font-size: 11px; border: none;")
        ab_layout.addWidget(self.audio_time_lbl)
        self.audio_bar.hide()
        pv_layout.addWidget(self.audio_bar)

        layout.addWidget(self.preview_box)

        self.name_lbl = QLabel("Select a file or folder")
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 600; background: transparent;")
        layout.addWidget(self.name_lbl)

        self.type_lbl = QLabel("")
        self.type_lbl.setStyleSheet("color: #9A9A9A; font-size: 12px; background: transparent;")
        layout.addWidget(self.type_lbl)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #2A2A2A;")
        layout.addWidget(sep)

        self.meta_lbl = QLabel("")
        self.meta_lbl.setWordWrap(True)
        self.meta_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta_lbl.setStyleSheet("color: #CCCCCC; font-size: 12px; line-height: 1.5; background: transparent;")
        layout.addWidget(self.meta_lbl)

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.setStyleSheet(
            "QPushButton { background-color: #0078D4; color: #FFFFFF; border: none; border-radius: 5px; padding: 6px 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1886DC; }"
        )
        self.open_btn.clicked.connect(self._open_current)
        btn_row.addWidget(self.open_btn)

        self.copy_path_btn = QPushButton("Copy Path")
        self.copy_path_btn.setStyleSheet(
            "QPushButton { background-color: #2B2B2B; color: #F3F3F3; border: 1px solid #3A3A3A; border-radius: 5px; padding: 6px 12px; }"
            "QPushButton:hover { background-color: #363636; }"
        )
        self.copy_path_btn.clicked.connect(self._copy_current_path)
        btn_row.addWidget(self.copy_path_btn)
        layout.addLayout(btn_row)

    def _stop_audio(self):
        self._audio_timer.stop()
        self.audio_player.close()
        self.audio_bar.hide()
        self.play_pause_btn.setText("▶")
        self.audio_slider.setValue(0)
        self.audio_time_lbl.setText("0:00")

    def _toggle_audio_play(self):
        if not self.audio_player.is_open:
            return
        if self.audio_player.is_playing:
            self.audio_player.pause()
            self.play_pause_btn.setText("▶")
            self._audio_timer.stop()
        else:
            self.audio_player.play()
            self.play_pause_btn.setText("⏸")
            self._audio_timer.start()

    def _on_audio_seek(self, val):
        if self.audio_player.is_open and self.audio_player.duration_ms > 0:
            target_ms = int((val / 1000.0) * self.audio_player.duration_ms)
            self.audio_player.seek(target_ms)

    def _tick_audio_progress(self):
        if not self.audio_player.is_open:
            self._audio_timer.stop()
            return
        pos = self.audio_player.position_ms()
        dur = max(1, self.audio_player.duration_ms)
        self.audio_slider.blockSignals(True)
        self.audio_slider.setValue(int((pos / dur) * 1000))
        self.audio_slider.blockSignals(False)
        secs = pos // 1000
        self.audio_time_lbl.setText(f"{secs // 60}:{secs % 60:02d}")
        if self.audio_player.mode() == "stopped" and self.audio_player.is_playing:
            self.audio_player.is_playing = False
            self.play_pause_btn.setText("▶")
            self._audio_timer.stop()

    def _open_current(self):
        if not self.current_path:
            return
        if os.path.isdir(self.current_path):
            self.app.navigate_to(self.current_path)
        else:
            self.app.launch_file(self.current_path)

    def _copy_current_path(self):
        if self.current_path:
            QApplication.clipboard().setText(self.current_path)
            self.app.status_lbl.setText(f"Copied path: {self.current_path}")

    def _copy_file_text_content(self):
        if not self.current_path or not os.path.isfile(self.current_path):
            return
        try:
            with open(self.current_path, "r", encoding="utf-8", errors="replace") as f:
                full_text = f.read()
        except Exception:
            full_text = self.text_preview.toPlainText()
        QApplication.clipboard().setText(full_text)
        self.copy_text_btn.setText(" Copied!")
        self.app.status_lbl.setText(f"Copied text from: {os.path.basename(self.current_path)}")
        QTimer.singleShot(1400, lambda: self.copy_text_btn.setText(" Copy text") if self.copy_text_btn else None)

    def _apply_scaled_preview(self):
        if self._raw_preview_pixmap is None or self._raw_preview_pixmap.isNull():
            return
        avail_w = max(160, self.width() - 48)
        avail_h = max(175, min(420, int(avail_w * 0.75)))
        self.preview_box.setMinimumHeight(min(220, avail_h + 24))
        pm = self._raw_preview_pixmap.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_preview_lbl.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._raw_preview_pixmap is not None and self.image_preview_lbl.isVisible():
            self._apply_scaled_preview()

    def show_item(self, path):
        self._stop_audio()
        self._raw_preview_pixmap = None
        self.preview_box.setMinimumHeight(195)
        self.copy_text_btn.hide()
        self.copy_text_btn.setText(" Copy text")
        self.current_path = path
        if not path or not os.path.exists(path):
            self.name_lbl.setText("No selection")
            self.type_lbl.setText("")
            self.meta_lbl.setText("Select any file or folder to inspect its preview and details.")
            self.text_preview.hide()
            self.image_preview_lbl.show()
            self.image_preview_lbl.setText("No preview")
            self.open_btn.setEnabled(False)
            self.copy_path_btn.setEnabled(False)
            return

        self.open_btn.setEnabled(True)
        self.copy_path_btn.setEnabled(True)
        self.open_btn.setText("Open")

        name = os.path.basename(path.rstrip("\\/")) or path
        self.name_lbl.setText(name)
        is_dir = os.path.isdir(path)

        try:
            st = os.stat(path)
            mod_str = time.strftime("%m/%d/%Y %I:%M %p", time.localtime(st.st_mtime))
            cre_str = time.strftime("%m/%d/%Y %I:%M %p", time.localtime(st.st_ctime))
            size_bytes = st.st_size
        except OSError:
            mod_str = cre_str = "Unknown"
            size_bytes = 0

        if is_dir:
            self.type_lbl.setText("File folder")
            self.text_preview.hide()
            self.image_preview_lbl.show()
            ico = self.app.get_folder_icon(path, None)
            self.image_preview_lbl.setPixmap(ico.pixmap(72, 72))

            try:
                entries = list(os.scandir(path))
                sub_dirs = sum(1 for e in entries if e.is_dir(follow_symlinks=False))
                sub_files = len(entries) - sub_dirs
                contains_txt = f"{sub_files} files, {sub_dirs} folders"
            except Exception:
                contains_txt = "Access restricted"

            self.meta_lbl.setText(
                f"<b>Contains:</b> {contains_txt}<br>"
                f"<b>Date modified:</b> {mod_str}<br>"
                f"<b>Date created:</b> {cre_str}<br>"
                f"<b>Location:</b> {os.path.dirname(path)}"
            )
            return

        ext = os.path.splitext(name)[1].lower()
        kind = f"{ext.upper().lstrip('.')} File" if ext else "File"
        self.type_lbl.setText(kind)

        size_kb = self.app.format_size(size_bytes)
        extra_info = ""

        # 1. Image Preview
        if ext in self.IMAGE_EXTS:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                extra_info = f"<b>Dimensions:</b> {img.width()} × {img.height()} px<br>"
                self._raw_preview_pixmap = QPixmap.fromImage(img)
                self.text_preview.hide()
                self.image_preview_lbl.show()
                self._apply_scaled_preview()
            else:
                self._show_file_icon_preview(path)
        # 2. Video Preview (Shell Video Frame + Play Video button)
        elif ext in VIDEO_THUMB_EXTS:
            self.open_btn.setText("▶ Play Video")
            img = _extract_windows_shell_thumbnail(path, size_px=320)
            if img is not None and not img.isNull():
                extra_info = f"<b>Frame preview:</b> {img.width()} × {img.height()} px<br>"
                self._raw_preview_pixmap = QPixmap.fromImage(img)
                self.text_preview.hide()
                self.image_preview_lbl.show()
                self._apply_scaled_preview()
            else:
                self._show_file_icon_preview(path)
        # 3. Audio Preview (Embedded Play/Pause & Seek Player)
        elif ext in AUDIO_EXTS:
            self.open_btn.setText("Open in Player")
            self._show_file_icon_preview(path)
            if self.audio_player.load(path):
                dur_s = self.audio_player.duration_ms // 1000
                extra_info = f"<b>Duration:</b> {dur_s // 60}:{dur_s % 60:02d}<br>"
                self.audio_time_lbl.setText(f"0:00 / {dur_s // 60}:{dur_s % 60:02d}")
                self.audio_bar.show()
        # 4. PDF Page 1 Thumbnail Preview
        elif ext == ".pdf":
            img = _extract_windows_shell_thumbnail(path, size_px=320)
            if img is not None and not img.isNull():
                self._raw_preview_pixmap = QPixmap.fromImage(img)
                self.text_preview.hide()
                self.image_preview_lbl.show()
                self._apply_scaled_preview()
            else:
                self._show_file_icon_preview(path)
        # 5. Zip Archive Preview (Lists contents)
        elif ext == ".zip":
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    names = zf.namelist()
                extra_info = f"<b>Archive entries:</b> {len(names)} items<br>"
                preview_lines = "\n".join(names[:80])
                if len(names) > 80:
                    preview_lines += f"\n... (+{len(names) - 80} more)"
                self.image_preview_lbl.hide()
                self.text_preview.show()
                self.text_preview.setPlainText(preview_lines or "(Empty ZIP archive)")
            except Exception:
                self._show_file_icon_preview(path)
        # 6. Text / Code Preview
        elif ext in self.TEXT_EXTS or size_bytes < 65536:
            try:
                with open(path, "r", encoding="utf-8", errors="strict") as f:
                    snippet = f.read(4096)
                self.image_preview_lbl.hide()
                self.text_preview.show()
                self.text_preview.setPlainText(snippet if snippet else "(Empty file)")
                self.copy_text_btn.show()
            except Exception:
                self._show_file_icon_preview(path)
        else:
            self._show_file_icon_preview(path)

        self.meta_lbl.setText(
            f"{extra_info}"
            f"<b>Size:</b> {size_kb} ({size_bytes:,} bytes)<br>"
            f"<b>Date modified:</b> {mod_str}<br>"
            f"<b>Date created:</b> {cre_str}<br>"
            f"<b>Location:</b> {os.path.dirname(path)}"
        )

    def _show_file_icon_preview(self, path):
        self.text_preview.hide()
        self.image_preview_lbl.show()
        ico = self.app.icon_provider.icon(QFileInfo(path))
        self.image_preview_lbl.setPixmap(ico.pixmap(68, 68))


# ---------------------------------------------------------------------------
# Sidebar Items (Home, Pinned Folders, Recycle Bin, This PC Drives)
# ---------------------------------------------------------------------------

class SidebarItemWidget(QFrame):
    def __init__(self, app, label, path, icon, pinned=False, is_recycle_bin=False):
        super().__init__()
        self.app = app
        self.path = path
        self.pinned = pinned
        self.is_recycle_bin = is_recycle_bin
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("SidebarRow")
        self.setToolTip("Recycle Bin" if is_recycle_bin else f"{label}\n{path}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 8, 5)
        layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(icon.pixmap(16, 16))
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon_lbl)

        text_lbl = QLabel(label)
        text_lbl.setStyleSheet("color: #F3F3F3; font-size: 12px; background: transparent;")
        text_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(text_lbl, 1)

        self.pin_btn = None
        if pinned:
            self.pin_btn = QPushButton("📌")
            self.pin_btn.setFixedSize(22, 22)
            self.pin_btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; color: #8E8E8E; font-size: 10px; }"
                "QPushButton:hover { color: #FF6B6B; }"
            )
            self.pin_btn.setToolTip("Unpin from sidebar")
            self.pin_btn.clicked.connect(lambda: self.app.unpin_folder(self.path))
            layout.addWidget(self.pin_btn)

    def enterEvent(self, event):
        if self.pin_btn:
            self.pin_btn.setText("✕")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.pin_btn:
            self.pin_btn.setText("📌")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_recycle_bin:
                self.app.open_recycle_bin()
            else:
                self.app.navigate_to(self.path)
        elif event.button() == Qt.RightButton:
            m = QMenu(self)
            if self.is_recycle_bin:
                m.addAction("Open Recycle Bin", self.app.open_recycle_bin)
                m.addAction("Empty Recycle Bin", self.app.empty_recycle_bin_action)
            else:
                m.addAction("Open in New Tab", lambda: self.app.add_tab(self.path))
                if self.pinned:
                    m.addAction("Unpin from Sidebar", lambda: self.app.unpin_folder(self.path))
            m.exec(event.globalPosition().toPoint())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setStyleSheet("QFrame#SidebarRow { background-color: #1E3A5F; border-radius: 5px; }")
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setStyleSheet("")
        src_paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not src_paths:
            event.ignore()
            return
        if self.is_recycle_bin:
            if send_to_recycle_bin(src_paths):
                self.app.refresh_all_panes()
            event.acceptProposedAction()
            return
        copy_mode = bool(event.modifiers() & Qt.ControlModifier)
        changed = transfer_items(
            src_paths, self.path, copy_mode=copy_mode, parent_widget=self, record_undo_cb=self.app.record_undo
        )
        event.acceptProposedAction()
        if changed:
            self.app.refresh_all_panes()


class PinDropZone(QLabel):
    def __init__(self, app):
        super().__init__("📌  Drop folder here to pin")
        self.app = app
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(32)
        self._normal_style = (
            "QLabel { color: #7A7A7A; font-size: 11px; border: 1px dashed #333333; "
            "border-radius: 6px; margin: 4px 10px; background: transparent; }"
        )
        self._active_style = (
            "QLabel { color: #60CDFF; font-size: 11px; border: 1px dashed #60CDFF; "
            "border-radius: 6px; margin: 4px 10px; background: #1E3A5F; }"
        )
        self.setStyleSheet(self._normal_style)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if any(os.path.isdir(p) for p in urls):
                self.setStyleSheet(self._active_style)
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)

    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        for p in urls:
            if os.path.isdir(p):
                self.app.pin_folder(p)
        event.acceptProposedAction()


class DroppableCrumbButton(QPushButton):
    def __init__(self, app, label, target_path, pane):
        super().__init__(label)
        self.app = app
        self.target_path = target_path
        self.pane = pane
        self.setObjectName("CrumbBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setToolTip(target_path)
        self.clicked.connect(lambda: self.pane.navigate_to(self.target_path))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setStyleSheet("QPushButton#CrumbBtn { background-color: #1E3A5F; color: #60CDFF; border-radius: 4px; padding: 2px 6px; }")
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")

    def dropEvent(self, event):
        self.setStyleSheet("")
        src_paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if src_paths:
            copy_mode = bool(event.modifiers() & Qt.ControlModifier)
            changed = transfer_items(
                src_paths, self.target_path, copy_mode=copy_mode, parent_widget=self, record_undo_cb=self.app.record_undo
            )
            event.acceptProposedAction()
            if changed:
                self.app.refresh_all_panes()


# ---------------------------------------------------------------------------
# Tab Container (Supports Accordion Details, All Icon Modes, Recursive Search, Folder Sizes)
# ---------------------------------------------------------------------------

class ExplorerTab(QWidget):
    def __init__(self, pane, app, start_path):
        super().__init__()
        self.pane = pane
        self.app = app
        self.current_root = os.path.abspath(start_path)
        self.history = [self.current_root]
        self.history_idx = 0
        self.loaded_items = set()
        self.sort_col = 0
        self.sort_reverse = False
        self._folder_item_map = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.tree = AccordionTreeWidget(self, app)
        self.icon_list = IconGridListWidget(self, app)
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.icon_list)
        layout.addWidget(self.stack)

        self.apply_view_mode(self.app.view_mode, reload=False)
        self.load_directory(self.current_root, push_history=False)

    def tab_title(self):
        name = os.path.basename(self.current_root.rstrip("\\/"))
        return name if name else self.current_root

    def apply_view_mode(self, mode, reload=True):
        if mode == "Details":
            self.stack.setCurrentWidget(self.tree)
        else:
            self.icon_list.apply_mode(mode)
            self.stack.setCurrentWidget(self.icon_list)
        if reload:
            self.load_directory(self.current_root, push_history=False)

    def on_header_clicked(self, col_idx):
        if self.sort_col == col_idx:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col_idx
            self.sort_reverse = False
        self._update_header_labels()
        self.load_directory(self.current_root, push_history=False)

    def sort_by(self, col_idx, reverse=None):
        self.sort_col = col_idx
        if reverse is not None:
            self.sort_reverse = reverse
        self._update_header_labels()
        self.load_directory(self.current_root, push_history=False)

    def _update_header_labels(self):
        arrow = "  ▼" if self.sort_reverse else "  ▲"
        base = ["Name", "Date modified", "Type", "Size"]
        labels = [b + (arrow if i == self.sort_col else "") for i, b in enumerate(base)]
        self.tree.setHeaderLabels(labels)

    def select_path_in_view(self, target_path):
        if not target_path:
            return
        norm_target = os.path.normcase(os.path.abspath(target_path))
        if self.app.view_mode == "Details":
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                p = it.data(0, ROLE_PATH)
                if p and os.path.normcase(os.path.abspath(p)) == norm_target:
                    self.tree.clearSelection()
                    it.setSelected(True)
                    self.tree.setCurrentItem(it)
                    self.tree.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                    self.tree.setFocus()
                    break
        else:
            for i in range(self.icon_list.count()):
                it = self.icon_list.item(i)
                p = it.data(ROLE_PATH)
                if p and os.path.normcase(os.path.abspath(p)) == norm_target:
                    self.icon_list.clearSelection()
                    it.setSelected(True)
                    self.icon_list.setCurrentItem(it)
                    self.icon_list.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                    self.icon_list.setFocus()
                    break

    def load_directory(self, path, push_history=True, highlight_path=None):
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid Path", f"Folder not found:\n{path}")
            return

        abs_path = os.path.abspath(path)
        if push_history and abs_path != self.current_root:
            self.history = self.history[: self.history_idx + 1]
            self.history.append(abs_path)
            self.history_idx = len(self.history) - 1

        self.current_root = abs_path
        self.tree.clear()
        self.icon_list.clear()
        self.loaded_items.clear()
        self._folder_item_map.clear()

        if self.app.view_mode == "Details":
            self._populate_tree_children(None, self.current_root)
        else:
            self._populate_icon_list(self.current_root)

        if highlight_path:
            self.select_path_in_view(highlight_path)

        self.pane.sync_ui_from_active_tab()
        if self.pane is self.app.active_pane:
            self.app.sync_ui_from_active_tab()

    def can_go_back(self):
        return self.history_idx > 0

    def can_go_forward(self):
        return self.history_idx < len(self.history) - 1

    def go_back(self):
        if self.can_go_back():
            prev_folder = self.current_root
            self.history_idx -= 1
            dest = self.history[self.history_idx]
            highlight = prev_folder if os.path.normcase(os.path.dirname(prev_folder)) == os.path.normcase(dest) else None
            self.load_directory(dest, push_history=False, highlight_path=highlight)

    def go_forward(self):
        if self.can_go_forward():
            prev_folder = self.current_root
            self.history_idx += 1
            dest = self.history[self.history_idx]
            highlight = prev_folder if os.path.normcase(os.path.dirname(prev_folder)) == os.path.normcase(dest) else None
            self.load_directory(dest, push_history=False, highlight_path=highlight)

    def _matches_kind_filter(self, is_dir, ext):
        kf = self.app.kind_filter
        if kf == "All":
            return True
        if kf == "Folders":
            return is_dir
        if is_dir:
            return False
        if kf == "Images":
            return ext in IMAGE_THUMB_EXTS
        if kf == "Videos":
            return ext in VIDEO_THUMB_EXTS
        if kf == "Audio":
            return ext in AUDIO_EXTS
        if kf == "Documents":
            return ext in DOC_EXTS
        if kf == "Code":
            return ext in CODE_EXTS
        if kf == "Archives":
            return ext in ARCHIVE_EXTS
        return True

    def _scan_entries(self, folder_path, allow_recursive=True):
        query = self.app.search_input.text().strip().lower()
        recursive = allow_recursive and self.app.search_subfolders and (bool(query) or self.app.kind_filter != "All")
        include_hidden = self.app.show_hidden
        folders = []
        files = []

        if not recursive:
            with os.scandir(folder_path) as it:
                for entry in it:
                    name = entry.name
                    if not include_hidden and self.app.is_hidden(entry.path, name):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        stat = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue

                    ext = os.path.splitext(name)[1].lower()
                    if not self._matches_kind_filter(is_dir, ext):
                        # When searching by name without recursive mode, still keep folders visible so user can drill in
                        if not (is_dir and query and self.app.kind_filter == "All"):
                            continue

                    if query and not is_dir and query not in name.lower():
                        continue

                    mtime_raw = stat.st_mtime
                    mtime_str = time.strftime("%m/%d/%Y %I:%M %p", time.localtime(mtime_raw))
                    if is_dir:
                        cached_sz = self.app.folder_size_cache.get(os.path.normcase(entry.path), -1)
                        folders.append((name, entry.path, cached_sz, "File folder", mtime_str, mtime_raw))
                    else:
                        kind = f"{ext.upper().lstrip('.')} File" if ext else "File"
                        files.append((name, entry.path, stat.st_size, kind, mtime_str, mtime_raw))
        else:
            # Recursive subfolder search (capped at 500 results for responsiveness)
            count = 0
            for root_dir, dir_names, file_names in os.walk(folder_path):
                if not include_hidden:
                    dir_names[:] = [d for d in dir_names if not self.app.is_hidden(os.path.join(root_dir, d), d)]
                for d in dir_names:
                    full_p = os.path.join(root_dir, d)
                    if query and query not in d.lower():
                        continue
                    if not self._matches_kind_filter(True, ""):
                        continue
                    try:
                        st = os.stat(full_p)
                        mtime_raw = st.st_mtime
                    except OSError:
                        mtime_raw = 0
                    mtime_str = time.strftime("%m/%d/%Y %I:%M %p", time.localtime(mtime_raw))
                    rel = os.path.relpath(full_p, folder_path)
                    folders.append((rel, full_p, -1, "File folder", mtime_str, mtime_raw))
                    count += 1
                    if count >= 500:
                        break
                if count >= 500:
                    break

                for fn in file_names:
                    full_p = os.path.join(root_dir, fn)
                    if not include_hidden and self.app.is_hidden(full_p, fn):
                        continue
                    if query and query not in fn.lower():
                        continue
                    ext = os.path.splitext(fn)[1].lower()
                    if not self._matches_kind_filter(False, ext):
                        continue
                    try:
                        st = os.stat(full_p)
                        mtime_raw = st.st_mtime
                        sz = st.st_size
                    except OSError:
                        mtime_raw = 0
                        sz = 0
                    mtime_str = time.strftime("%m/%d/%Y %I:%M %p", time.localtime(mtime_raw))
                    kind = f"{ext.upper().lstrip('.')} File" if ext else "File"
                    rel = os.path.relpath(full_p, folder_path)
                    files.append((rel, full_p, sz, kind, mtime_str, mtime_raw))
                    count += 1
                    if count >= 500:
                        break
                if count >= 500:
                    break

        def sort_key(item):
            if self.sort_col == 0:
                return item[0].lower()
            if self.sort_col == 1:
                return item[5]
            if self.sort_col == 2:
                return item[3].lower()
            return item[2]

        folders.sort(key=sort_key, reverse=self.sort_reverse)
        files.sort(key=sort_key, reverse=self.sort_reverse)
        return folders, files

    def _display_name(self, name, is_dir):
        if is_dir or self.app.show_extensions:
            return name
        stem, _ = os.path.splitext(name)
        return stem if stem else name

    def _make_tooltip(self, name, full_path, kind, size_str, mtime_str, is_dir):
        if is_dir:
            sz_line = f"\nSize: {size_str}" if size_str else ""
            return f"{name}\nType: Folder{sz_line}\nDate modified: {mtime_str}\nPath: {full_path}"
        return f"{name}\nType: {kind}\nSize: {size_str}\nDate modified: {mtime_str}\nPath: {full_path}"

    def _populate_tree_children(self, parent_item, folder_path):
        try:
            folders, files = self._scan_entries(folder_path, allow_recursive=(parent_item is None))
        except PermissionError:
            self._add_tree_placeholder(parent_item, "Access Denied")
            return
        except OSError as e:
            self._add_tree_placeholder(parent_item, str(e))
            return

        if not folders and not files:
            self._add_tree_placeholder(parent_item, "(No matching items)")
            return

        folders_to_calc = []
        for name, full_path, cached_sz, kind, mtime_str, _ in folders:
            disp = self._display_name(name, True)
            sz_str = self.app.format_size(cached_sz) if cached_sz >= 0 else ("..." if self.app.calc_folder_sizes else "")
            item = QTreeWidgetItem([disp, mtime_str, kind, sz_str])
            item.setData(0, ROLE_PATH, full_path)
            item.setData(0, ROLE_IS_DIR, True)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setIcon(0, self.app.get_folder_icon(full_path, "closed"))
            tip = self._make_tooltip(name, full_path, kind, sz_str, mtime_str, True)
            for c in range(4):
                item.setToolTip(c, tip)
            if self.app.show_checkboxes:
                item.setCheckState(0, Qt.Unchecked)
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            if self.app.calc_folder_sizes and cached_sz < 0:
                self._folder_item_map[os.path.normcase(full_path)] = item
                folders_to_calc.append(full_path)

        for name, full_path, size_bytes, kind, mtime_str, _ in files:
            disp = self._display_name(name, False)
            size_str = self.app.format_size(size_bytes)
            item = QTreeWidgetItem([disp, mtime_str, kind, size_str])
            item.setData(0, ROLE_PATH, full_path)
            item.setData(0, ROLE_IS_DIR, False)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setIcon(0, self.app.get_file_icon(full_path))
            tip = self._make_tooltip(name, full_path, kind, size_str, mtime_str, False)
            for c in range(4):
                item.setToolTip(c, tip)
            if self.app.show_checkboxes:
                item.setCheckState(0, Qt.Unchecked)
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

        if folders_to_calc:
            self.app.request_folder_sizes(folders_to_calc)

    def update_folder_size_cell(self, folder_path, size_bytes):
        key = os.path.normcase(folder_path)
        item = self._folder_item_map.get(key)
        if item is not None:
            try:
                sz_str = self.app.format_size(size_bytes)
                item.setText(3, sz_str)
            except RuntimeError:
                pass

    def _populate_icon_list(self, folder_path):
        try:
            folders, files = self._scan_entries(folder_path, allow_recursive=True)
        except Exception as e:
            self.icon_list.addItem(f"Error: {e}")
            return

        mode = self.app.view_mode
        for name, full_path, _, kind, mtime_str, _ in folders:
            disp = self._display_name(name, True)
            label = f"{disp}\nFile folder" if mode in ("Tiles", "Content") else disp
            item = QListWidgetItem(self.app.get_folder_icon(full_path, None), label)
            item.setData(ROLE_PATH, full_path)
            item.setData(ROLE_IS_DIR, True)
            item.setToolTip(self._make_tooltip(name, full_path, kind, "", mtime_str, True))
            if self.app.show_checkboxes:
                item.setCheckState(Qt.Unchecked)
            self.icon_list.addItem(item)

        thumb_queue = []
        use_thumbs = mode in ("Extra large icons", "Large icons", "Medium icons", "Tiles", "Content")

        for name, full_path, size_bytes, kind, mtime_str, _ in files:
            disp = self._display_name(name, False)
            size_str = self.app.format_size(size_bytes)
            if mode == "Tiles":
                label = f"{disp}\n{kind} • {size_str}"
            elif mode == "Content":
                label = f"{disp}   —   {kind}   •   {size_str}   •   {mtime_str}"
            else:
                label = disp

            ext = os.path.splitext(name)[1].lower()
            if use_thumbs and (ext in IMAGE_THUMB_EXTS or ext in VIDEO_THUMB_EXTS or ext == ".pdf"):
                cached = self.app.get_cached_thumbnail(full_path)
                ico = cached if cached is not None else self.app.get_raw_file_icon(full_path)
                item = QListWidgetItem(ico, label)
                if cached is None:
                    thumb_queue.append((item, full_path, ext))
            else:
                ico = self.app.get_raw_file_icon(full_path)
                item = QListWidgetItem(ico, label)

            item.setData(ROLE_PATH, full_path)
            item.setData(ROLE_IS_DIR, False)
            item.setToolTip(self._make_tooltip(name, full_path, kind, size_str, mtime_str, False))
            if self.app.show_checkboxes:
                item.setCheckState(Qt.Unchecked)
            self.icon_list.addItem(item)

        if thumb_queue:
            self.app.enqueue_thumbnails(thumb_queue)

    def _add_tree_placeholder(self, parent_item, text):
        item = QTreeWidgetItem([text, "", "", ""])
        item.setForeground(0, QColor("#7E7E7E"))
        item.setFlags(Qt.ItemIsEnabled)
        if parent_item is None:
            self.tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)

    def toggle_folder(self, item, force_state=None):
        if not item or not item.data(0, ROLE_IS_DIR):
            return
        path = item.data(0, ROLE_PATH)
        if not path or not os.path.isdir(path):
            return

        currently_open = item.isExpanded()
        target_open = (not currently_open) if force_state is None else force_state

        if target_open and id(item) not in self.loaded_items:
            self._populate_tree_children(item, path)
            self.loaded_items.add(id(item))

        item.setExpanded(target_open)
        item.setIcon(0, self.app.get_folder_icon(path, "open" if target_open else "closed"))

    def collapse_all(self):
        def walk(parent):
            count = self.tree.topLevelItemCount() if parent is None else parent.childCount()
            for i in range(count):
                child = self.tree.topLevelItem(i) if parent is None else parent.child(i)
                if child.data(0, ROLE_IS_DIR):
                    child.setExpanded(False)
                    cpath = child.data(0, ROLE_PATH)
                    child.setIcon(0, self.app.get_folder_icon(cpath, "closed") if cpath else self.app.folder_closed_icon)
                    walk(child)
        walk(None)

    def select_all_items(self):
        if self.app.view_mode == "Details":
            self.tree.selectAll()
        else:
            self.icon_list.selectAll()

    def invert_selection(self):
        if self.app.view_mode == "Details":
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if it.data(0, ROLE_PATH):
                    it.setSelected(not it.isSelected())
        else:
            for i in range(self.icon_list.count()):
                it = self.icon_list.item(i)
                if it.data(ROLE_PATH):
                    it.setSelected(not it.isSelected())

    def total_top_count(self):
        if self.app.view_mode == "Details":
            return self.tree.topLevelItemCount()
        return self.icon_list.count()

    def selected_paths(self):
        paths = []
        if self.app.view_mode == "Details":
            for item in self.tree.selectedItems():
                p = item.data(0, ROLE_PATH)
                if p:
                    paths.append(p)
        else:
            for item in self.icon_list.selectedItems():
                p = item.data(ROLE_PATH)
                if p:
                    paths.append(p)
        return paths

    def on_context_menu(self, pos):
        self.app.set_active_pane(self.pane)
        item = self.tree.itemAt(pos)
        if item and not item.isSelected():
            self.tree.clearSelection()
            item.setSelected(True)
            self.tree.setCurrentItem(item)
        self.app.show_context_menu(self.tree.viewport().mapToGlobal(pos))

    def on_icon_context_menu(self, pos):
        self.app.set_active_pane(self.pane)
        item = self.icon_list.itemAt(pos)
        if item and not item.isSelected():
            self.icon_list.clearSelection()
            item.setSelected(True)
            self.icon_list.setCurrentItem(item)
        self.app.show_context_menu(self.icon_list.viewport().mapToGlobal(pos))


# ---------------------------------------------------------------------------
# Explorer Pane (Used for Primary Pane + Optional Split Dual-Pane Mode)
# ---------------------------------------------------------------------------

class ExplorerPane(QFrame):
    """Self-contained explorer pane with its own tab strip, breadcrumb bar, and file view."""

    def __init__(self, app, start_path, is_secondary=False):
        super().__init__()
        self.app = app
        self.is_secondary = is_secondary
        self.tabs = []
        self.active_tab = None
        self.editing_path = False

        self.setObjectName("ExplorerPane")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Active pane top accent indicator (visible when split mode is active)
        self.active_indicator = QFrame()
        self.active_indicator.setFixedHeight(2)
        self.active_indicator.setStyleSheet("background-color: transparent;")
        layout.addWidget(self.active_indicator)

        # Secondary pane gets its own compact tab + breadcrumb bar
        if is_secondary:
            sec_top = QFrame()
            sec_top.setStyleSheet("background-color: #141414; border-bottom: 1px solid #262626;")
            sec_top.setFixedHeight(34)
            stl = QHBoxLayout(sec_top)
            stl.setContentsMargins(6, 3, 6, 3)
            stl.setSpacing(4)

            self.tab_strip_layout = QHBoxLayout()
            self.tab_strip_layout.setContentsMargins(0, 0, 0, 0)
            self.tab_strip_layout.setSpacing(3)
            stl.addLayout(self.tab_strip_layout)

            add_b = QPushButton("＋")
            add_b.setObjectName("NavBtn")
            add_b.setFixedSize(24, 24)
            add_b.clicked.connect(lambda: self.add_tab(self.current_root()))
            stl.addWidget(add_b)
            stl.addStretch(1)

            close_pane_b = QPushButton("✕")
            close_pane_b.setObjectName("NavBtn")
            close_pane_b.setFixedSize(24, 24)
            close_pane_b.setToolTip("Close Split Pane (F6)")
            close_pane_b.clicked.connect(self.app.toggle_split_pane)
            stl.addWidget(close_pane_b)
            layout.addWidget(sec_top)

            sec_nav = QFrame()
            sec_nav.setStyleSheet("background-color: #1D1D1D; border-bottom: 1px solid #262626;")
            sec_nav.setFixedHeight(38)
            snl = QHBoxLayout(sec_nav)
            snl.setContentsMargins(6, 4, 6, 4)
            snl.setSpacing(3)

            self.back_btn = QPushButton("←")
            self.fwd_btn = QPushButton("→")
            up_b = QPushButton("↑")
            for b, fn in [(self.back_btn, self.go_back), (self.fwd_btn, self.go_forward), (up_b, self.go_up)]:
                b.setObjectName("NavBtn")
                b.setFixedSize(26, 26)
                b.clicked.connect(fn)
                snl.addWidget(b)

            self.addr_pill = QFrame()
            self.addr_pill.setObjectName("AddrPill")
            self.addr_pill.setFixedHeight(28)
            al = QHBoxLayout(self.addr_pill)
            al.setContentsMargins(6, 0, 6, 0)

            self.crumb_container = QWidget()
            self.crumb_container.setStyleSheet("background: transparent;")
            self.crumb_layout = QHBoxLayout(self.crumb_container)
            self.crumb_layout.setContentsMargins(0, 0, 0, 0)
            self.crumb_layout.setSpacing(2)
            self.crumb_container.mousePressEvent = lambda e: self.start_path_edit()
            al.addWidget(self.crumb_container, 1)

            self.path_edit = QLineEdit()
            self.path_edit.setStyleSheet("background: transparent; border: none; color: #F3F3F3; font-size: 12px;")
            self.path_edit.hide()
            self.path_edit.returnPressed.connect(self.commit_path_edit)
            self.path_edit.editingFinished.connect(self.cancel_path_edit)
            al.addWidget(self.path_edit, 1)

            snl.addWidget(self.addr_pill, 1)
            layout.addWidget(sec_nav)
        else:
            # Primary pane uses the main window's top tab strip & address bar
            self.tab_strip_layout = None
            self.crumb_container = None
            self.crumb_layout = None
            self.path_edit = None
            self.back_btn = None
            self.fwd_btn = None

        self.tab_host = QWidget()
        self.tab_host_layout = QVBoxLayout(self.tab_host)
        self.tab_host_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tab_host, 1)

        self.add_tab(start_path)

    def set_focused_visual(self, is_focused, split_active):
        if split_active and is_focused:
            self.active_indicator.setStyleSheet("background-color: #60CDFF;")
        else:
            self.active_indicator.setStyleSheet("background-color: transparent;")

    def current_root(self):
        return self.active_tab.current_root if self.active_tab else os.path.expanduser("~")

    def add_tab(self, path):
        if not os.path.isdir(path):
            path = os.path.expanduser("~")
        tab = ExplorerTab(self, self.app, path)
        self.tabs.append(tab)
        self.tab_host_layout.addWidget(tab)
        self.switch_tab(tab)

    def switch_tab(self, tab):
        for t in self.tabs:
            t.setVisible(t is tab)
        self.active_tab = tab
        self.sync_ui_from_active_tab()
        if self.pane_is_active():
            self.app.sync_ui_from_active_tab()

    def pane_is_active(self):
        return self.app.active_pane is self

    def close_tab(self, tab):
        if len(self.tabs) <= 1:
            return
        idx = self.tabs.index(tab)
        self.tabs.remove(tab)
        self.tab_host_layout.removeWidget(tab)
        tab.deleteLater()
        self.switch_tab(self.tabs[max(0, idx - 1)])

    def navigate_to(self, path):
        self.app.set_active_pane(self)
        if self.active_tab:
            prev_folder = self.active_tab.current_root
            abs_dest = os.path.abspath(path)
            # If jumping up to an ancestor folder (e.g., via breadcrumb), highlight the immediate child folder we came from
            highlight = None
            try:
                if os.path.commonpath([abs_dest, prev_folder]) == abs_dest and abs_dest != prev_folder:
                    rel = os.path.relpath(prev_folder, abs_dest)
                    first_segment = rel.split(os.sep)[0]
                    highlight = os.path.join(abs_dest, first_segment)
            except ValueError:
                pass
            self.active_tab.load_directory(abs_dest, push_history=True, highlight_path=highlight)

    def go_back(self):
        self.app.set_active_pane(self)
        if self.active_tab:
            self.active_tab.go_back()

    def go_forward(self):
        self.app.set_active_pane(self)
        if self.active_tab:
            self.active_tab.go_forward()

    def go_up(self):
        self.app.set_active_pane(self)
        if not self.active_tab:
            return
        prev_folder = self.active_tab.current_root
        parent = os.path.dirname(prev_folder)
        if parent and parent != prev_folder:
            self.active_tab.load_directory(parent, push_history=True, highlight_path=prev_folder)

    def refresh(self):
        if self.active_tab:
            self.active_tab.load_directory(self.active_tab.current_root, push_history=False)

    def sync_ui_from_active_tab(self):
        if not self.is_secondary or not self.active_tab:
            return
        # Render secondary tab bar
        while self.tab_strip_layout.count():
            c = self.tab_strip_layout.takeAt(0)
            if c.widget():
                c.widget().deleteLater()
        for tab in self.tabs:
            is_act = tab is self.active_tab
            bg = "#252525" if is_act else "#141414"
            fg = "#FFFFFF" if is_act else "#9A9A9A"
            pill = QFrame()
            pill.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 5px; }}")
            hl = QHBoxLayout(pill)
            hl.setContentsMargins(8, 2, 6, 2)
            hl.setSpacing(4)
            lbl = QLabel(tab.tab_title()[:18])
            lbl.setStyleSheet(f"color: {fg}; font-size: 11px; background: transparent;")
            hl.addWidget(lbl)
            pill.mousePressEvent = lambda e, t=tab: (self.app.set_active_pane(self), self.switch_tab(t))
            if len(self.tabs) > 1:
                xb = QPushButton("✕")
                xb.setFixedSize(16, 16)
                xb.setStyleSheet("QPushButton { background: transparent; border: none; color: #8E8E8E; font-size: 9px; }")
                xb.clicked.connect(lambda checked=False, t=tab: self.close_tab(t))
                hl.addWidget(xb)
            self.tab_strip_layout.addWidget(pill)

        # Render secondary breadcrumbs
        while self.crumb_layout.count():
            c = self.crumb_layout.takeAt(0)
            if c.widget():
                c.widget().deleteLater()
        path = self.active_tab.current_root
        parts = []
        curr = path
        while True:
            head, tail = os.path.split(curr)
            if tail:
                parts.append((tail, curr))
                curr = head
            else:
                if head:
                    parts.append((head, head))
                break
        parts.reverse()
        for i, (label, full_p) in enumerate(parts):
            if i > 0:
                sep = QLabel("›")
                sep.setStyleSheet("color: #9A9A9A; font-size: 16px; background: transparent;")
                self.crumb_layout.addWidget(sep)
            self.crumb_layout.addWidget(DroppableCrumbButton(self.app, label, full_p, self))
        self.crumb_layout.addStretch(1)
        self.back_btn.setEnabled(self.active_tab.can_go_back())
        self.fwd_btn.setEnabled(self.active_tab.can_go_forward())

    def start_path_edit(self):
        if not self.is_secondary or not self.active_tab or self.editing_path:
            return
        self.editing_path = True
        self.crumb_container.hide()
        self.path_edit.setText(self.active_tab.current_root)
        self.path_edit.show()
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def commit_path_edit(self):
        new_path = self.path_edit.text().strip()
        self.cancel_path_edit()
        if new_path:
            self.navigate_to(new_path)

    def cancel_path_edit(self):
        if not self.editing_path:
            return
        self.editing_path = False
        self.path_edit.hide()
        self.crumb_container.show()


# ---------------------------------------------------------------------------
# Background Folder Size Calculator Signal Bridge
# ---------------------------------------------------------------------------

class FolderSizeSignals(QObject):
    size_ready = Signal(str, object)  # path, size_bytes


# ---------------------------------------------------------------------------
# Main Windows 11 Dark Mode Accordion Explorer Window
# ---------------------------------------------------------------------------

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #191919;
    color: #F3F3F3;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QFrame#TabBar {
    background-color: #0C0C0C;
}
QFrame#NavBar {
    background-color: #1F1F1F;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QFrame#CmdBar {
    background-color: #191919;
    border-bottom: 1px solid #262626;
}
QPushButton#WinCtrlBtn {
    background: transparent;
    border: none;
    color: #CCCCCC;
    border-radius: 0px;
}
QPushButton#WinCtrlBtn:hover {
    background-color: #2B2B2B;
    color: #FFFFFF;
}
QPushButton#WinCloseBtn {
    background: transparent;
    border: none;
    color: #CCCCCC;
    border-radius: 0px;
}
QPushButton#WinCloseBtn:hover {
    background-color: #C42B1C;
    color: #FFFFFF;
}
QFrame#Sidebar {
    background-color: #191919;
    border-right: 1px solid #2A2A2A;
}
QFrame#SidebarRow:hover {
    background-color: #2B2B2B;
    border-radius: 5px;
}
QPushButton#NavBtn, QToolButton#CmdBtn, QPushButton#CmdBtn {
    background: transparent;
    color: #E5E5E5;
    border: none;
    border-radius: 5px;
    padding: 5px 9px;
}
QPushButton#NavBtn:hover, QToolButton#CmdBtn:hover, QPushButton#CmdBtn:hover {
    background-color: #2D2D2D;
}
QPushButton#CmdBtnActive, QToolButton#CmdBtnActive {
    background-color: #2E2E2E;
    color: #60CDFF;
    border: 1px solid #3F3F3F;
    border-radius: 5px;
    padding: 5px 10px;
}
QToolButton#CmdBtn::menu-indicator, QToolButton#CmdBtnActive::menu-indicator {
    image: none;
}
QLineEdit#PillInput {
    background-color: #2B2B2B;
    color: #F3F3F3;
    border: 1px solid #383838;
    border-radius: 5px;
    padding: 4px 10px;
    selection-background-color: #0078D4;
}
QLineEdit#PillInput:focus {
    border: 1px solid #60CDFF;
}
QComboBox#FilterCombo {
    background-color: #2B2B2B;
    color: #E5E5E5;
    border: 1px solid #383838;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 12px;
}
QComboBox#FilterCombo::drop-down {
    border: none;
    width: 18px;
}
QComboBox#FilterCombo QAbstractItemView {
    background-color: #262626;
    color: #F3F3F3;
    border: 1px solid #3A3A3A;
    selection-background-color: #383838;
}
QFrame#AddrPill {
    background-color: #2B2B2B;
    border: 1px solid #383838;
    border-radius: 6px;
}
QPushButton#CrumbBtn {
    background: transparent;
    color: #F3F3F3;
    border: none;
    border-radius: 4px;
    padding: 4px 9px;
    font-size: 15px;
    font-weight: 500;
}
QPushButton#CrumbBtn:hover {
    background-color: #3A3A3A;
    color: #FFFFFF;
}
QTreeWidget, QListWidget {
    background-color: #191919;
    border: none;
    outline: none;
    color: #F3F3F3;
}
QTreeWidget::item {
    height: 30px;
    border-radius: 4px;
    padding-left: 2px;
}
QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: #262626;
    border-radius: 5px;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #323232;
    color: #FFFFFF;
    border-radius: 5px;
}
QHeaderView::section {
    background-color: #191919;
    color: #CCCCCC;
    border: none;
    border-right: 1px solid #262626;
    border-bottom: 1px solid #262626;
    padding: 6px 10px;
    font-size: 12px;
}
QHeaderView::section:hover {
    background-color: #262626;
    color: #FFFFFF;
}
QMenu {
    background-color: #262626;
    color: #F3F3F3;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #383838;
}
QMenu::separator {
    height: 1px;
    background: #383838;
    margin: 4px 8px;
}
QToolTip {
    background-color: #2B2B2B;
    color: #F3F3F3;
    border: 1px solid #454545;
    padding: 6px 8px;
    border-radius: 5px;
    font-size: 12px;
}
QScrollBar:vertical {
    background: #191919;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #3E3E3E;
    min-height: 28px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #555555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QSplitter::handle {
    background-color: #2A2A2A;
    width: 4px;
}
QSplitter::handle:hover {
    background-color: #60CDFF;
}
"""


VIEW_MODES = [
    "Extra large icons",
    "Large icons",
    "Medium icons",
    "Small icons",
    "List",
    "Details",
    "Tiles",
    "Content",
]

KIND_FILTERS = ["All", "Folders", "Images", "Videos", "Audio", "Documents", "Code", "Archives"]


class Win11AccordionExplorer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Accordion Explorer")
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.resize(1340, 790)
        self.setMinimumSize(420, 320)
        self._drag_win_offset = None
        self._override_cursor_active = False

        self.icon_provider = QFileIconProvider()
        self._file_icon_cache = {}
        self._raw_icon_cache = {}
        self._thumb_cache = {}
        self._thumb_queue = []
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(12)
        self._thumb_timer.timeout.connect(self._process_thumbnail_batch)

        self.folder_size_cache = {}
        self._folder_size_inflight = set()
        self.folder_size_signals = FolderSizeSignals()
        self.folder_size_signals.size_ready.connect(self._on_folder_size_ready)

        self.base_folder_icon = self.icon_provider.icon(QFileIconProvider.Folder)
        app_ico = QIcon()
        for sz in (16, 24, 32, 48, 64):
            app_ico.addPixmap(self.base_folder_icon.pixmap(sz, sz))
        self.setWindowIcon(app_ico)
        self.folder_closed_icon = make_composite_icon(self.base_folder_icon, "closed")
        self.folder_open_icon = make_composite_icon(self.base_folder_icon, "open")

        self.pins_file = os.path.join(os.path.expanduser("~"), ".accordion_explorer_pins.json")
        self.pinned_folders = self._load_pins()
        self.folder_colors_file = os.path.join(os.path.expanduser("~"), ".accordion_explorer_folder_colors.json")
        self.folder_colors = self._load_folder_colors()
        self._colored_folder_cache = {}

        self.active_pane = None
        self.clipboard_paths = []
        self.clipboard_mode = None
        self.undo_stack = []
        self.redo_stack = []

        self.view_mode = "Details"
        self.show_hidden = False
        self.show_extensions = True
        self.show_checkboxes = False
        self.calc_folder_sizes = False
        self.details_pane_visible = False
        self.split_pane_visible = False
        self.search_subfolders = False
        self.kind_filter = "All"
        self.editing_path = False

        self.setStyleSheet(DARK_STYLESHEET)
        self._build_ui()
        self._setup_shortcuts()
        enable_windows_dark_titlebar(self)
        enable_windows_native_snap_frame(self)
        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(0, self._update_command_bar_overflow)

    @property
    def active_tab(self):
        return self.active_pane.active_tab if hasattr(self, "active_pane") and self.active_pane else None

    def set_active_pane(self, pane):
        if self.active_pane is pane:
            return
        self.active_pane = pane
        self.primary_pane.set_focused_visual(self.active_pane is self.primary_pane, self.split_pane_visible)
        self.secondary_pane.set_focused_visual(self.active_pane is self.secondary_pane, self.split_pane_visible)
        self.on_selection_changed()

    def get_ext_icon(self, ext, fallback_color="#4B5563", fallback_text="FILE"):
        dummy_path = os.path.join(os.path.expanduser("~"), f"__dummy_icon_probe__{ext}")
        ico = self.icon_provider.icon(QFileInfo(dummy_path))
        if ico.isNull():
            return make_badge_icon(fallback_color, fallback_text)
        return ico

    def get_file_icon(self, path):
        ext = os.path.splitext(path)[1].lower()
        key = ext if ext and ext not in (".exe", ".ico", ".lnk") else path
        if key not in self._file_icon_cache:
            raw = self.icon_provider.icon(QFileInfo(path))
            self._file_icon_cache[key] = make_composite_icon(raw, None)
        return self._file_icon_cache[key]

    def get_raw_file_icon(self, path):
        ext = os.path.splitext(path)[1].lower()
        key = ext if ext and ext not in (".exe", ".ico", ".lnk") else path
        if key not in self._raw_icon_cache:
            self._raw_icon_cache[key] = self.icon_provider.icon(QFileInfo(path))
        return self._raw_icon_cache[key]

    def get_cached_thumbnail(self, path):
        try:
            st = os.stat(path)
            key = (os.path.normcase(path), st.st_mtime_ns, st.st_size)
        except OSError:
            key = (os.path.normcase(path), 0, 0)
        return self._thumb_cache.get(key)

    def _build_media_thumbnail(self, path, ext):
        try:
            st = os.stat(path)
            key = (os.path.normcase(path), st.st_mtime_ns, st.st_size)
        except OSError:
            key = (os.path.normcase(path), 0, 0)

        if key in self._thumb_cache:
            return self._thumb_cache[key]

        ico = None
        if ext in IMAGE_THUMB_EXTS:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                ico = build_framed_thumbnail(img, box_size=128, is_video=False)
        elif ext in VIDEO_THUMB_EXTS:
            img = _extract_windows_shell_thumbnail(path, size_px=128)
            if img is not None and not img.isNull():
                ico = build_framed_thumbnail(img, box_size=128, is_video=True)
        elif ext == ".pdf":
            img = _extract_windows_shell_thumbnail(path, size_px=128)
            if img is not None and not img.isNull():
                ico = build_framed_thumbnail(img, box_size=128, is_video=False)

        if ico is None:
            ico = self.get_raw_file_icon(path)

        self._thumb_cache[key] = ico
        return ico

    def enqueue_thumbnails(self, items):
        self._thumb_queue.extend(items)
        if not self._thumb_timer.isActive():
            self._thumb_timer.start()

    def _process_thumbnail_batch(self):
        if not self._thumb_queue:
            self._thumb_timer.stop()
            return
        batch = self._thumb_queue[:6]
        self._thumb_queue = self._thumb_queue[6:]
        for item, full_path, ext in batch:
            try:
                if item.listWidget() is None:
                    continue
                ico = self._build_media_thumbnail(full_path, ext)
                item.setIcon(ico)
            except RuntimeError:
                continue

    def request_folder_sizes(self, folder_paths):
        to_run = []
        for p in folder_paths:
            key = os.path.normcase(p)
            if key not in self.folder_size_cache and key not in self._folder_size_inflight:
                self._folder_size_inflight.add(key)
                to_run.append(p)
        if not to_run:
            return

        def worker(paths):
            for fp in paths:
                total = 0
                try:
                    for r, _, fns in os.walk(fp):
                        for fn in fns:
                            try:
                                total += os.path.getsize(os.path.join(r, fn))
                            except OSError:
                                pass
                except OSError:
                    pass
                self.folder_size_signals.size_ready.emit(fp, total)

        threading.Thread(target=worker, args=(to_run,), daemon=True).start()

    def _on_folder_size_ready(self, folder_path, size_bytes):
        key = os.path.normcase(folder_path)
        self._folder_size_inflight.discard(key)
        self.folder_size_cache[key] = size_bytes
        for pane in (self.primary_pane, self.secondary_pane):
            for tab in pane.tabs:
                tab.update_folder_size_cell(folder_path, size_bytes)

    def _load_pins(self):
        if os.path.exists(self.pins_file):
            try:
                with open(self.pins_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [p for p in data if os.path.isdir(p)]
            except Exception:
                pass
        home = os.path.expanduser("~")
        defaults = [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Pictures"),
        ]
        return [p for p in defaults if os.path.isdir(p)]

    def _load_folder_colors(self):
        if os.path.exists(self.folder_colors_file):
            try:
                with open(self.folder_colors_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _save_folder_colors(self):
        try:
            with open(self.folder_colors_file, "w", encoding="utf-8") as f:
                json.dump(self.folder_colors, f, indent=2)
        except Exception:
            pass

    def get_folder_icon(self, path, chevron_state=None):
        """Return custom colored folder icon (with optional chevron) if set, otherwise default Win11 folder."""
        if not path:
            if chevron_state == "closed":
                return self.folder_closed_icon
            if chevron_state == "open":
                return self.folder_open_icon
            return self.base_folder_icon

        hex_col = self.folder_colors.get(os.path.normcase(os.path.abspath(path)))
        if not hex_col:
            if chevron_state == "closed":
                return self.folder_closed_icon
            if chevron_state == "open":
                return self.folder_open_icon
            return self.base_folder_icon

        cache_key = (hex_col.lower(), chevron_state)
        if cache_key not in self._colored_folder_cache:
            base = make_colored_folder_icon(hex_col, size=32)
            if chevron_state in ("closed", "open"):
                self._colored_folder_cache[cache_key] = make_composite_icon(base, chevron_state)
            else:
                self._colored_folder_cache[cache_key] = base
        return self._colored_folder_cache[cache_key]

    def set_folder_color(self, folder_paths, hex_color):
        changed = False
        for p in folder_paths:
            if not p or not os.path.isdir(p):
                continue
            norm = os.path.normcase(os.path.abspath(p))
            if hex_color is None:
                if norm in self.folder_colors:
                    del self.folder_colors[norm]
                    changed = True
            else:
                self.folder_colors[norm] = hex_color
                changed = True
        if changed:
            self._save_folder_colors()
            self._render_sidebar()
            self.refresh_all_panes()
            self.status_lbl.setText(
                "Reset folder color to default" if hex_color is None else f"Updated folder color ({hex_color})"
            )

    def pick_custom_folder_color(self, folder_paths):
        first = folder_paths[0]
        cur_hex = self.folder_colors.get(os.path.normcase(os.path.abspath(first)), "#3B82F6")
        chosen = QColorDialog.getColor(QColor(cur_hex), self, "Choose Folder Color")
        if chosen.isValid():
            self.set_folder_color(folder_paths, chosen.name())

    def _save_pins(self):
        try:
            with open(self.pins_file, "w", encoding="utf-8") as f:
                json.dump(self.pinned_folders, f, indent=2)
        except Exception:
            pass

    def pin_folder(self, path):
        abs_p = os.path.abspath(path)
        if os.path.isdir(abs_p) and abs_p not in self.pinned_folders:
            self.pinned_folders.append(abs_p)
            self._save_pins()
            self._render_sidebar()
            self.status_lbl.setText(f"Pinned to sidebar: {os.path.basename(abs_p) or abs_p}")

    def unpin_folder(self, path):
        if path in self.pinned_folders:
            self.pinned_folders.remove(path)
            self._save_pins()
            self._render_sidebar()
            self.status_lbl.setText(f"Unpinned: {os.path.basename(path) or path}")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. MERGED WINDOWS 11 TAB BAR + WINDOW CONTROLS
        self.tab_bar = QFrame()
        self.tab_bar.setObjectName("TabBar")
        self.tab_bar.setFixedHeight(40)
        tab_bar_layout = QHBoxLayout(self.tab_bar)
        tab_bar_layout.setContentsMargins(8, 6, 0, 0)
        tab_bar_layout.setSpacing(4)

        self.tab_strip_layout = QHBoxLayout()
        self.tab_strip_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_strip_layout.setSpacing(3)
        tab_bar_layout.addLayout(self.tab_strip_layout)

        new_tab_btn = QPushButton("＋")
        new_tab_btn.setObjectName("NavBtn")
        new_tab_btn.setFixedSize(28, 28)
        new_tab_btn.setToolTip("New Tab (Ctrl+T)")
        new_tab_btn.clicked.connect(
            lambda: self.primary_pane.add_tab(self.primary_pane.current_root())
        )
        tab_bar_layout.addWidget(new_tab_btn)

        self.drag_spacer = QWidget()
        self.drag_spacer.setStyleSheet("background: transparent;")
        self.drag_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drag_spacer.mousePressEvent = self._on_titlebar_press
        self.drag_spacer.mouseMoveEvent = self._on_titlebar_move
        self.drag_spacer.mouseReleaseEvent = self._on_titlebar_release
        self.drag_spacer.mouseDoubleClickEvent = lambda e: self._toggle_max_restore()
        tab_bar_layout.addWidget(self.drag_spacer, 1)

        cap_box = QHBoxLayout()
        cap_box.setContentsMargins(0, 0, 0, 6)
        cap_box.setSpacing(0)

        self.min_btn = QPushButton()
        self.min_btn.setObjectName("WinCtrlBtn")
        self.min_btn.setIcon(make_fluent_icon("win_min", "#CCCCCC", size=14))
        self.min_btn.setFixedSize(46, 34)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.clicked.connect(self.showMinimized)
        cap_box.addWidget(self.min_btn)

        self.max_btn = QPushButton()
        self.max_btn.setObjectName("WinCtrlBtn")
        self.max_btn.setIcon(make_fluent_icon("win_max", "#CCCCCC", size=14))
        self.max_btn.setFixedSize(46, 34)
        self.max_btn.setToolTip("Maximize")
        self.max_btn.clicked.connect(self._toggle_max_restore)
        cap_box.addWidget(self.max_btn)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("WinCloseBtn")
        self.close_btn.setIcon(make_fluent_icon("win_close", "#CCCCCC", size=14))
        self.close_btn.setFixedSize(46, 34)
        self.close_btn.setToolTip("Close")
        self.close_btn.clicked.connect(self.close)
        cap_box.addWidget(self.close_btn)

        tab_bar_layout.addLayout(cap_box)
        root_layout.addWidget(self.tab_bar)

        # 2. NAVIGATION + BREADCRUMB + KIND FILTER + SEARCH BAR
        nav_bar = QFrame()
        nav_bar.setObjectName("NavBar")
        nav_bar.setFixedHeight(54)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 8, 10, 8)
        nav_layout.setSpacing(6)

        self.back_btn = QPushButton()
        self.fwd_btn = QPushButton()
        up_btn = QPushButton()
        ref_btn = QPushButton()
        for btn, ikind, slot, tip in [
            (self.back_btn, "nav_back", self.go_back, "Back (Alt+Left)"),
            (self.fwd_btn, "nav_fwd", self.go_forward, "Forward (Alt+Right)"),
            (up_btn, "nav_up", self.go_up, "Up one level (Alt+Up)"),
            (ref_btn, "nav_refresh", self.refresh, "Refresh (F5)"),
        ]:
            btn.setObjectName("NavBtn")
            btn.setIcon(make_fluent_icon(ikind, "#E5E5E5", size=18))
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(36, 36)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            nav_layout.addWidget(btn)

        self.addr_pill = QFrame()
        self.addr_pill.setObjectName("AddrPill")
        self.addr_pill.setFixedHeight(38)
        self.addr_layout = QHBoxLayout(self.addr_pill)
        self.addr_layout.setContentsMargins(10, 0, 10, 0)
        self.addr_layout.setSpacing(4)

        self.crumb_container = QWidget()
        self.crumb_container.setStyleSheet("background: transparent;")
        self.crumb_layout = QHBoxLayout(self.crumb_container)
        self.crumb_layout.setContentsMargins(0, 0, 0, 0)
        self.crumb_layout.setSpacing(3)
        self.crumb_container.mousePressEvent = lambda e: self._start_path_edit()
        self.addr_layout.addWidget(self.crumb_container, 1)

        self.path_edit = QLineEdit()
        self.path_edit.setStyleSheet("background: transparent; border: none; color: #FFFFFF; font-size: 15px;")
        self.path_edit.hide()
        self.path_edit.returnPressed.connect(self._commit_path_edit)
        self.path_edit.editingFinished.connect(self._cancel_path_edit)
        self.addr_layout.addWidget(self.path_edit, 1)

        nav_layout.addWidget(self.addr_pill, 1)

        # Kind Filter Dropdown
        self.kind_combo = QComboBox()
        self.kind_combo.setObjectName("FilterCombo")
        self.kind_combo.addItems(KIND_FILTERS)
        self.kind_combo.setFixedHeight(38)
        self.kind_combo.setToolTip("Filter by file kind")
        self.kind_combo.currentTextChanged.connect(self._on_kind_filter_changed)
        nav_layout.addWidget(self.kind_combo)

        # Recursive Subfolders Toggle
        self.subfolders_btn = QPushButton("Subfolders")
        self.subfolders_btn.setObjectName("CmdBtn")
        self.subfolders_btn.setFixedHeight(38)
        self.subfolders_btn.setToolTip("Include nested subfolders when searching/filtering")
        self.subfolders_btn.clicked.connect(self._toggle_search_subfolders)
        nav_layout.addWidget(self.subfolders_btn)

        # Search Pill
        self.search_input = QLineEdit()
        self.search_input.setObjectName("PillInput")
        self.search_input.setPlaceholderText("Search folder")
        self.search_input.setFixedSize(220, 38)
        self.search_input.textChanged.connect(lambda: self.refresh_all_panes())
        nav_layout.addWidget(self.search_input)

        root_layout.addWidget(nav_bar)

        # 3. COMMAND BAR
        cmd_bar = QFrame()
        cmd_bar.setObjectName("CmdBar")
        cmd_bar.setFixedHeight(44)
        cmd_layout = QHBoxLayout(cmd_bar)
        cmd_layout.setContentsMargins(10, 4, 10, 4)
        cmd_layout.setSpacing(4)

        new_btn = QToolButton()
        new_btn.setObjectName("CmdBtn")
        new_btn.setIcon(make_fluent_icon("new_circle", "#60CDFF", size=16))
        new_btn.setText("  New  ▾")
        new_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        new_btn.setPopupMode(QToolButton.InstantPopup)
        new_menu = self._build_new_menu(new_btn)
        new_btn.setMenu(new_menu)
        cmd_layout.addWidget(new_btn)

        cmd_layout.addWidget(self._make_vsep())

        for icon_kind, tip, fn in [
            ("cut", "Cut (Ctrl+X)", lambda: self.copy_cut_selected("cut")),
            ("copy", "Copy (Ctrl+C)", lambda: self.copy_cut_selected("copy")),
            ("paste", "Paste (Ctrl+V)", self.paste_items),
            ("rename", "Rename (F2 or slow double-click)", self.rename_selected),
            ("delete", "Delete to Recycle Bin (Del)  |  Shift+Del Permanent", lambda: self.delete_selected(False)),
        ]:
            b = QPushButton()
            b.setObjectName("CmdBtn")
            b.setIcon(make_fluent_icon(icon_kind, "#CCCCCC", size=16))
            b.setFixedSize(34, 30)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            cmd_layout.addWidget(b)

        cmd_layout.addWidget(self._make_vsep())

        self.sort_btn = QToolButton()
        self.sort_btn.setObjectName("CmdBtn")
        self.sort_btn.setIcon(make_fluent_icon("sort", "#CCCCCC", size=16))
        self.sort_btn.setText("  Sort  ▾")
        self.sort_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.sort_btn.setPopupMode(QToolButton.InstantPopup)
        sort_menu = QMenu(self.sort_btn)
        sort_menu.addAction("Name", lambda: self.active_tab.sort_by(0))
        sort_menu.addAction("Date modified", lambda: self.active_tab.sort_by(1))
        sort_menu.addAction("Type", lambda: self.active_tab.sort_by(2))
        sort_menu.addAction("Size", lambda: self.active_tab.sort_by(3))
        sort_menu.addSeparator()
        sort_menu.addAction("Ascending", lambda: self.active_tab.sort_by(self.active_tab.sort_col, False))
        sort_menu.addAction("Descending", lambda: self.active_tab.sort_by(self.active_tab.sort_col, True))
        self.sort_btn.setMenu(sort_menu)
        cmd_layout.addWidget(self.sort_btn)

        self.view_btn = QToolButton()
        self.view_btn.setObjectName("CmdBtn")
        self.view_btn.setIcon(make_fluent_icon("view", "#CCCCCC", size=16))
        self.view_btn.setText("  View  ▾")
        self.view_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.view_btn.setPopupMode(QToolButton.InstantPopup)
        view_menu = QMenu(self.view_btn)

        self.view_action_group = QActionGroup(self)
        self.view_action_group.setExclusive(True)
        self.view_actions = {}
        for mode in VIEW_MODES:
            act = QAction(mode, self, checkable=True)
            if mode == self.view_mode:
                act.setChecked(True)
            act.triggered.connect(lambda checked=False, m=mode: self.set_view_mode(m))
            self.view_action_group.addAction(act)
            view_menu.addAction(act)
            self.view_actions[mode] = act

        view_menu.addSeparator()

        self.details_pane_act = QAction("Details / Preview pane", self, checkable=True)
        self.details_pane_act.triggered.connect(self.toggle_details_pane)
        view_menu.addAction(self.details_pane_act)

        self.split_pane_act = QAction("Split / Dual-pane view  (F6)", self, checkable=True)
        self.split_pane_act.triggered.connect(self.toggle_split_pane)
        view_menu.addAction(self.split_pane_act)

        view_menu.addSeparator()

        show_sub = view_menu.addMenu("Show")
        self.ext_act = QAction("File name extensions", self, checkable=True)
        self.ext_act.setChecked(self.show_extensions)
        self.ext_act.triggered.connect(self._toggle_extensions)
        show_sub.addAction(self.ext_act)

        self.hidden_act = QAction("Hidden items", self, checkable=True)
        self.hidden_act.setChecked(self.show_hidden)
        self.hidden_act.triggered.connect(self._toggle_hidden)
        show_sub.addAction(self.hidden_act)

        self.chk_act = QAction("Item check boxes", self, checkable=True)
        self.chk_act.setChecked(self.show_checkboxes)
        self.chk_act.triggered.connect(self._toggle_checkboxes)
        show_sub.addAction(self.chk_act)

        self.folder_sz_act = QAction("Calculate folder sizes", self, checkable=True)
        self.folder_sz_act.setChecked(self.calc_folder_sizes)
        self.folder_sz_act.triggered.connect(self._toggle_calc_folder_sizes)
        show_sub.addAction(self.folder_sz_act)

        view_menu.addSeparator()
        view_menu.addAction("Collapse all expanded folders", self.collapse_all)
        self.view_btn.setMenu(view_menu)
        cmd_layout.addWidget(self.view_btn)

        cmd_layout.addWidget(self._make_vsep())

        # Command bar items (Priority+ overflow into "•••" only if window is narrow).
        # Note: Browse, Select all, and Invert stay inside "•••" ONLY per user preference!
        self.overflow_specs = [
            ("pin", "Pin to sidebar", "Pin current folder to sidebar", lambda: self.pin_folder(self.active_tab.current_root) if self.active_tab else None),
            ("terminal", "Terminal", "Open current folder in Windows Terminal", self.open_in_terminal),
            ("properties", "Properties", "Properties (Alt+Enter)", self.open_properties),
        ]
        self.overflow_buttons = []
        for icon_kind, label, tip, fn in self.overflow_specs:
            ob = QPushButton(f" {label}")
            ob.setObjectName("CmdBtn")
            ob.setIcon(make_fluent_icon(icon_kind, "#CCCCCC", size=15))
            ob.setToolTip(tip)
            ob.clicked.connect(fn)
            cmd_layout.addWidget(ob)
            self.overflow_buttons.append((ob, icon_kind, label, fn))

        # Always-visible "•••" menu (contains Browse, Select all, Invert, Undo/Redo, plus any overflow items)
        self.more_btn = QToolButton()
        self.more_btn.setObjectName("CmdBtn")
        self.more_btn.setText("•••")
        self.more_btn.setToolTip("See more")
        self.more_btn.setPopupMode(QToolButton.InstantPopup)
        self.more_menu = QMenu(self.more_btn)
        self.more_btn.setMenu(self.more_menu)
        cmd_layout.addWidget(self.more_btn)

        cmd_layout.addStretch(1)

        # Right-Side Split Dual-Pane Toggle Button
        self.split_btn = QPushButton("  Split")
        self.split_btn.setIcon(make_fluent_icon("split_pane", "#CCCCCC", "#60CDFF", size=16))
        self.split_btn.setObjectName("CmdBtn")
        self.split_btn.setToolTip("Toggle Split Dual-Pane View (F6)")
        self.split_btn.clicked.connect(self.toggle_split_pane)
        cmd_layout.addWidget(self.split_btn)

        # Far-Right "Details" Preview Pane Toggle Button
        self.details_btn = QPushButton("  Details")
        self.details_btn.setIcon(make_fluent_icon("details_pane", "#CCCCCC", "#60CDFF", size=16))
        self.details_btn.setObjectName("CmdBtn")
        self.details_btn.setToolTip("Toggle Details & File Preview pane (Alt+Shift+P)")
        self.details_btn.clicked.connect(self.toggle_details_pane)
        cmd_layout.addWidget(self.details_btn)

        root_layout.addWidget(cmd_bar)

        # 4. MAIN SPLITTER (Left Sidebar + Primary Pane + Secondary Split Pane + Right Details Pane)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.setChildrenCollapsible(False)

        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("Sidebar")
        self.sidebar_frame.setMinimumWidth(130)
        self.sidebar_frame.setMaximumWidth(600)
        sidebar_outer = QVBoxLayout(self.sidebar_frame)
        sidebar_outer.setContentsMargins(0, 6, 0, 6)
        sidebar_outer.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.sidebar_content = QWidget()
        self.sidebar_layout = QVBoxLayout(self.sidebar_content)
        self.sidebar_layout.setContentsMargins(4, 2, 4, 2)
        self.sidebar_layout.setSpacing(2)
        scroll.setWidget(self.sidebar_content)
        sidebar_outer.addWidget(scroll, 1)

        sidebar_outer.addWidget(PinDropZone(self))
        self.main_splitter.addWidget(self.sidebar_frame)

        home_dir = os.path.expanduser("~")
        self.primary_pane = ExplorerPane(self, home_dir, is_secondary=False)
        self.main_splitter.addWidget(self.primary_pane)

        self.secondary_pane = ExplorerPane(self, home_dir, is_secondary=True)
        self.secondary_pane.hide()
        self.main_splitter.addWidget(self.secondary_pane)

        self.active_pane = self.primary_pane

        self.details_pane = DetailsPreviewPane(self)
        self.details_pane.hide()
        self.main_splitter.addWidget(self.details_pane)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)
        self.main_splitter.setStretchFactor(3, 0)
        self.main_splitter.setSizes([225, 1115, 500, 320])
        root_layout.addWidget(self.main_splitter, 1)

        # 5. STATUS BAR
        status_frame = QFrame()
        status_frame.setStyleSheet("background-color: #191919; border-top: 1px solid #2A2A2A;")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(14, 4, 14, 4)
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        status_layout.addWidget(self.status_lbl)
        root_layout.addWidget(status_frame)

        self._render_sidebar()
        self.sync_ui_from_active_tab()

    def _build_new_menu(self, parent):
        menu = QMenu(parent)

        act_folder = menu.addAction(self.base_folder_icon, "Folder")
        act_folder.triggered.connect(self.create_new_folder)

        act_shortcut = menu.addAction(self.get_ext_icon(".lnk", "#2563EB", "↗"), "Shortcut")
        act_shortcut.triggered.connect(self.create_new_shortcut)

        menu.addSeparator()

        items = [
            (".accdb", "Microsoft Access Database", "New Microsoft Access Database.accdb", "#A4373A", "A"),
            (".bmp", "Bitmap image", "New Bitmap image.bmp", "#0EA5E9", "BMP"),
            (".docx", "Microsoft Word Document", "New Microsoft Word Document.docx", "#2B579A", "W"),
            (".gdoc", "Google Docs", "New Google Doc.gdoc", "#4285F4", "≡"),
            (".gsheet", "Google Sheets", "New Google Sheet.gsheet", "#0F9D58", "⊞"),
            (".gslides", "Google Slides", "New Google Slides.gslides", "#F4B400", "▢"),
            (".pptx", "Microsoft PowerPoint Presentation", "New Microsoft PowerPoint Presentation.pptx", "#D24726", "P"),
            (".pub", "Microsoft Publisher Document", "New Microsoft Publisher Document.pub", "#077568", "Pub"),
            (".py", "Python Source File", "New Python Source File.py", "#3776AB", "PY"),
            (".txt", "Text Document", "New Text Document.txt", "#64748B", "TXT"),
            (".xlsx", "Microsoft Excel Worksheet", "New Microsoft Excel Worksheet.xlsx", "#217346", "X"),
            (".zip", "Compressed (zipped) Folder", "New Compressed (zipped) Folder.zip", "#D97706", "ZIP"),
        ]

        for ext, label, default_name, col, badge in items:
            ico = self.get_ext_icon(ext, col, badge)
            act = menu.addAction(ico, label)
            act.triggered.connect(lambda checked=False, e=ext, d=default_name: self.create_new_file(e, d))

        menu.addSeparator()
        act_custom = menu.addAction("✨  Custom File...")
        act_custom.triggered.connect(lambda: self.create_new_file("", ""))
        return menu

    def _make_vsep(self):
        sep = QFrame()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet("background-color: #2E2E2E;")
        return sep

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+T"), self, lambda: self.active_pane.add_tab(self.active_pane.current_root()))
        QShortcut(QKeySequence("Ctrl+W"), self, lambda: self.active_pane.close_tab(self.active_tab))
        QShortcut(QKeySequence("Ctrl+L"), self, self._start_path_edit)
        QShortcut(QKeySequence("Ctrl+A"), self, lambda: self.active_tab.select_all_items() if self.active_tab else None)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo_action)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.redo_action)
        QShortcut(QKeySequence("F6"), self, self.toggle_split_pane)
        QShortcut(QKeySequence("Alt+Left"), self, self.go_back)
        QShortcut(QKeySequence("Alt+Right"), self, self.go_forward)
        QShortcut(QKeySequence("Alt+Up"), self, self.go_up)
        QShortcut(QKeySequence("Alt+Return"), self, self.open_properties)
        QShortcut(QKeySequence("Alt+Shift+P"), self, self.toggle_details_pane)
        QShortcut(QKeySequence("Ctrl+C"), self, lambda: self.copy_cut_selected("copy"))
        QShortcut(QKeySequence("Ctrl+X"), self, lambda: self.copy_cut_selected("cut"))
        QShortcut(QKeySequence("Ctrl+V"), self, self.paste_items)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, self.create_new_folder)
        QShortcut(QKeySequence("F5"), self, self.refresh_all_panes)

    # --- Undo / Redo Engine ---
    def record_undo(self, action_dict):
        self.undo_stack.append(action_dict)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo_action(self):
        if not self.undo_stack:
            self.status_lbl.setText("Nothing to undo")
            return
        act = self.undo_stack.pop()
        op = act.get("op")
        try:
            if op == "move":
                for src, dst in reversed(act["pairs"]):
                    if os.path.exists(dst):
                        os.makedirs(os.path.dirname(src), exist_ok=True)
                        shutil.move(dst, src)
                self.redo_stack.append(act)
                self.status_lbl.setText("Undid move")
            elif op == "copy":
                for _, dst in reversed(act["pairs"]):
                    if os.path.exists(dst):
                        if os.path.isdir(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                self.redo_stack.append(act)
                self.status_lbl.setText("Undid copy")
            elif op == "rename":
                if os.path.exists(act["new"]):
                    os.rename(act["new"], act["old"])
                self.redo_stack.append(act)
                self.status_lbl.setText(f"Undid rename → {os.path.basename(act['old'])}")
            elif op == "create":
                p = act["path"]
                if os.path.exists(p):
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                self.status_lbl.setText(f"Undid create {os.path.basename(p)}")
        except Exception as e:
            QMessageBox.warning(self, "Undo Error", str(e))
        self.refresh_all_panes()

    def redo_action(self):
        if not self.redo_stack:
            self.status_lbl.setText("Nothing to redo")
            return
        act = self.redo_stack.pop()
        op = act.get("op")
        try:
            if op == "move":
                for src, dst in act["pairs"]:
                    if os.path.exists(src):
                        shutil.move(src, dst)
                self.undo_stack.append(act)
                self.status_lbl.setText("Redid move")
            elif op == "copy":
                for src, dst in act["pairs"]:
                    if os.path.exists(src):
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                self.undo_stack.append(act)
                self.status_lbl.setText("Redid copy")
            elif op == "rename":
                if os.path.exists(act["old"]):
                    os.rename(act["old"], act["new"])
                self.undo_stack.append(act)
                self.status_lbl.setText(f"Redid rename → {os.path.basename(act['new'])}")
        except Exception as e:
            QMessageBox.warning(self, "Redo Error", str(e))
        self.refresh_all_panes()

    # --- Frameless Window Resizing & Overflow Toolbar ---
    def _qt_edges_at_global(self, global_pos):
        if self.isMaximized() or not self.isVisible():
            return Qt.Edges()
        g = self.frameGeometry()
        if not g.adjusted(-2, -2, 2, 2).contains(global_pos):
            return Qt.Edges()
        m = 8
        edges = Qt.Edges()
        if global_pos.x() - g.left() < m:
            edges |= Qt.LeftEdge
        elif g.right() - global_pos.x() < m:
            edges |= Qt.RightEdge
        if global_pos.y() - g.top() < m:
            edges |= Qt.TopEdge
        elif g.bottom() - global_pos.y() < m:
            edges |= Qt.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.MouseMove:
            if not (event.buttons() & Qt.LeftButton):
                edges = self._qt_edges_at_global(event.globalPosition().toPoint())
                if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
                    if not self._override_cursor_active:
                        QApplication.setOverrideCursor(Qt.SizeFDiagCursor)
                        self._override_cursor_active = True
                    else:
                        QApplication.changeOverrideCursor(Qt.SizeFDiagCursor)
                elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
                    if not self._override_cursor_active:
                        QApplication.setOverrideCursor(Qt.SizeBDiagCursor)
                        self._override_cursor_active = True
                    else:
                        QApplication.changeOverrideCursor(Qt.SizeBDiagCursor)
                elif edges in (Qt.LeftEdge, Qt.RightEdge):
                    if not self._override_cursor_active:
                        QApplication.setOverrideCursor(Qt.SizeHorCursor)
                        self._override_cursor_active = True
                    else:
                        QApplication.changeOverrideCursor(Qt.SizeHorCursor)
                elif edges in (Qt.TopEdge, Qt.BottomEdge):
                    if not self._override_cursor_active:
                        QApplication.setOverrideCursor(Qt.SizeVerCursor)
                        self._override_cursor_active = True
                    else:
                        QApplication.changeOverrideCursor(Qt.SizeVerCursor)
                else:
                    if self._override_cursor_active:
                        QApplication.restoreOverrideCursor()
                        self._override_cursor_active = False
        elif etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            edges = self._qt_edges_at_global(event.globalPosition().toPoint())
            if edges and self.windowHandle():
                if self._override_cursor_active:
                    QApplication.restoreOverrideCursor()
                    self._override_cursor_active = False
                self.windowHandle().startSystemResize(edges)
                return True
        elif etype == QEvent.Leave:
            if obj is self and self._override_cursor_active:
                QApplication.restoreOverrideCursor()
                self._override_cursor_active = False
        return super().eventFilter(obj, event)

    def _update_command_bar_overflow(self):
        if not hasattr(self, "overflow_buttons") or not hasattr(self, "more_btn"):
            return

        w = self.width()
        if w < 560:
            self.sort_btn.setText("")
            self.view_btn.setText("")
            self.split_btn.setText("")
            self.details_btn.setText("")
        else:
            self.sort_btn.setText("  Sort  ▾")
            self.view_btn.setText("  View  ▾")
            self.split_btn.setText("  Split")
            self.details_btn.setText("  Details")

        core_used = 540 if w >= 560 else 370
        available = max(0, w - core_used)

        used = 0
        overflow_items = []
        for btn, icon_kind, label, fn in self.overflow_buttons:
            needed = btn.sizeHint().width() + 6
            if used + needed <= available:
                btn.setVisible(True)
                used += needed
            else:
                btn.setVisible(False)
                overflow_items.append((icon_kind, label, fn))

        # Build "•••" menu: Browse, Select all, Invert live ONLY inside "•••" per user screenshot!
        self.more_menu.clear()
        act_browse = self.more_menu.addAction(make_fluent_icon("browse", "#CCCCCC", size=15), "Browse")
        act_browse.triggered.connect(self.pick_folder)

        act_sel_all = self.more_menu.addAction(make_fluent_icon("select_all", "#CCCCCC", size=15), "Select all")
        act_sel_all.triggered.connect(lambda: self.active_tab.select_all_items() if self.active_tab else None)

        act_invert = self.more_menu.addAction(make_fluent_icon("invert", "#CCCCCC", size=15), "Invert")
        act_invert.triggered.connect(lambda: self.active_tab.invert_selection() if self.active_tab else None)

        self.more_menu.addSeparator()
        act_undo = self.more_menu.addAction(make_fluent_icon("undo", "#CCCCCC", size=15), "Undo  (Ctrl+Z)")
        act_undo.triggered.connect(self.undo_action)

        act_redo = self.more_menu.addAction(make_fluent_icon("redo", "#CCCCCC", size=15), "Redo  (Ctrl+Y)")
        act_redo.triggered.connect(self.redo_action)

        if overflow_items:
            self.more_menu.addSeparator()
            for icon_kind, label, fn in overflow_items:
                act = self.more_menu.addAction(make_fluent_icon(icon_kind, "#CCCCCC", size=15), label)
                act.triggered.connect(fn)

        self.more_btn.setVisible(True)

    def nativeEvent(self, eventType, message):
        """Handle Windows WM_NCCALCSIZE & WM_NCHITTEST for native Aero Snap, Snap Layouts, and edge resizing."""
        if os.name == "nt" and eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                WM_NCCALCSIZE = 0x0083
                WM_NCHITTEST = 0x0084
                WM_GETMINMAXINFO = 0x0024

                if msg.message == WM_NCCALCSIZE and msg.wParam:
                    # Remove the standard top/side non-client titlebar frame while keeping WS_THICKFRAME snap behavior
                    params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
                    if self.isMaximized():
                        # Prevent maximized window from spilling off-screen into taskbar
                        user32 = ctypes.windll.user32
                        MONITOR_DEFAULTTONEAREST = 2
                        hmon = user32.MonitorFromWindow(int(self.winId()), MONITOR_DEFAULTTONEAREST)
                        class MONITORINFO(ctypes.Structure):
                            _fields_ = [
                                ("cbSize", wintypes.DWORD),
                                ("rcMonitor", wintypes.RECT),
                                ("rcWork", wintypes.RECT),
                                ("dwFlags", wintypes.DWORD),
                            ]
                        mi = MONITORINFO()
                        mi.cbSize = ctypes.sizeof(MONITORINFO)
                        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                            params.rgrc[0] = mi.rcWork
                    return True, 0

                elif msg.message == WM_GETMINMAXINFO:
                    mmi = MINMAXINFO.from_address(msg.lParam)
                    dpr = self.devicePixelRatioF()
                    mmi.ptMinTrackSize.x = int(self.minimumWidth() * dpr)
                    mmi.ptMinTrackSize.y = int(self.minimumHeight() * dpr)
                    return True, 0

                elif msg.message == WM_NCHITTEST:
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    dpr = self.devicePixelRatioF()
                    local_pos = self.mapFromGlobal(QPoint(int(x / dpr), int(y / dpr)))
                    lx, ly = local_pos.x(), local_pos.y()
                    w, h = self.width(), self.height()

                    # 1. Resize borders/corners when not maximized
                    if not self.isMaximized():
                        m = 7
                        left = lx < m
                        right = lx >= w - m
                        top = ly < m
                        bottom = ly >= h - m
                        if top and left:
                            return True, 13    # HTTOPLEFT
                        if top and right:
                            return True, 14    # HTTOPRIGHT
                        if bottom and left:
                            return True, 16    # HTBOTTOMLEFT
                        if bottom and right:
                            return True, 17    # HTBOTTOMRIGHT
                        if left:
                            return True, 10    # HTLEFT
                        if right:
                            return True, 11    # HTRIGHT
                        if top:
                            return True, 12    # HTTOP
                        if bottom:
                            return True, 15    # HTBOTTOM

                    # 2. Check caption buttons so Windows 11 Snap Layouts flyout triggers on Maximize hover!
                    if hasattr(self, "max_btn") and self.max_btn.isVisible():
                        max_rect = QRect(self.max_btn.mapTo(self, QPoint(0, 0)), self.max_btn.size())
                        if max_rect.contains(local_pos):
                            return True, 9     # HTMAXBUTTON

                    # 3. Empty draggable tab-bar spacer -> HTCAPTION (triggers native Windows Aero Snap!)
                    if hasattr(self, "drag_spacer") and self.drag_spacer.isVisible():
                        spacer_rect = QRect(self.drag_spacer.mapTo(self, QPoint(0, 0)), self.drag_spacer.size())
                        if spacer_rect.contains(local_pos):
                            return True, 2     # HTCAPTION
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, "max_btn"):
            if self.isMaximized():
                self.max_btn.setIcon(make_fluent_icon("win_restore", "#CCCCCC", size=14))
                self.max_btn.setToolTip("Restore Down")
            else:
                self.max_btn.setIcon(make_fluent_icon("win_max", "#CCCCCC", size=14))
                self.max_btn.setToolTip("Maximize")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_command_bar_overflow()

    def _toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setIcon(make_fluent_icon("win_max", "#CCCCCC", size=14))
            self.max_btn.setToolTip("Maximize")
        else:
            self.showMaximized()
            self.max_btn.setIcon(make_fluent_icon("win_restore", "#CCCCCC", size=14))
            self.max_btn.setToolTip("Restore Down")

    def _on_titlebar_press(self, event):
        if event.button() == Qt.LeftButton:
            if self.windowHandle() and self.windowHandle().startSystemMove():
                return
            self._drag_win_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _on_titlebar_move(self, event):
        if (event.buttons() & Qt.LeftButton) and self._drag_win_offset is not None:
            if self.isMaximized():
                ratio = event.position().x() / max(1, self.width())
                self.showNormal()
                self.max_btn.setIcon(make_fluent_icon("win_max", "#CCCCCC", size=14))
                self._drag_win_offset = QPoint(int(self.width() * ratio), 18)
            self.move(event.globalPosition().toPoint() - self._drag_win_offset)

    def _on_titlebar_release(self, event):
        self._drag_win_offset = None

    # --- Search, Kind Filter, Views, Split Dual-Pane & Details Pane ---
    def _on_kind_filter_changed(self, text):
        self.kind_filter = text
        self.refresh_all_panes()

    def _toggle_search_subfolders(self):
        self.search_subfolders = not self.search_subfolders
        self.subfolders_btn.setObjectName("CmdBtnActive" if self.search_subfolders else "CmdBtn")
        self.subfolders_btn.style().unpolish(self.subfolders_btn)
        self.subfolders_btn.style().polish(self.subfolders_btn)
        self.refresh_all_panes()

    def set_view_mode(self, mode):
        self.view_mode = mode
        if mode in self.view_actions:
            self.view_actions[mode].setChecked(True)
        for pane in (self.primary_pane, self.secondary_pane):
            for tab in pane.tabs:
                tab.apply_view_mode(mode, reload=True)
        self.status_lbl.setText(f"View: {mode}")

    def cycle_view_mode(self, step):
        idx = VIEW_MODES.index(self.view_mode)
        new_idx = max(0, min(len(VIEW_MODES) - 1, idx + step))
        if new_idx != idx:
            self.set_view_mode(VIEW_MODES[new_idx])

    def toggle_split_pane(self):
        self.split_pane_visible = not self.split_pane_visible
        self.secondary_pane.setVisible(self.split_pane_visible)
        self.split_pane_act.setChecked(self.split_pane_visible)
        self.split_btn.setObjectName("CmdBtnActive" if self.split_pane_visible else "CmdBtn")
        self.split_btn.style().unpolish(self.split_btn)
        self.split_btn.style().polish(self.split_btn)

        if self.split_pane_visible:
            # Open secondary pane at the same folder as primary pane if uninitialized
            self.secondary_pane.navigate_to(self.primary_pane.current_root())
            self.set_active_pane(self.secondary_pane)
        else:
            self.set_active_pane(self.primary_pane)

        self.primary_pane.set_focused_visual(self.active_pane is self.primary_pane, self.split_pane_visible)
        self.secondary_pane.set_focused_visual(self.active_pane is self.secondary_pane, self.split_pane_visible)

    def toggle_details_pane(self):
        self.details_pane_visible = not self.details_pane_visible
        self.details_pane.setVisible(self.details_pane_visible)
        self.details_pane_act.setChecked(self.details_pane_visible)
        self.details_btn.setObjectName("CmdBtnActive" if self.details_pane_visible else "CmdBtn")
        self.details_btn.style().unpolish(self.details_btn)
        self.details_btn.style().polish(self.details_btn)
        if self.details_pane_visible:
            sizes = self.main_splitter.sizes()
            if len(sizes) >= 4 and sizes[3] < 220:
                total = sum(sizes)
                target_w = 340
                sizes[1] = max(250, sizes[1] - target_w)
                sizes[3] = target_w
                self.main_splitter.setSizes(sizes)
            self._update_details_pane()
        else:
            self.details_pane._stop_audio()

    def _update_details_pane(self):
        if not self.details_pane_visible or not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        self.details_pane.show_item(paths[0] if paths else self.active_tab.current_root)

    def _toggle_hidden(self, checked):
        self.show_hidden = checked
        self.refresh_all_panes()

    def _toggle_extensions(self, checked):
        self.show_extensions = checked
        self.refresh_all_panes()

    def _toggle_checkboxes(self, checked):
        self.show_checkboxes = checked
        self.refresh_all_panes()

    def _toggle_calc_folder_sizes(self, checked):
        self.calc_folder_sizes = checked
        self.refresh_all_panes()

    # --- Sidebar Rendering ---
    def _render_sidebar(self):
        while self.sidebar_layout.count():
            child = self.sidebar_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        home = os.path.expanduser("~")
        home_icon = self.icon_provider.icon(QFileIconProvider.Desktop)
        self.sidebar_layout.addWidget(SidebarItemWidget(self, "Home", home, home_icon, pinned=False))

        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background-color: #2A2A2A; margin: 6px 8px;")
        self.sidebar_layout.addWidget(sep1)

        for p in self.pinned_folders:
            if os.path.isdir(p):
                name = os.path.basename(p.rstrip("\\/")) or p
                icon = self.get_folder_icon(p, None)
                self.sidebar_layout.addWidget(SidebarItemWidget(self, name, p, icon, pinned=True))

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: #2A2A2A; margin: 6px 8px;")
        self.sidebar_layout.addWidget(sep2)

        # Recycle Bin shortcut in sidebar
        rb_icon = make_fluent_icon("recycle", "#60CDFF", size=16)
        self.sidebar_layout.addWidget(
            SidebarItemWidget(self, "Recycle Bin", "shell:RecycleBinFolder", rb_icon, pinned=False, is_recycle_bin=True)
        )

        sep3 = QFrame()
        sep3.setFixedHeight(1)
        sep3.setStyleSheet("background-color: #2A2A2A; margin: 6px 8px;")
        self.sidebar_layout.addWidget(sep3)

        pc_lbl = QLabel("This PC")
        pc_lbl.setStyleSheet("color: #8E8E8E; font-size: 11px; font-weight: 600; padding: 2px 10px;")
        self.sidebar_layout.addWidget(pc_lbl)

        drive_icon = self.icon_provider.icon(QFileIconProvider.Drive)
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    self.sidebar_layout.addWidget(
                        SidebarItemWidget(self, f"Local Disk ({letter}:)", drive, drive_icon, pinned=False)
                    )
        else:
            self.sidebar_layout.addWidget(SidebarItemWidget(self, "Root (/)", "/", drive_icon, pinned=False))

        self.sidebar_layout.addStretch(1)

    def open_recycle_bin(self):
        if os.name == "nt":
            try:
                os.startfile("shell:RecycleBinFolder")
            except Exception:
                subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])

    def empty_recycle_bin_action(self):
        ans = QMessageBox.question(
            self,
            "Empty Recycle Bin",
            "Are you sure you want to permanently delete all items in the Recycle Bin?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            empty_windows_recycle_bin(self)
            self.status_lbl.setText("Recycle Bin emptied")

    # --- Primary Tab Strip & Breadcrumbs ---
    def add_tab(self, path):
        self.active_pane.add_tab(path)

    def _render_tab_bar(self):
        while self.tab_strip_layout.count():
            child = self.tab_strip_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for tab in self.primary_pane.tabs:
            is_active = tab is self.primary_pane.active_tab
            pill = QFrame()
            bg = "#1F1F1F" if is_active else "#0C0C0C"
            fg = "#FFFFFF" if is_active else "#A0A0A0"
            pill.setStyleSheet(
                f"QFrame {{ background-color: {bg}; border-top-left-radius: 7px; border-top-right-radius: 7px; }}"
            )
            pill.setToolTip(tab.current_root)
            hl = QHBoxLayout(pill)
            hl.setContentsMargins(10, 4, 8, 4)
            hl.setSpacing(6)

            ico = QLabel()
            ico.setPixmap(self.base_folder_icon.pixmap(15, 15))
            ico.setStyleSheet("background: transparent;")
            hl.addWidget(ico)

            title = tab.tab_title()
            if len(title) > 22:
                title = title[:21] + "…"
            lbl = QLabel(title)
            lbl.setStyleSheet(f"color: {fg}; font-size: 12px; background: transparent;")
            lbl.setCursor(Qt.PointingHandCursor)
            hl.addWidget(lbl)

            pill.mousePressEvent = lambda e, t=tab: (
                self.set_active_pane(self.primary_pane),
                self.primary_pane.switch_tab(t),
            )

            if len(self.primary_pane.tabs) > 1:
                xbtn = QPushButton("✕")
                xbtn.setFixedSize(18, 18)
                xbtn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; color: #8E8E8E; font-size: 10px; border-radius: 3px; }"
                    "QPushButton:hover { background: #383838; color: #FFFFFF; }"
                )
                xbtn.clicked.connect(lambda checked=False, t=tab: self.primary_pane.close_tab(t))
                hl.addWidget(xbtn)

            self.tab_strip_layout.addWidget(pill)

    def _render_breadcrumbs(self):
        while self.crumb_layout.count():
            child = self.crumb_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        if not self.primary_pane.active_tab:
            return

        path = self.primary_pane.active_tab.current_root
        parts = []
        curr = path
        while True:
            head, tail = os.path.split(curr)
            if tail:
                parts.append((tail, curr))
                curr = head
            else:
                if head:
                    parts.append((head, head))
                break
        parts.reverse()

        for i, (label, full_p) in enumerate(parts):
            if i > 0:
                sep = QLabel("›")
                sep.setStyleSheet("color: #777777; background: transparent;")
                self.crumb_layout.addWidget(sep)
            self.crumb_layout.addWidget(DroppableCrumbButton(self, label, full_p, self.primary_pane))
        self.crumb_layout.addStretch(1)

    def _start_path_edit(self):
        if self.active_pane is self.secondary_pane and self.split_pane_visible:
            self.secondary_pane.start_path_edit()
            return
        if not self.primary_pane.active_tab or self.editing_path:
            return
        self.editing_path = True
        self.crumb_container.hide()
        self.path_edit.setText(self.primary_pane.active_tab.current_root)
        self.path_edit.show()
        self.path_edit.setFocus()
        self.path_edit.selectAll()

    def _commit_path_edit(self):
        new_path = self.path_edit.text().strip()
        self._cancel_path_edit()
        if new_path:
            self.primary_pane.navigate_to(new_path)

    def _cancel_path_edit(self):
        if not self.editing_path:
            return
        self.editing_path = False
        self.path_edit.hide()
        self.crumb_container.show()

    def sync_ui_from_active_tab(self):
        self._render_tab_bar()
        self._render_breadcrumbs()
        if self.primary_pane.active_tab:
            self.back_btn.setEnabled(self.primary_pane.active_tab.can_go_back())
            self.fwd_btn.setEnabled(self.primary_pane.active_tab.can_go_forward())
        self.on_selection_changed()

    def on_selection_changed(self):
        self.update_status()
        self._update_details_pane()

    # --- Actions ---
    def navigate_to(self, path):
        self.active_pane.navigate_to(path)

    def go_back(self):
        self.active_pane.go_back()

    def go_forward(self):
        self.active_pane.go_forward()

    def go_up(self):
        self.active_pane.go_up()

    def pick_folder(self):
        start = self.active_pane.current_root()
        chosen = QFileDialog.getExistingDirectory(self, "Select Folder", start)
        if chosen:
            self.active_pane.navigate_to(chosen)

    def refresh(self):
        self.active_pane.refresh()

    def refresh_all_panes(self):
        self.primary_pane.refresh()
        if self.split_pane_visible:
            self.secondary_pane.refresh()

    def collapse_all(self):
        if self.active_tab:
            self.active_tab.collapse_all()

    def open_in_terminal(self):
        target = os.path.normpath(self._target_dir_for_creation())
        if not os.path.isdir(target):
            target = os.path.expanduser("~")
        if os.name == "nt":
            wt_path = shutil.which("wt.exe")
            if wt_path:
                try:
                    subprocess.Popen(
                        [wt_path, "-d", target],
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                    self.status_lbl.setText(f"Opened Terminal at {target}")
                    return
                except Exception:
                    pass
            try:
                subprocess.Popen(
                    ["cmd.exe", "/k", "cd", "/d", target],
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                self.status_lbl.setText(f"Opened Command Prompt at {target}")
            except Exception as e:
                QMessageBox.warning(self, "Terminal Error", f"Could not launch terminal:\n{e}")

    def open_properties(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths else self.active_tab.current_root
        show_windows_properties(target)

    def extract_zip_file(self, zip_path, to_subfolder=False):
        if not os.path.isfile(zip_path):
            return
        parent_dir = os.path.dirname(zip_path)
        if to_subfolder:
            stem = os.path.splitext(os.path.basename(zip_path))[0]
            dest_dir = os.path.join(parent_dir, stem)
            os.makedirs(dest_dir, exist_ok=True)
        else:
            dest_dir = parent_dir

        dest_abs = os.path.abspath(dest_dir)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    target_path = os.path.abspath(os.path.join(dest_abs, member.filename))
                    if os.path.commonpath([dest_abs, target_path]) != dest_abs:
                        raise RuntimeError(f"Blocked unsafe zip path: {member.filename}")
                zf.extractall(dest_abs)
            self.refresh_all_panes()
            if to_subfolder:
                self.refresh_and_select(dest_abs)
            self.status_lbl.setText(f"Extracted {os.path.basename(zip_path)} → {dest_abs}")
        except Exception as e:
            QMessageBox.warning(self, "Extract Error", f"Failed to extract archive:\n{e}")

    def show_context_menu(self, global_pos):
        menu = QMenu(self)
        menu.addAction("Open", self.open_selected)
        menu.addAction("Open in New Tab", self.open_in_new_tab)
        if self.split_pane_visible:
            other = self.secondary_pane if self.active_pane is self.primary_pane else self.primary_pane
            menu.addAction("Open in Other Split Pane", lambda: self._open_in_other_pane(other))
        menu.addAction("📌  Pin to Left Sidebar", self.pin_selected_folder)

        selected_dirs = [p for p in (self.active_tab.selected_paths() if self.active_tab else []) if os.path.isdir(p)]
        if selected_dirs:
            color_menu = menu.addMenu("🎨  Folder Color")
            cur_norm = os.path.normcase(os.path.abspath(selected_dirs[0]))
            active_hex = self.folder_colors.get(cur_norm)
            for label, hex_val in FOLDER_COLOR_PRESETS:
                if hex_val is None:
                    act = color_menu.addAction(self.base_folder_icon, label)
                else:
                    act = color_menu.addAction(make_color_swatch_icon(hex_val), label)
                act.setCheckable(True)
                act.setChecked(active_hex == hex_val)
                act.triggered.connect(lambda checked=False, h=hex_val, dirs=list(selected_dirs): self.set_folder_color(dirs, h))
            color_menu.addSeparator()
            custom_act = color_menu.addAction("✨  Custom Color...")
            custom_act.triggered.connect(lambda checked=False, dirs=list(selected_dirs): self.pick_custom_folder_color(dirs))
        menu.addAction("Reveal in Windows Explorer", self.reveal_in_explorer)

        paths = self.active_tab.selected_paths() if self.active_tab else []
        if len(paths) == 1 and paths[0].lower().endswith(".zip") and os.path.isfile(paths[0]):
            zp = paths[0]
            stem = os.path.splitext(os.path.basename(zp))[0]
            menu.addSeparator()
            menu.addAction("📦  Extract All Here", lambda p=zp: self.extract_zip_file(p, to_subfolder=False))
            menu.addAction(f'📦  Extract to "{stem}\\"', lambda p=zp: self.extract_zip_file(p, to_subfolder=True))

        menu.addSeparator()
        new_sub = menu.addMenu("⊕  New")
        for act in self._build_new_menu(new_sub).actions():
            new_sub.addAction(act)
        menu.addSeparator()
        menu.addAction("Cut  (Ctrl+X)", lambda: self.copy_cut_selected("cut"))
        menu.addAction("Copy  (Ctrl+C)", lambda: self.copy_cut_selected("copy"))
        menu.addAction("Paste  (Ctrl+V)", self.paste_items)
        menu.addSeparator()
        menu.addAction("Rename  (F2)", self.rename_selected)
        menu.addAction("Delete  (Del)", lambda: self.delete_selected(False))
        menu.addSeparator()
        menu.addAction("Copy Full Path", self.copy_path)
        menu.addAction("Properties  (Alt+Enter)", self.open_properties)
        menu.exec(global_pos)

    def _open_in_other_pane(self, other_pane):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths and os.path.isdir(paths[0]) else self.active_tab.current_root
        other_pane.navigate_to(target)

    def open_selected(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        if not paths:
            return
        p = paths[0]
        if os.path.isdir(p):
            self.active_tab.load_directory(p, push_history=True)
        else:
            self.launch_file(p)

    def open_in_new_tab(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths and os.path.isdir(paths[0]) else self.active_tab.current_root
        self.active_pane.add_tab(target)

    def pin_selected_folder(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths and os.path.isdir(paths[0]) else self.active_tab.current_root
        self.pin_folder(target)

    def reveal_in_explorer(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths else self.active_tab.current_root
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])

    def copy_path(self):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        target = paths[0] if paths else self.active_tab.current_root
        QApplication.clipboard().setText(target)
        self.status_lbl.setText(f"Copied path: {target}")

    def copy_cut_selected(self, mode):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        if not paths:
            return
        self.clipboard_paths = paths
        self.clipboard_mode = mode
        verb = "Copied" if mode == "copy" else "Cut"
        self.status_lbl.setText(f"{verb} {len(paths)} item(s)")

    def paste_items(self):
        if not self.active_tab or not self.clipboard_paths:
            return
        sel = self.active_tab.selected_paths()
        dest_dir = sel[0] if sel and os.path.isdir(sel[0]) else self.active_tab.current_root
        copy_mode = self.clipboard_mode == "copy"
        changed = transfer_items(
            self.clipboard_paths, dest_dir, copy_mode=copy_mode, parent_widget=self, record_undo_cb=self.record_undo
        )
        if not copy_mode:
            self.clipboard_paths = []
            self.clipboard_mode = None
        if changed:
            self.refresh_all_panes()

    def refresh_and_select(self, target_path):
        self.refresh_all_panes()
        if not self.active_tab or not target_path:
            return
        norm_target = os.path.normcase(os.path.abspath(target_path))
        if self.view_mode == "Details":
            tree = self.active_tab.tree
            def find_and_select(parent):
                count = tree.topLevelItemCount() if parent is None else parent.childCount()
                for i in range(count):
                    it = tree.topLevelItem(i) if parent is None else parent.child(i)
                    p = it.data(0, ROLE_PATH)
                    if p and os.path.normcase(os.path.abspath(p)) == norm_target:
                        tree.clearSelection()
                        it.setSelected(True)
                        tree.setCurrentItem(it)
                        tree.scrollToItem(it)
                        return True
                    if it.isExpanded() and find_and_select(it):
                        return True
                return False
            find_and_select(None)
        else:
            lst = self.active_tab.icon_list
            for i in range(lst.count()):
                it = lst.item(i)
                p = it.data(ROLE_PATH)
                if p and os.path.normcase(os.path.abspath(p)) == norm_target:
                    lst.clearSelection()
                    it.setSelected(True)
                    lst.setCurrentItem(it)
                    lst.scrollToItem(it)
                    break

    def rename_selected(self):
        if not self.active_tab:
            return
        if self.view_mode == "Details":
            self.active_tab.tree.start_inline_rename()
        else:
            self.active_tab.icon_list.start_inline_rename()

    def delete_selected(self, permanent=False):
        if not self.active_tab:
            return
        paths = self.active_tab.selected_paths()
        if not paths:
            return
        if permanent:
            ans = QMessageBox.question(
                self,
                "Permanently Delete",
                f"Permanently delete {len(paths)} item(s) without Recycle Bin?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return
            for p in paths:
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                except Exception as e:
                    QMessageBox.warning(self, "Delete Error", f"Could not delete {p}:\n{e}")
        else:
            if not send_to_recycle_bin(paths):
                QMessageBox.warning(self, "Recycle Bin Error", "Could not move one or more items to Recycle Bin.")
            else:
                self.status_lbl.setText(f"Moved {len(paths)} item(s) to Recycle Bin")
        self.refresh_all_panes()

    def _target_dir_for_creation(self):
        if not self.active_tab:
            return os.path.expanduser("~")
        paths = self.active_tab.selected_paths()
        if paths and os.path.isdir(paths[0]):
            return paths[0]
        return self.active_tab.current_root

    def create_new_folder(self):
        target_dir = self._target_dir_for_creation()
        name, ok = QInputDialog.getText(
            self, "New Folder", f"Folder name (in {os.path.basename(target_dir) or target_dir}):"
        )
        if ok and name.strip():
            new_dir = os.path.join(target_dir, name.strip())
            try:
                os.makedirs(new_dir, exist_ok=True)
                self.record_undo({"op": "create", "path": new_dir})
                self.refresh_and_select(new_dir)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def create_new_shortcut(self):
        target_dir = self._target_dir_for_creation()
        target_item, ok = QInputDialog.getText(
            self, "Create Shortcut", "Type the location of the item (file path, folder path, or URL):"
        )
        if not ok or not target_item.strip():
            return
        target_item = target_item.strip().strip('"')
        default_lnk = (os.path.basename(target_item.rstrip("\\/")) or "Shortcut") + ".lnk"
        lnk_name, ok2 = QInputDialog.getText(self, "Shortcut Name", "Type a name for this shortcut:", text=default_lnk)
        if not ok2 or not lnk_name.strip():
            return
        lnk_file = lnk_name.strip()
        if not lnk_file.lower().endswith(".lnk"):
            lnk_file += ".lnk"
        lnk_path = os.path.join(target_dir, lnk_file)

        if os.name == "nt":
            ps_cmd = (
                f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{lnk_path}");'
                f'$s.TargetPath="{target_item}";$s.Save()'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=0x08000000)
            self.record_undo({"op": "create", "path": lnk_path})
            self.refresh_and_select(lnk_path)

    def create_new_file(self, default_ext, default_name):
        target_dir = self._target_dir_for_creation()
        name, ok = QInputDialog.getText(
            self,
            "New File",
            f"File name (in {os.path.basename(target_dir) or target_dir}):",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        fname = name.strip()
        if default_ext and "." not in fname:
            fname += default_ext
        full_path = os.path.join(target_dir, fname)
        if os.path.exists(full_path):
            QMessageBox.warning(self, "File Exists", f"A file named '{fname}' already exists.")
            return

        try:
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".zip":
                with zipfile.ZipFile(full_path, "w", zipfile.ZIP_DEFLATED):
                    pass
            elif ext == ".bmp":
                bmp_bytes = (
                    b"BM\x3a\x00\x00\x00\x00\x00\x00\x00\x36\x00\x00\x00"
                    b"\x28\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00"
                    b"\x01\x00\x18\x00\x00\x00\x00\x00\x04\x00\x00\x00"
                    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
                    b"\xff\xff\xff\x00"
                )
                with open(full_path, "wb") as f:
                    f.write(bmp_bytes)
            else:
                with open(full_path, "w", encoding="utf-8") as f:
                    if ext == ".json":
                        f.write("{}\n")
                    elif ext in (".html", ".htm"):
                        f.write("<!DOCTYPE html>\n<html>\n<head><title>New Page</title></head>\n<body>\n</body>\n</html>\n")
                    elif ext == ".py":
                        f.write("# New Python Script\n")

            self.record_undo({"op": "create", "path": full_path})
            self.refresh_and_select(full_path)
            self.status_lbl.setText(f"Created: {full_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error Creating File", str(e))

    def update_status(self):
        if not self.active_tab:
            return
        total = self.active_tab.total_top_count()
        sel = self.active_tab.selected_paths()
        if sel:
            self.status_lbl.setText(f"{total} items   |   {len(sel)} selected   |   {sel[0]}")
        else:
            self.status_lbl.setText(f"{total} items")

    def launch_file(self, path):
        try:
            if os.name == "nt":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Cannot Open File", str(e))

    def format_size(self, num_bytes):
        if num_bytes == 0:
            return "0 KB"
        kb = max(1, (num_bytes + 1023) // 1024)
        return f"{kb:,} KB"

    def is_hidden(self, path, name):
        if name.startswith("."):
            return True
        if os.name == "nt":
            try:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
                if attrs != -1 and (attrs & 2):
                    return True
            except Exception:
                pass
        return False


if __name__ == "__main__":
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AccordionExplorer.App.1")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QFileIconProvider().icon(QFileIconProvider.Folder))
    window = Win11AccordionExplorer()
    window.show()
    sys.exit(app.exec())
