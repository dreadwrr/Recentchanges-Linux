import os
import psutil
import re
import sys
from dataclasses import dataclass
from PySide6.QtCore import Signal, QObject, Slot
from PySide6.QtGui import QTextCharFormat, QColor, QTextCursor, QIcon
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QDialog, QPushButton, QComboBox, QLineEdit, QDialogButtonBox, QLabel
from .gpgcrypto import start_user_agent


ANSI_COLOR_MAP = {
    "36": QColor("cyan"),
    "31": QColor("red"),
    "1;32": QColor("limegreen"),
    "34": QColor("blue"),
    "33": QColor("orange"),
    "35": QColor("magenta"),
    "37": QColor("white")
}

RESET_CODE = "0"
ANSI_REGEX = re.compile(r'\033\[([0-9;]+)m')


class FastColorText(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.current_color = None

    def append_colored_output(self, line: str):
        normalized = line.replace("\r\n", "\n").replace("\r", "\n")
        parts = ANSI_REGEX.split(normalized)
        i = 0

        while i < len(parts):
            text = parts[i]
            if text:
                self.insert_colored_text(text, self.current_color)
            i += 1

            if i < len(parts):
                code = parts[i]
                if code == RESET_CODE:
                    self.current_color = None
                elif code in ANSI_COLOR_MAP:
                    self.current_color = ANSI_COLOR_MAP[code]
                i += 1

        self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        )

    def insert_colored_text(self, text, color):
        fmt = QTextCharFormat()
        if color:
            fmt.setForeground(color)

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, fmt)
        self.setTextCursor(cursor)


class QTextEditLogger(QObject):  # gui/console
    new_message = Signal(str)

    def __init__(self, output_handler):
        super().__init__()
        self.output_handler = output_handler
        self.console = sys.__stdout__   # save original stdout

    def write(self, message):
        if message is None:
            return

        self.new_message.emit(message)
        # self.output_handler(message)   # show in GUI

        self.console.write(message)  # also show in console
        self.console.flush()

    def flush(self):
        self.console.flush()


class Worker(QObject):
    progress = Signal(int)
    log = Signal(str)
    complete = Signal(int)

    exception = Signal(object, object, object)

    def __init__(self, database):
        super().__init__()
        self.database = database
        self._should_stop = False

    def stop(self):
        self._should_stop = True


class DriveLogicError(Exception):
    pass


class ConfigurationError(Exception):
    pass


class DriveSelectorDialog(QDialog):
    def __init__(self, basedir, j_settings, idx_drive=False, filter_out=None, parent=None):
        super().__init__(parent)

        self.final_drives = {}
        self.filter_drv = filter_out
        self.setWindowTitle("Select Drive")

        layout = QVBoxLayout(self)

        self.drive_combo = QComboBox()

        if idx_drive:
            drives = self.get_physical_drives(basedir, j_settings, filter_out)
            self.drives = drives

        self.drive_combo.addItems(drives)
        layout.addWidget(self.drive_combo)

        select_btn = QPushButton("Select")
        select_btn.clicked.connect(self.accept)
        layout.addWidget(select_btn)

    def selected_drive(self):
        return self.drive_combo.currentText(), self.final_drives.get(self.drive_combo.currentText())

    def get_physical_drives(self, basedir, j_settings, filter_out=None):

        known_uuid = set()
        for key in j_settings.keys():
            drive_info = j_settings.get(key, {})
            if isinstance(drive_info, dict):
                drive_uuid = drive_info.get("drive_partuuid")
                if drive_uuid:
                    known_uuid.add(drive_uuid)

        drives = []
        devices = []

        dev_uuid_hash = {}

        for p in psutil.disk_partitions(all=False):  # all=False skip pseudo filesystems
            if p.fstype in ('tmpfs', 'squashfs', 'overlay'):
                continue
            if p.mountpoint.startswith("/mnt/live"):
                continue
            # remove system basedir
            if basedir and p.mountpoint.lower() == basedir.lower():
                continue
            if filter_out and p.mountpoint in filter_out:
                continue
            devices.append((p.device, p.mountpoint))

        if devices:
            # build dev - uuid hash map
            by_part_path = "/dev/disk/by-partuuid/"
            if os.path.exists(by_part_path):
                with os.scandir(by_part_path) as it:
                    for entry in it:
                        if entry.is_symlink():
                            full_path = os.path.realpath(entry.path)
                            dev_uuid_hash[full_path] = entry.name
            else:
                print(f"Error: {by_part_path} does not exist.")
            for dev, drv in devices:
                if dev in dev_uuid_hash:
                    self.final_drives[drv] = {
                        "uuid": dev_uuid_hash[dev],
                        "dev": os.path.basename(dev)
                    }

            for drive, drive_info in self.final_drives.items():  # drive, uuid
                uuid = drive_info.get("uuid")

                if uuid and uuid not in known_uuid:
                    drives.append(drive)

            return drives


