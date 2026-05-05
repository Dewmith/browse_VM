import json
import os
import stat
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import paramiko
from PySide6.QtCore import QByteArray, QBuffer, QSize, Qt
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
HOME_ROOT = "/data/home"
APP_TITLE = "Lab File Browser"
ALLOWED_EXT_TEXT = {
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".py",
    ".m",
    ".sh",
    ".md",
    ".ini",
    ".cfg",
    ".tsv",
}
ALLOWED_EXT_IMAGE = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}
ALLOWED_EXT_PDF = {".pdf"}
MAX_TEXT_PREVIEW_BYTES = 256 * 1024
MAX_IMAGE_PREVIEW_BYTES = 8 * 1024 * 1024
MAX_PDF_PREVIEW_BYTES = 12 * 1024 * 1024


def load_connection_settings() -> tuple[str, int]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing configuration file: {CONFIG_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in configuration file: {CONFIG_PATH}") from exc

    host = str(config.get("host", "")).strip()
    port = int(config.get("port"))

    if not host:
        raise RuntimeError("Configuration error: 'host' must be set in credentials.json.")
    if not isinstance(port, int):
        raise RuntimeError("Configuration error: 'port' must be an integer in credentials.json.")

    return host, port


HOST, PORT = load_connection_settings()


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: int


class SFTPClientManager:
    def __init__(self) -> None:
        self.transport: Optional[paramiko.Transport] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.username: Optional[str] = None

    def connect(self, username: str, password: str) -> None:
        self.disconnect()
        self.transport = paramiko.Transport((HOST, PORT))
        self.transport.connect(username=username, password=password)
        self.sftp = paramiko.SFTPClient.from_transport(self.transport)
        self.username = username

    def disconnect(self) -> None:
        try:
            if self.sftp:
                self.sftp.close()
        except Exception:
            pass
        try:
            if self.transport:
                self.transport.close()
        except Exception:
            pass
        self.sftp = None
        self.transport = None
        self.username = None

    def ensure_connected(self) -> paramiko.SFTPClient:
        if self.sftp is None:
            raise RuntimeError("Not connected to the server.")
        return self.sftp

    def get_user_root(self) -> str:
        if not self.username:
            raise RuntimeError("Username not available.")
        return f"{HOME_ROOT}/{self.username}"

    def normalize_dir(self, path: str) -> str:
        return self.ensure_connected().normalize(path)

    def is_allowed_path(self, path: str) -> bool:
        root = self.get_user_root().rstrip("/")
        normalized = self.normalize_dir(path)
        return normalized == root or normalized.startswith(root + "/")

    def safe_path(self, path: str) -> str:
        normalized = self.normalize_dir(path)
        if not self.is_allowed_path(normalized):
            raise PermissionError("Access outside your home folder is not allowed.")
        return normalized

    def list_dir(self, path: str) -> List[RemoteEntry]:
        sftp = self.ensure_connected()
        safe = self.safe_path(path)
        results: List[RemoteEntry] = []
        for item in sftp.listdir_attr(safe):
            full_path = self.join_remote(safe, item.filename)
            results.append(
                RemoteEntry(
                    name=item.filename,
                    path=full_path,
                    is_dir=stat.S_ISDIR(item.st_mode),
                    size=item.st_size,
                    mtime=item.st_mtime,
                )
            )
        results.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        return results

    def read_bytes(self, path: str) -> bytes:
        sftp = self.ensure_connected()
        safe = self.safe_path(path)
        with sftp.open(safe, "rb") as fh:
            return fh.read()

    def read_preview_bytes(self, path: str, max_bytes: int) -> tuple[bytes, bool]:
        sftp = self.ensure_connected()
        safe = self.safe_path(path)
        with sftp.open(safe, "rb") as fh:
            data = fh.read(max_bytes + 1)
        return data[:max_bytes], len(data) > max_bytes

    def download_file(self, remote_path: str, local_path: str) -> None:
        sftp = self.ensure_connected()
        safe = self.safe_path(remote_path)
        sftp.get(safe, local_path)

    @staticmethod
    def join_remote(base: str, name: str) -> str:
        if base == "/":
            return f"/{name}"
        return f"{base.rstrip('/')}/{name}"


class LoginDialog(QDialog):
    def __init__(self, manager: SFTPClientManager) -> None:
        super().__init__()
        self.manager = manager
        self.setWindowTitle(f"{APP_TITLE} - Login")
        self.setMinimumWidth(380)

        self.info_label = QLabel(
            f"Connect to {HOST}:{PORT}\nAccess is limited to your own folder under {HOME_ROOT}."
        )
        self.info_label.setWordWrap(True)

        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.login_button = QPushButton("Login")
        self.cancel_button = QPushButton("Cancel")

        form = QFormLayout()
        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)

        buttons = QHBoxLayout()
        buttons.addWidget(self.login_button)
        buttons.addWidget(self.cancel_button)

        layout = QVBoxLayout()
        layout.addWidget(self.info_label)
        layout.addLayout(form)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self.login_button.clicked.connect(self.handle_login)
        self.cancel_button.clicked.connect(self.reject)
        self.password_edit.returnPressed.connect(self.handle_login)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)

    def handle_login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()

        if not username or not password:
            QMessageBox.warning(self, "Missing fields", "Please enter both username and password.")
            return

        try:
            self.login_button.setEnabled(False)
            self.login_button.setText("Connecting...")
            QApplication.processEvents()
            self.manager.connect(username, password)
            self.manager.safe_path(self.manager.get_user_root())
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Login failed", str(exc))
        finally:
            self.login_button.setEnabled(True)
            self.login_button.setText("Login")


class PreviewPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.title = QLabel("Preview")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.layout.addWidget(self.title)

        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_label = QLabel("Select a file to preview")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setWordWrap(True)
        self.image_label.setMinimumSize(320, 240)
        self.image_scroll.setWidget(self.image_label)
        self.image_scroll.hide()

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.hide()

        self.pdf_doc = None
        self.pdf_view = None
        if PDF_AVAILABLE:
            self.pdf_doc = QPdfDocument(self)
            self.pdf_view = QPdfView(self)
            self.pdf_view.setDocument(self.pdf_doc)
            self.pdf_view.hide()

        self.layout.addWidget(self.image_scroll)
        self.layout.addWidget(self.text_edit)
        if self.pdf_view:
            self.layout.addWidget(self.pdf_view)

    def clear_preview(self, message: str = "Select a file to preview") -> None:
        self.title.setText("Preview")
        self.image_label.setText(message)
        self.image_label.setPixmap(QPixmap())
        self.image_label.show()
        self.image_scroll.hide()
        self.text_edit.hide()
        self.text_edit.clear()
        if self.pdf_view:
            self.pdf_view.hide()
        if self.pdf_doc:
            self.pdf_doc.close()

    def show_text(self, name: str, content: str) -> None:
        self.title.setText(f"Preview - {name}")
        self.image_scroll.hide()
        if self.pdf_view:
            self.pdf_view.hide()
        self.text_edit.setPlainText(content)
        self.text_edit.show()

    def show_image(self, name: str, data: bytes) -> None:
        self.title.setText(f"Preview - {name}")
        self.text_edit.hide()
        if self.pdf_view:
            self.pdf_view.hide()

        if PIL_AVAILABLE:
            pixmap = self._load_image_pil(data)
        else:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
        self._set_pixmap_display(pixmap)

    def _load_image_pil(self, data: bytes) -> QPixmap:
        try:
            img = Image.open(BytesIO(data))
            if img.mode != "RGB":
                if img.mode == "RGBA":
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])
                    img = rgb_img
                else:
                    img = img.convert("RGB")

            img.thumbnail((800, 600), Image.Resampling.LANCZOS)
            ppm_data = BytesIO()
            img.save(ppm_data, format="PPM")
            ppm_data.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(ppm_data.read(), "PPM")
            return pixmap
        except Exception:
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            return pixmap

    def _set_pixmap_display(self, pixmap: QPixmap) -> None:
        self.image_label.clear()
        self.image_label.show()
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap)
            self.image_scroll.show()
        else:
            self.clear_preview("Unable to render this image.")

    def show_pdf(self, name: str, data: bytes) -> None:
        if not (self.pdf_doc and self.pdf_view):
            self.clear_preview("PDF preview is not available on this system. You can still download the file.")
            return

        self.title.setText(f"Preview - {name}")
        self.image_scroll.hide()
        self.text_edit.hide()

        qbytes = QByteArray(data)
        self._pdf_buffer = QBuffer()
        self._pdf_buffer.setData(qbytes)
        self._pdf_buffer.open(QBuffer.ReadOnly)
        self.pdf_doc.load(self._pdf_buffer)
        self.pdf_view.show()