@dataclass
class BasedirDrive:
    suffix: str
    parent: str
    part_uuid: str
    moi: str
    drive_type: str
    cache_s: str
    systimeche: str
    psextn: list


class BasedirProfiles:
    def __init__(self, drive_button):
        self.data = []
        self.drive_button = drive_button
        self.current_index = 0
        self.items = 0

    def add_item(self, item):
        if isinstance(item, tuple):
            self.data.append(item)
            self.items += 1
            return self.items - 1
        else:
            raise ValueError("Item must be a tuple.")

    def update_current_item(self, psextn, **new_data):
        if self.current_index >= 0 and self.current_index < self.items:

            uuid, drive, key = self.data[self.current_index]
            drive.psextn = psextn
            key.update(new_data)
            self.data[self.current_index] = (uuid, drive, key)
        else:
            raise IndexError("No current item or invalid index.")

    def remove_item(self, index, current_index):
        x = self.items
        if 0 <= index < x:
            del self.data[index]
            self.items -= 1
            if index <= current_index:
                self.current_index = max(0, self.current_index - 1)
            return self.current_index
        else:
            raise IndexError("remove_item Index out of range.")

    def set_item(self, index, item):
        if 0 <= index < self.items:
            self.data[index] = item
        else:
            raise IndexError("Index out of range.")

    def get_item(self, index):
        if 0 <= index < self.items:
            return self.data[index]
        else:
            raise IndexError("Index out of range.")

    def get_current_item(self):
        if self.current_index >= 0 and self.current_index < self.items:
            return self.data[self.current_index]
        else:
            raise IndexError("No current item or invalid index.")

    def index_by_value(self, value):
        for i, drive_data in enumerate(self.data):
            _, drive_object, _ = drive_data
            if value in (drive_object.part_uuid, drive_object.suffix, drive_object.moi, drive_object.cache_s, drive_object.systimeche):
                return i
        return -1

    def set_current_index(self, index):
        x = self.items
        if 0 <= index < x:
            self.current_index = index
            uuid, drive, info = self.data[index]
            self.drive_button.setText(drive.moi)
        else:
            raise IndexError("Index out of range.")


class GpgPromptWorker(QObject):

    finished = Signal(bool)

    def __init__(self, dbtarget, user):
        super().__init__()
        self.dbtarget = dbtarget
        self.user = user

    @Slot()
    def run(self):
        self.finished.emit(start_user_agent(self.dbtarget, self.user))


class PassphraseDialog(QDialog):
    def __init__(self, icon_path=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter new GPG Password")
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        self.layout = QVBoxLayout(self)

        if icon_path:
            label = QLabel()
            label.setPixmap(QIcon(icon_path).pixmap(64, 64))
            self.layout.addWidget(label)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addWidget(self.password_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)

    def get_password(self):
        return self.password_input.text()