class MainWindow(QMainWindow):
    def __init__(self, manager: SFTPClientManager) -> None:
        super().__init__()
        self.manager = manager
        self.current_path = self.manager.get_user_root()
        self.entries: List[RemoteEntry] = []
        self.tree_initialized = False

        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 820)

        self._build_toolbar()
        self._build_ui()
        self._build_statusbar()
        self.refresh()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(toolbar)

        back_action = QAction("Up", self)
        back_action.triggered.connect(self.go_up)
        toolbar.addAction(back_action)

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(refresh_action)

        self.download_action = QAction("Download", self)
        self.download_action.triggered.connect(self.download_selected)
        toolbar.addAction(self.download_action)

        self.open_action = QAction("Open", self)
        self.open_action.triggered.connect(self.open_selected)
        toolbar.addAction(self.open_action)

        toolbar.addSeparator()
        self.path_label = QLabel()
        toolbar.addWidget(self.path_label)

    def _build_ui(self) -> None:
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folders"])
        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        self.tree.itemExpanded.connect(self.on_tree_item_expanded)

        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setShowGrid(False)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.cellClicked.connect(self.on_file_selected)
        self.file_table.cellDoubleClicked.connect(self.on_file_double_clicked)
        self.file_table.itemSelectionChanged.connect(self.update_action_state)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.setColumnWidth(0, 360)

        self.preview = PreviewPanel()

        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.file_table)
        splitter.addWidget(self.preview)
        splitter.setSizes([250, 650, 500])

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _build_statusbar(self) -> None:
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(f"Connected as {self.manager.username} to {HOST}")

    def refresh(self) -> None:
        try:
            self.current_path = self.manager.safe_path(self.current_path)
            self.path_label.setText(f"Current path: {self.current_path}")
            self.status.showMessage(f"Loading {self.current_path}...")
            self.entries = self.manager.list_dir(self.current_path)
            if not self.tree_initialized:
                self.populate_tree()
                self.tree_initialized = True
            self.populate_files()
            self.preview.clear_preview()
            self.select_tree_path(self.current_path)
            self.status.showMessage(f"Ready - {len(self.entries)} item(s)")
        except Exception as exc:
            self.show_error("Refresh failed", exc)

    def populate_tree(self) -> None:
        self.tree.clear()
        root_path = self.manager.get_user_root()
        root_item = QTreeWidgetItem([os.path.basename(root_path) or root_path])
        root_item.setData(0, Qt.UserRole, root_path)
        root_item.setData(0, Qt.UserRole + 1, True)
        root_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon))
        self.tree.addTopLevelItem(root_item)

        try:
            entries = self.manager.list_dir(root_path)
            dirs = sorted((e for e in entries if e.is_dir), key=lambda x: x.name.lower())
            for entry in dirs:
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.UserRole, entry.path)
                child.setData(0, Qt.UserRole + 1, False)
                child.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                child.addChild(QTreeWidgetItem(["Loading..."]))
                root_item.addChild(child)
            self.tree.expandItem(root_item)
        except Exception:
            pass

    def on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.UserRole)
        already_loaded = item.data(0, Qt.UserRole + 1)
        if already_loaded or not path:
            return

        try:
            if item.childCount() > 0 and item.child(0).text(0) == "Loading...":
                item.removeChild(item.child(0))

            entries = self.manager.list_dir(path)
            dirs = sorted((e for e in entries if e.is_dir), key=lambda x: x.name.lower())
            for entry in dirs:
                child = QTreeWidgetItem([entry.name])
                child.setData(0, Qt.UserRole, entry.path)
                child.setData(0, Qt.UserRole + 1, False)
                child.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
                child.addChild(QTreeWidgetItem(["Loading..."]))
                item.addChild(child)

            item.setData(0, Qt.UserRole + 1, True)
        except Exception:
            pass

    def populate_files(self) -> None:
        self.file_table.setRowCount(len(self.entries))
        dir_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        file_icon = self.style().standardIcon(QStyle.SP_FileIcon)

        for row, entry in enumerate(self.entries):
            type_label = "Folder" if entry.is_dir else self.file_type_label(entry.name)
            size_label = "-" if entry.is_dir else self.human_size(entry.size)
            modified_label = self.format_mtime(entry.mtime)

            name_item = QTableWidgetItem(entry.name)
            name_item.setData(Qt.UserRole, entry.path)
            name_item.setIcon(dir_icon if entry.is_dir else file_icon)

            self.file_table.setItem(row, 0, name_item)
            self.file_table.setItem(row, 1, QTableWidgetItem(type_label))
            self.file_table.setItem(row, 2, QTableWidgetItem(size_label))
            self.file_table.setItem(row, 3, QTableWidgetItem(modified_label))

        self.file_table.resizeRowsToContents()
        self.update_action_state()

    def select_tree_path(self, path: str) -> None:
        matches = self.tree.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive)
        for item in matches:
            if item.data(0, Qt.UserRole) == path:
                self.tree.setCurrentItem(item)
                return

    def selected_entry(self) -> Optional[RemoteEntry]:
        row = self.file_table.currentRow()
        if row < 0 or row >= len(self.entries):
            return None
        return self.entries[row]

    def update_action_state(self) -> None:
        entry = self.selected_entry()
        is_file = bool(entry and not entry.is_dir)
        self.download_action.setEnabled(is_file)
        self.open_action.setEnabled(is_file)

    def on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            self.current_path = path
            self.refresh()

    def on_file_selected(self, row: int, column: int) -> None:
        self.update_action_state()
        entry = self.entries[row]
        if entry.is_dir:
            self.preview.clear_preview("Folder selected. Double-click to open it.")
            return
        self.preview_file(entry)

    def on_file_double_clicked(self, row: int, column: int) -> None:
        entry = self.entries[row]
        if entry.is_dir:
            self.current_path = entry.path
            self.refresh()
        else:
            self.preview_file(entry)

    def preview_file(self, entry: RemoteEntry) -> None:
        ext = os.path.splitext(entry.name)[1].lower()
        try:
            if ext in ALLOWED_EXT_IMAGE:
                if entry.size > MAX_IMAGE_PREVIEW_BYTES:
                    self.preview.clear_preview("Image is too large for inline preview. Use Open or Download.")
                    return
                self.status.showMessage(f"Previewing image {entry.name}...")
                data = self.manager.read_bytes(entry.path)
                self.preview.show_image(entry.name, data)
            elif ext in ALLOWED_EXT_TEXT:
                self.status.showMessage(f"Previewing text {entry.name}...")
                data, truncated = self.manager.read_preview_bytes(entry.path, MAX_TEXT_PREVIEW_BYTES)
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("latin-1", errors="replace")
                if truncated:
                    text += "\n\n[Preview truncated]"
                self.preview.show_text(entry.name, text)
            elif ext in ALLOWED_EXT_PDF:
                if entry.size > MAX_PDF_PREVIEW_BYTES:
                    self.preview.clear_preview("PDF is too large for inline preview. Use Open or Download.")
                    return
                self.status.showMessage(f"Previewing PDF {entry.name}...")
                data = self.manager.read_bytes(entry.path)
                self.preview.show_pdf(entry.name, data)
            else:
                self.preview.clear_preview("No built-in preview for this file type. Use Download or Open.")
            self.status.showMessage(f"Ready - previewed {entry.name}")
        except Exception as exc:
            self.show_error("Preview failed", exc)

    def download_selected(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Please select a file first.")
            return
        if entry.is_dir:
            QMessageBox.information(self, "Folder selected", "Please select a file, not a folder.")
            return

        target, _ = QFileDialog.getSaveFileName(self, "Save file", entry.name)
        if not target:
            return

        try:
            self.status.showMessage(f"Downloading {entry.name}...")
            self.manager.download_file(entry.path, target)
            self.status.showMessage(f"Downloaded {entry.name}")
            QMessageBox.information(self, "Download complete", f"Saved to:\n{target}")
        except Exception as exc:
            self.show_error("Download failed", exc)

    def open_selected(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Please select a file first.")
            return
        if entry.is_dir:
            QMessageBox.information(self, "Folder selected", "Please select a file, not a folder.")
            return

        try:
            suffix = os.path.splitext(entry.name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="lab_browser_") as temp_file:
                temp_path = temp_file.name

            self.status.showMessage(f"Opening {entry.name}...")
            self.manager.download_file(entry.path, temp_path)

            if sys.platform == "win32":
                os.startfile(temp_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", temp_path])
            else:
                subprocess.Popen(["xdg-open", temp_path])

            self.status.showMessage(f"Opened {entry.name}")
            QMessageBox.information(self, "File opened", f"Opening file:\n{entry.name}")
        except Exception as exc:
            self.show_error("Failed to open file", exc)

    def go_up(self) -> None:
        root = self.manager.get_user_root().rstrip("/")
        current = self.current_path.rstrip("/")
        if current == root:
            return
        parent = os.path.dirname(current)
        if not parent.startswith(root):
            parent = root
        self.current_path = parent
        self.refresh()

    @staticmethod
    def file_type_label(name: str) -> str:
        ext = os.path.splitext(name)[1].lower()
        if ext in ALLOWED_EXT_IMAGE:
            return "Image"
        if ext in ALLOWED_EXT_TEXT:
            return "Text"
        if ext in ALLOWED_EXT_PDF:
            return "PDF"
        return ext[1:].upper() if ext else "File"

    @staticmethod
    def human_size(size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        val = float(size)
        for unit in units:
            if val < 1024 or unit == units[-1]:
                return f"{val:.1f} {unit}"
            val /= 1024
        return f"{size} B"

    @staticmethod
    def format_mtime(mtime: int) -> str:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

    def show_error(self, title: str, exc: Exception) -> None:
        self.status.showMessage(title)
        QMessageBox.critical(self, title, str(exc))

    def closeEvent(self, event) -> None:
        self.manager.disconnect()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)

    manager = SFTPClientManager()
    login = LoginDialog(manager)
    if login.exec() != QDialog.Accepted:
        manager.disconnect()
        return 0

    window = MainWindow(manager)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
