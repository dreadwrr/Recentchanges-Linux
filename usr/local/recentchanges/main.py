# 02/25/2026              Qt gui linux                 Developer buddy 5.0
import glob
import logging
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from PySide6.QtCore import Qt, Slot, Signal, QThread, QTimer, QSortFilterProxyModel, QSize
from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap, QImage, QPalette, QColor
from PySide6.QtSql import QSqlQuery
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QMainWindow, QMenu, QHeaderView, QStyle
from src.clearworker import ClearWorker
from src.configfunctions import check_config
from src.configfunctions import dump_j_settings
from src.configfunctions import dump_toml
from src.configfunctions import get_config
from src.configfunctions import load_toml
from src.configfunctions import update_dict
from src.configfunctions import update_j_settings
from src.configfunctions import update_toml_values
from src.dbworkerstream import DbWorkerIncremental
from src.gpgcrypto import decr
from src.gpgcrypto import encr
from src.gpgcrypto import parse_gpg_agent_conf
from src.gpgcrypto import test_gpg_agent
from src.gpgkeymanagement import genkey
from src.gpgkeymanagement import iskey
from src.imageraster import raised_image
from src.logs import check_log_perms
from src.logs import change_logger
from src.logs import setup_logger
from src.processhandler import ProcessHandler
from src.pyfunctions import is_integer
from src.pyfunctions import user_path
from src.pysql import clear_extn_tbl
from src.pysql import create_db
from src.pysql import dbtable_has_data
from src.qtclasses import BasedirProfiles
from src.qtclasses import BasedirDrive
from src.qtclasses import ConfigurationError
from src.qtclasses import DriveLogicError
from src.qtclasses import DriveSelectorDialog
from src.qtclasses import FastColorText
from src.qtclasses import PassphraseDialog
from src.qtclasses import QTextEditLogger
from src.qtdrivefunctions import current_drive_type_model_check
from src.qtdrivefunctions import device_name_of_mount
from src.qtdrivefunctions import get_cache_s
from src.qtdrivefunctions import get_idx_tables
from src.qtdrivefunctions import get_mount_from_partuuid
from src.qtdrivefunctions import get_mount_partuuid
from src.qtdrivefunctions import get_new_idx_suffix
from src.qtdrivefunctions import parent_of_device
from src.qtdrivefunctions import parse_drive
from src.qtdrivefunctions import parse_suffix
from src.qtdrivefunctions import setup_drive_cache
from src.qtdrivefunctions import setup_drive_settings
from src.qtfunctions import add_new_extension
from src.qtfunctions import available_fonts
from src.qtfunctions import check_for_updates
from src.qtfunctions import commit_note
from src.qtfunctions import fill_extensions
from src.qtfunctions import get_conn
from src.qtfunctions import get_help
from src.qtfunctions import has_log_data
from src.qtfunctions import has_sys_data
from src.qtfunctions import help_about
from src.qtfunctions import load_gpg
from src.qtfunctions import open_html_resource
from src.qtfunctions import polkit_check
from src.qtfunctions import profile_to_str
from src.qtfunctions import ps_profile_type
from src.qtfunctions import run_set_helper
from src.qtfunctions import select_custom
from src.qtfunctions import show_cmddoc
from src.qtfunctions import sort_right
from src.qtfunctions import table_loaded
from src.qtfunctions import user_data_from_database
from src.qtfunctions import user_data_to_database
from src.qtfunctions import valid_crest
from src.qtfunctions import window_prompt
from src.qtfunctions import window_message
from src.rntchangesfunctions import check_utility
from src.rntchangesfunctions import cnc
from src.rntchangesfunctions import display
from src.rntchangesfunctions import get_diff_file
from src.rntchangesfunctions import get_linux_distro
from src.rntchangesfunctions import multi_value
from src.rntchangesfunctions import name_of
from src.rntchangesfunctions import removefile
from src.rntchangesfunctions import resolve_editor
from src.rntchangesfunctions import time_convert
from src.ui_mainwindow import Ui_MainWindow
from src.xzmprofile import XzmProfile


class MainWindow(QMainWindow):

    worker_timeout_sn = Signal()
    proc_timeout_sn = Signal()
    stop_worker_sn = Signal()  # stop thread or proc
    stop_proc_sn = Signal()
    reload_database_sn = Signal(int, bool, object)  # hudt append text
    update_ui_sn = Signal(int, str)  # change checkboxes after QProcess or thread
    reload_drives_sn = Signal(int, int, str)  # update drive combobox on complete
    reload_sj_sn = Signal(int, object, str, bool)  # also update drive combo on complete

    def __init__(self, appdata_local, home_dir, xdg_runtime, pst_data, config, j_settings, toml_file, json_file, log_path, driveTYPE, distro_name, dbopt, dbtarget, CACHE_S, CACHE_S_str, systimeche, suffix, gpg_path, gnupg_home, dspEDITOR, dspPATH, popPATH, downloads, email, usr, uid, gid, tempdir):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.toml_file = toml_file
        self.sj = json_file
        self.driveTYPE = driveTYPE
        self.log_path = log_path
        self.distro_name = distro_name
        self.dbopt = dbopt  # db
        self.dbtarget = dbtarget  # gpg
        self.gnupg_home = gnupg_home
        self.CACHE_S = CACHE_S
        self.CACHE_S_str = CACHE_S_str
        self.systimeche = systimeche
        self.suffix = suffix
        self.gpg_path = gpg_path
        self.dspEDITOR = dspEDITOR
        self.dspPATH = dspPATH
        self.popPATH = popPATH
        self.email = email
        self.usr = usr
        self.uid = uid
        self.gid = gid
        self.tempdir = tempdir  # thisapp

        self.config = None
        self.ANALYTICSECT = config['analytics']['ANALYTICSECT']
        self.FEEDBACK = config['analytics']['FEEDBACK']
        self.compLVL = config['logs']['compLVL']
        self.pageIDX = config['display']['pageIDX']
        self.hudCOLOR = config['display']['hudCOLOR']
        self.hudSZE = config['display']['hudSZE']
        self.hudFNT = config['display']['hudFNT']
        self.MODULENAME = config['paths']['MODULENAME']  # diff file prefix
        self.basedir = config['search']['drive']  # search target
        self.oldbasedir = self.basedir
        proteusEXTN = config['shield']['proteusEXTN']
        self. proteusEXTN = ["[no extension]" if p == "" else p for p in proteusEXTN]
        self.proteusPATH = config['shield']['proteusPATH']
        self.checksum = config['diagnostics']['checkSUM']
        self.proteusSHIELD = config['shield']['proteusSHIELD']
        self.xzm = config['shield']['xzm']
        self.is_xzm_profile = self.xzm if self.suffix == "/" else False
        self.EXCLDIRS = user_path(config['search']['EXCLDIRS'], usr)
        zipPROGRAM = config['compress']['zipPROGRAM']
        self.zipPROGRAM = zipPROGRAM.lower()
        self.zipPATH = config['compress']['zipPATH']
        self.downloads = downloads
        self.extensions = config['search']['extension']

        self.j_settings = j_settings  # usrprofile

        self.psEXTN = self.j_settings.get(self.suffix, {}).get("proteusEXTN")
        self.ps_is_xzm = False
        if self.psEXTN:
            self.ps_is_xzm = ps_profile_type(self.psEXTN)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.remaining_startup)  # polkit, any other routines
        self.timer.start(1000)

        # load the database at some point if not already by pg change
        # QTimer.singleShot(5000, self.display_db)

        # Vars
        self.app_version = "5.0.3"
        self.PWD = os.getcwd()
        self.home_dir = home_dir
        config_local = home_dir / ".config" / "recentchanges"
        self.homedir = home_dir
        self.xdg_runtime = xdg_runtime
        self.USRDIR = os.path.join(home_dir, "Downloads")
        self.lclhome = appdata_local
        self.lclscripts = appdata_local / "scripts"
        self.resources = appdata_local / "Resources"
        self.user_resources = pst_data / "Resources"
        self.dispatch = appdata_local / "set_recent_helper"
        self.filter_file = appdata_local / "filter.py"
        flth_frm = pst_data / "flth.csv"
        self.flth = str(flth_frm)

        self.jpgdir = appdata_local / "Documents"  # str(Path.home() / "Documents")   /home/guest/.config/icons/
        self.crestdir = self.jpgdir / "crests"
        self.jpgdefault = "background.png"  # default png
        self.crestdefault = "dragonm"  # . crest

        # verify on load
        self.jpguserdir = pst_data / "Documents"
        self.crestuserdir = self.jpguserdir / "crests"

        self.userpicture = self.jpguserdir / "background.png"
        self.usercrest = self.crestuserdir / "dragonm.png"

        if self.userpicture.is_file():
            self.picture = self.userpicture
        else:
            os.makedirs(self.jpguserdir, mode=0o755, exist_ok=True)
            self.picture = self.jpgdir / "background.png"  # current png
            shutil.copy(self.picture, self.userpicture)
        if self.usercrest.is_file():
            self.crest = self.usercrest
        else:
            os.makedirs(self.crestuserdir, mode=0o755, exist_ok=True)
            self.crest = self.crestdir / "dragonm.png"  # . crest
            shutil.copy(self.crest, self.usercrest)

        command_file = self.resources / "commands.txt"
        user_command_file = self.user_resources / "commands.txt"

        if not user_command_file.is_file():
            os.makedirs(self.user_resources, mode=0o755, exist_ok=True)
            shutil.copy(command_file, user_command_file)
        self.command_file = user_command_file
        self.default_command_file = command_file

        self.defaultdiff = os.path.join(self.USRDIR, f'{self.MODULENAME}xSystemDiffFromLastSearch500.txt')

        self.file_out = xdg_runtime / "file_output"  # default result file

        self.tomldefault = config_local / "config.bak"
        self.tomldefault_imt = None  # initial mtime

        sys_tables, self.cache_table, _ = get_idx_tables(self.basedir, self.CACHE_S_str, suffix)
        self.sys_a, self.sys_b = sys_tables

        self.is_polkit = False
        self.isexec = False
        self.is_user_abort = False
        self.dirtybit = False  # something to save while the db is connected or program exit

        self.difffile = None
        self.xzm_obj = None
        self.user_extensions = []

        self.worker = None
        self.worker2 = None  # database streamer

        self.worker_thread = None
        self.proc = None

        self.db = None  # set after first db load
        self.table = None  # last loaded table

        self.lastdir = None
        self.lastdrive = self.suffix

        self.result = None
        self.exit_result = None

        self.nc = None

        # initialize
        self.init_timers()
        self.init_events()
        self.install_logger()

        self.ui.dbprogressBAR.setValue(0)
        pixmap = QPixmap(self.crest)  # Load the image from the path      '.\\Documents\\crests\\dragonm.png'  # original
        self.ui.jpgcr.setPixmap(pixmap)  # Set the pixmap on the label
        self.ui.jpgcr.setScaledContents(True)
        self.refresh_jpg()  # load pic

        # one time items
        ro = self.j_settings.get("search_range")
        if ro:
            self.ui.stime.setValue(int(ro))
        fo = self.j_settings.get("find_range")
        if fo:
            self.ui.sffile.setValue(int(fo))
        ix = 0
        so = self.j_settings.get("search_output")
        if so:
            ix = self.ui.combftimeout.findText(so)
            if ix != -1:
                self.ui.combftimeout.setCurrentIndex(ix)
            else:
                update_dict(None, self.j_settings, "search_output")
                dump_j_settings(self.j_settings, self.sj)
                print(f"Couldnt find search output setting {so}")
        else:
            self.ui.combftimeout.setCurrentText("Downloads")
        self.initialize_ui(is_startup=True)  # load extensions from database. if no database create one. fill combos
        # end one time items

        if self.pageIDX == 2:
            self.show_page_2()
        elif self.pageIDX == 1:
            self.show_page()

    @Slot(str)
    def append_log(self, text):
        cursor = self.ui.hudt.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if text and cursor.positionInBlock() != 0 and not text.startswith(("\n", "\r")):
            text = "\n" + text
        if text and not text.endswith(("\n", "\r")):
            text += "\n"
        self.ui.hudt.append_colored_output(text)

    @Slot(str)
    def update_db_status(self, text):
        """ control dbmainlabel / ui elements """
        self.ui.dbmainlabel.setText(text)
        if self._status_reset_timer.isActive():
            self._status_reset_timer.stop()
        self._status_reset_timer.start(40000)

    @Slot(int)
    def increment_progress(self, value):
        self.ui.progressBAR.setValue(value)

    @Slot(int)
    def increment_db_progress(self, value):
        self.ui.dbprogressBAR.setValue(value)

    @Slot(bool)
    def set_nc(self, nc):
        self.nc = nc

    def install_logger(self):
        # hudt
        old_widget = self.ui.hudt
        layout = self.ui.gridLayout
        index = layout.indexOf(old_widget)
        position = layout.getItemPosition(index)
        layout.removeWidget(old_widget)
        old_widget.deleteLater()

        self.ui.hudt = FastColorText()  # hud/terminal colors gui
        self.ui.hudt.setStyleSheet(
            "QPlainTextEdit {"
            " background-color: black;"
            " font-family: Consolas, Courier, monospace;"
            " font-size: 12pt;"
            "}"
        )
        layout.addWidget(self.ui.hudt, *position)

        # self.ui.hudt.append_colored_output("\033[31mRed text\033[0m")  test nested ansi colors
        # self.ui.hudt.append_colored_output("\033[1;32mGreen bold\033[0m\033[31mRed text\033[0m")

        self.logger = QTextEditLogger(None)  # self.append_colored_output)
        self.logger.new_message.connect(self.ui.hudt.append_colored_output)
        self.main_stdout = sys.stdout
        self.main_stderr = sys.stderr
        sys.stdout = self.logger
        sys.stderr = self.logger  # self.logger.output_handler = self.ui.hudt.append_colored_output  not thread safe
        # end hudt

    def init_events(self):

        self.update_ui_sn.connect(self.update_ui_settings)
        self.reload_database_sn.connect(self.reload_database)
        self.reload_drives_sn.connect(self.reload_drives)
        self.reload_sj_sn.connect(self.manage_sj)

        # Menu bar
        self.ui.actionStop.triggered.connect(self.x_action)

        self.ui.actionSave.triggered.connect(self.save_user_data)
        self.ui.actionClearh.triggered.connect(lambda _: self.ui.hudt.clear())

        self.ui.actionExit.triggered.connect(QApplication.quit)
        self.ui.actionClear_extensions.triggered.connect(self.clear_extensions)
        self.ui.actionUpdates.triggered.connect(lambda: check_for_updates(self.app_version, "dreadwrr", "Recentchanges", self))

        self.ui.actionCommands_2.triggered.connect(lambda: show_cmddoc(self.command_file, self.lclhome, self.gpg_path, self.gnupg_home, self.email, self.systimeche, self.ui.hudt))
        self.ui.actionQuick1.triggered.connect(lambda: display(self.dspEDITOR, self.command_file, True, self.dspPATH))
        self.ui.actionDiag1.triggered.connect(self.show_status)
        self.ui.actionLogging.triggered.connect(lambda: display(self.dspEDITOR, self.log_path, True, self.dspPATH))

        self.ui.actionAbout.triggered.connect(lambda: help_about(self.lclhome, self.ui.hudt))
        self.ui.actionResource.triggered.connect(self.open_resource)
        self.ui.actionHelp.triggered.connect(lambda: get_help(self.lclscripts, self.resources, self.ui.hudt))
        # end Menu bar

        # # 1 left <
        self.ui.queryButton.clicked.connect(self.execute_query)
        self.ui.sbasediridx.setMaximum(10)
        self.ui.sbasediridx.valueChanged.connect(self.set_basedir)  # change basedir beside main search .spinner
        # Main window

        # #1 mid ^ Stop Reset defaults button
        self.ui.resetButton.clicked.connect(self.x_action)

        # Find createdfiles
        self.ui.downloadButton.clicked.connect(lambda: self.find_downloads(self.basedir))
        self.ui.rmvButton.clicked.connect(self.rmv_idx_drive)
        self.ui.addButton.clicked.connect(self.idx_drive)
        # right >
        self.ui.jpgb.clicked.connect(self.load_jpg)

        # tomlb `settings` button
        # self.ui.tomlb.clicked.connect(self.showsettings)
        menu = QMenu(self)
        menu.addAction("Settings", lambda: self.edit_config())  # menu.addAction("Settings", lambda: display(self.dspEDITOR, self.toml_file, True, self.dspPATH))
        """ compatibility """
        # from src.qtfunctions import load_file_manager
        # menu.addAction("Open file manager", lambda: load_file_manager(self.lclhome, popPATH=self.popPATH))  # original
        # from src.qtfunctions import load_konsole
        # menu.addAction("Open terminal", lambda: load_konsole(self.lclhome, popPATH=self.popPATH)) # original
        """ porteus / nemesis """
        menu.addAction("Open file manager", lambda: run_set_helper(self.dispatch, ["run", "filemanager", str(self.lclhome), self.popPATH], self.is_polkit))
        menu.addAction("Open terminal", lambda: run_set_helper(self.dispatch, ["run", "terminal", str(self.lclhome), self.popPATH], self.is_polkit))
        menu.addSeparator()
        menu.addAction("Filter", lambda: display(self.dspEDITOR, self.filter_file, True, self.dspPATH))
        menu.addAction("Clear Hudt", lambda: self.ui.hudt.clear())
        menu.addAction("List fonts", lambda: available_fonts(self.ui.hudt))
        self.ui.tomlb.setMenu(menu)
        self.ui.tomlb.setPopupMode(self.ui.tomlb.ToolButtonPopupMode.InstantPopup)
        # end tomlb

        # bottom right
        self.ui.textEdit.textChanged.connect(self.set_dirtybit)
        # Top search
        self.ui.ftimeb.clicked.connect(lambda checked=False, s=self.ui.ftimeb: self.tsearch(s))
        self.ui.ftimebf.clicked.connect(lambda checked=False, s=self.ui.ftimebf: self.tsearch(s, True))
        self.ui.stimeb.clicked.connect(lambda checked=False, s=self.ui.stimeb: self.tsearch(s))
        self.ui.stimebf.clicked.connect(lambda checked=False, s=self.ui.stimebf: self.tsearch(s, True))
        # New than search
        self.ui.ntsb.clicked.connect(self.ntsearch)
        self.ui.ntbrowseb.clicked.connect(self.ntsearch)
        self.ui.ntbrowseb2.clicked.connect(self.ntsearch)
        # End Top search

        # findfile
        self.ui.ffileb.clicked.connect(lambda: self.ffile(False))

        self.ui.ffileb2.clicked.connect(self.new_extension)
        self.ui.ffilecb.clicked.connect(self.ffcompress)

        self.ui.diffchkc.toggled.connect(self.set_scan)
        # page_2
        self.ui.combdb.currentTextChanged.connect(self.display_db)

        self.ui.dbmainb1.clicked.connect(self.clear_cache)
        self.ui.dbmainb2.clicked.connect(self.super_impose)
        self.ui.dbmainb4.clicked.connect(self.set_hardlinks)
        # refresh button pg2
        self.ui.dbmainb3.setIcon(self.ui.dbmainb3.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self.ui.dbmainb3.setIconSize(QSize(20, 20))
        self.ui.dbmainb3.clicked.connect(self.reload_table)

        self.ui.dbidxb1.clicked.connect(lambda checked: self.clear_sys(self.suffix))

        self.ui.dbidxb2.clicked.connect(self.build_idx)
        self.ui.dbidxb3.clicked.connect(self.scan_idx)
        # nav   # End page_2
        self.ui.toolhomeb_2.clicked.connect(self.show_page)
        self.ui.toolrtb.clicked.connect(self.show_page_2)
        self.ui.toolrtb_2.clicked.connect(self.show_page)
        self.ui.toollftb_2.clicked.connect(self.show_page)
        self.ui.toollftb.clicked.connect(self.show_page_2)
        # End nav
        # End Main window

    def update_basedir(self, basedir, suffix, drive, index):

        CACHE_S = drive.cache_s
        systimeche = drive.systimeche
        driveTYPE = drive.drive_type
        psEXTN = drive.psextn

        self.oldbasedir = self.basedir
        self.basedir = basedir
        self.driveTYPE = driveTYPE
        self.psEXTN = psEXTN
        self.ps_is_xzm = ps_profile_type(psEXTN)
        self.CACHE_S = CACHE_S
        self.systimeche = systimeche
        self.suffix = suffix

        self.load_drives()  # downloads combo

        sys_tables, self.cache_table, _ = get_idx_tables(basedir, self.CACHE_S_str, suffix)
        self.sys_a, self.sys_b = sys_tables
        self.reload_database(0, is_remove=True, tables=('logs',))  # sort the dbcomb

        self.basedirs.set_current_index(index, self.ui.basedirButton, self.basedir)

    def set_scan(self, checked):
        if checked:
            self.ui.diffchkb.setChecked(True)

    # highlighted basedir button arrows pg_1
    def set_basedir(self):

        if not self.job_running(True):
            return

        self.ui.sbasediridx.blockSignals(True)
        y = self.basedirs.current_index
        x = self.ui.sbasediridx.value()
        d = 0 if x < y else 1  # up or down
        suffix = ""
        try:

            uuid, drive, info = self.basedirs.get_item(x)
            suffix = drive.suffix
            basedir = suffix
            if suffix != "/":

                mnt = get_mount_from_partuuid(uuid) if uuid else None

                if mnt:
                    basedir = mnt
                else:
                    r = self.basedirs.remove_item(x)
                    self.ui.sbasediridx.setValue(r)
                    self.ui.sbasediridx.setMaximum(self.basedirs.items - 1)
                    self.ui.sbasediridx.blockSignals(False)
                    self.isexec = False
                    return

            self.update_basedir(basedir, suffix, drive, x)
            self.is_xzm_profile = self.xzm if suffix == "/" else False
        except IndexError:
            self.ui.hudt.appendPlainText(f"Couldnt locate drive info going {'down' if d else 'up'} on basedir combo.")
            self.ui.sbasediridx.setValue(y)
        except Exception as e:
            self.ui.hudt.appendPlainText(f"Exception changing drives. {suffix}. err: {e} {type(e).__name__} \n {traceback.format_exc()}")
            logging.error("Error switching sbasediridx %s to index %s err: %s", self.basedir, x, e, exc_info=True)

        self.ui.sbasediridx.blockSignals(False)
        self.isexec = False

    def load_basedir_combo(self, a_drives, systimename):

        # add to class basedirs that have profiles for basedirButton

        basedirs = BasedirProfiles()

        drive_info = self.j_settings[self.suffix].copy()
        uuid = drive_info.get("drive_partuuid")
        moi = get_mount_from_partuuid(uuid)
        parent_device = drive_info.get("parent_device")
        dtype = drive_info.get("drive_type")
        psextn = drive_info.get("proteusEXTN")

        basedirs.add_item((uuid, BasedirDrive(self.suffix, parent_device, uuid, moi, dtype, self.CACHE_S, self.systimeche, psextn), drive_info))

        for a in a_drives:
            if a != self.suffix and a in self.j_settings and "proteusEXTN" in self.j_settings[a]:

                drive_info = self.j_settings[a].copy()

                parent_device = None
                uuid = None
                moi = "/"

                CACHE_S = self.CACHE_S_str
                systimeche = systimename

                if a != "/":

                    uuid = drive_info.get("drive_partuuid")

                    systimeche = systimename + "_" + a
                    CACHE_S = systimeche + ".gpg"
                    CACHE_S = os.path.join(self.lclhome, CACHE_S)

                    moi = get_mount_from_partuuid(uuid)  # a index could not be mounted therefor dont list it
                    device = device_name_of_mount(moi)

                    if device:
                        parent_device = parent_of_device(device)

                dtype = drive_info.get("drive_type")
                psextn = drive_info.get("proteusEXTN")

                basedirs.add_item((uuid, BasedirDrive(a, parent_device, uuid, moi, dtype, CACHE_S, systimeche, psextn), drive_info))

        self.basedirs = basedirs
        self.ui.sbasediridx.setMaximum(basedirs.items - 1)
        self.ui.basedirButton.setText(self.basedir)

    def load_find_file_combo(self):

        self.ui.combffileout.clear()
        self.ui.combffileout.addItem("/tmp")
        self.ui.combffileout.addItem("Downloads")

        d = self.downloads  # popPATH
        if d.strip():
            self.ui.combffileout.addItem(d)
            ix = self.ui.combffileout.count() - 1
            self.ui.combffileout.setCurrentIndex(ix)

        do = self.j_settings.get("compress_output")
        if do:
            si = do
            if do == "downloads":
                si = self.downloads
            ix2 = self.ui.combffileout.findText(si)
            if ix2 != -1:
                self.ui.combffileout.setCurrentIndex(ix2)
            else:
                update_j_settings(None, self.j_settings, "compress_output", self.sj)
                # print(f"Couldnt find downloads {si}")

    def initialize_ui(self, is_startup=False):

        self.change_format(is_startup)  # apply hudt settings

        # fill combos pg_1
        if is_startup:
            if os.path.isfile(self.dbopt):

                QTimer.singleShot(500, self.load_user_data)  # extension combo and the notes from the db
            else:
                fill_extensions(self.ui.combffile, self.extensions)  # extension combo if no db yet

                if not os.path.isfile(self.dbtarget):

                    try:
                        create_db(self.dbopt, (self.sys_a, self.sys_b))
                        if not encr(self.dbopt, self.dbtarget, self.email, user=self.usr, no_compression=self.nc, dcr=True):
                            self.ui.hudt.appendPlainText("Unable to create database")
                    except Exception as e:
                        QMessageBox.critical(None, "Error", f"Problem creating database through initializer. Exiting.. {e}")
                        QApplication.exit(1)

        # find download combo
        a_drives, systimename = self.load_drives()  # if any have a cache file ? loaded it into basedir combo

        # basedir combo. basedirButton + spinner = basedir combo
        self.load_basedir_combo(a_drives, systimename)

        # find file output combo
        self.load_find_file_combo()

        # end fill combos pg_1

    def remaining_startup(self):
        if polkit_check():
            self.is_polkit = True
        self.timer.stop()

    # Custom settings for hudt
    def set_stylesht(self, f_f, ccolor):

        if not is_integer(self.hudSZE):
            self.ui.hudt.appendPlainText(f"Invalid size format hudSZE: {self.hudSZE} defaulting to 12")
            self.hudSZE = 12
            update_toml_values({'display': {'hudSZE': 12}}, self.toml_file)
        else:
            if self.hudSZE == 0:
                self.hudSZE = 12
        self.ui.hudt.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: black;
                color: #{ccolor};
                font-family: {f_f};
                font-size: {self.hudSZE}pt;
            }}
        """)

    def change_format(self, is_startup=False):

        if is_startup:

            f_f = f"{self.hudFNT}, Courier, monospace"
            color = ""
            if self.hudCOLOR == "unix":
                color = "00FF00"
            elif self.hudCOLOR == "wb":
                color = "FFFFFF"
            elif self.hudCOLOR == "solar":
                color = "2AA198"
            elif self.hudCOLOR == "monochrome":
                color = "C0C0C0"
            self.set_stylesht(f_f, color)
    # end Custom settings for hudt

    def init_timers(self):
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.thread_timeout)

        self.proc_timeout_timer = QTimer(self)
        self.proc_timeout_timer.setSingleShot(True)
        self.proc_timeout_timer.timeout.connect(self.proc_timeout)

        self.worker_timeout_sn.connect(self.timeout_timer.stop)
        self.proc_timeout_sn.connect(self.proc_timeout_timer.stop)

        self._status_reset_timer = QTimer(self)
        self._status_reset_timer.setSingleShot(True)
        self._status_reset_timer.timeout.connect(
            lambda: self.ui.dbmainlabel.setText(
                "Status: Connected" if self.tableview_loaded() else "Status: offline"
            )
        )

        self.database_reload_timer = QTimer(self)
        self.database_reload_timer.setSingleShot(True)
        self._reload_connection = None

    # def keyPressEvent(self, event):
    #     if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
    #         QApplication.quit()
    #     super().keyPressEvent(event)

    def x_action(self):
        sender = self.sender()
        if self.isexec:
            self.clean_up()
            if hasattr(self, 'ui') and hasattr(self.ui, 'hudt'):
                self.ui.hudt.appendPlainText("Stopping current jobs or process")
        else:
            if sender != self.ui.actionStop:
                self.reset_settings()

    def is_thread(self):
        try:
            thread = getattr(self, 'worker_thread', None)
            if thread and thread.isRunning():
                self.ui.hudt.appendPlainText("Thread did not stop cleanly")
        except (RuntimeError, AttributeError) as e:
            logging.error("is_thread on closeEvent failed with the following exception: %s err: %s", e, type(e).__name__)

    def clean_up(self):
        if getattr(self, "is_user_abort", False):
            return
        self.is_user_abort = True
        for t_name in ['proc_timeout_timer', 'timeout_timer']:
            t = getattr(self, t_name, None)
            if t and t.isActive():
                t.stop()
        if getattr(self, 'worker', None) is not None:
            self.stop_worker_sn.emit()
        thread = getattr(self, 'worker_thread', None)
        try:
            if isinstance(thread, QThread) and thread.isRunning():
                thread.quit()
                if not thread.wait(3000):
                    self.ui.hudt.appendPlainText("Worker thread did not stop cleanly")
        except (RuntimeError, AttributeError) as e:
            logging.debug(f"clean_up couldnt close thread {e}")
            pass
        proc = getattr(self, "proc", None)
        if proc and proc.is_running():
            self.stop_proc_sn.emit()

    # on exit close threads processes and savenotes
    def closeEvent(self, event):

        if self.dirtybit:
            self.dirtybit = False
            uinpt = window_prompt(self, "Save notes", "Save note changes?", "Yes", "No")
            if uinpt:
                self.save_notes(isexit=True)  # self.save_user_data(True)

        if getattr(self, 'isexec', False):
            self.clean_up()
            for x, t in enumerate((getattr(self, 'worker_thread', None), getattr(self, 'worker2', None))):
                try:
                    if isinstance(t, QThread) and t.isRunning():
                        if x == 1:
                            t.requestInterruption()
                            t.wait(3000)
                        else:
                            logging.debug(f"closeEvent couldnt close thread {x}")
                except (RuntimeError, AttributeError) as e:
                    logging.debug(f"closeEvent couldnt close thread. {e}")
                    pass
            proc = getattr(self, 'proc', None)
            if proc:
                try:
                    if hasattr(proc, 'process') and proc.process:
                        proc.process.waitForFinished(10000)
                except (RuntimeError, AttributeError) as e:
                    logging.debug(f"closeEvent couldnt close process {e}")
                    pass

        sys.stdout = self.main_stdout
        sys.stderr = self.main_stderr
        try:
            self.logger.new_message.disconnect(self.ui.hudt.append_colored_output)
        except Exception:
            logging.error("closeEvent couldnt disconnect hudt properly")
            pass

        super().closeEvent(event)
        event.accept()

    def on_exit(self):
        self.setEnabled(True)

    def set_config(self, exit_code):

        if exit_code == 0:

            self.on_exit()

            toml = self.toml_file

            amt = toml.stat().st_mtime_ns
            imt = self.tomldefault_imt

            try:

                updated_config = load_toml(toml)
                if not updated_config:
                    raise ConfigurationError

                config_changed = (self.config != updated_config)

                if amt != imt or config_changed:

                    driveTYPE = updated_config['search']['driveTYPE']  # script entry
                    dspEDITOR = updated_config['display']['dspEDITOR']
                    popPATH = updated_config['display']['popPATH'].rstrip('/')
                    email = updated_config['backend']['email']
                    updated_downloads = updated_config['compress']['downloads'].rstrip('/')  # end script entry
                    ANALYTICSECT = updated_config['analytics']['ANALYTICSECT']
                    FEEDBACK = updated_config['analytics']['FEEDBACK']
                    zipPATH = updated_config['compress']['zipPATH']
                    zipPROGRAM_frm = updated_config['compress']['zipPROGRAM']
                    zipPROGRAM = zipPROGRAM_frm.lower()
                    checksum = updated_config['diagnostics']['checkSUM']
                    hudCOLOR = updated_config['display']['hudCOLOR']
                    hudSZE = updated_config['display']['hudSZE']
                    hudFNT = updated_config['display']['hudFNT']
                    compLVL = updated_config['logs']['compLVL']
                    MODULENAME = updated_config['paths']['MODULENAME']
                    EXCLDIRS = user_path(updated_config['search']['EXCLDIRS'], self.usr)
                    basedir = updated_config['search']['drive']
                    extensions = updated_config['search']['extension']
                    proteusEXTN = updated_config['shield']['proteusEXTN']
                    proteusPATH = updated_config['shield']['proteusPATH']
                    proteusSHIELD = updated_config['shield']['proteusSHIELD']
                    xzm = updated_config['shield']['xzm']

                    dspPATH_frm = self.config['display']['dspPATH'].rstrip('/')
                    new_dspPATH = updated_config['display']['dspPATH'].rstrip('/')
                    nogo = user_path(self.config['shield']['nogo'], self.usr)
                    new_nogo = user_path(updated_config['shield']['nogo'], self.usr)
                    suppress_list = user_path(self.config['shield']['filterout'], self.usr)
                    new_suppress_list = user_path(updated_config['shield']['filterout'], self.usr)

                    ll_level = self.config['logs']['logLEVEL']
                    new_ll_level = updated_config['logs']['logLEVEL']

                    root_log_file = self.config['logs']['rootLOG']
                    new_root_log_file = updated_config['logs']['rootLOG']

                    log_file = self.config['logs']['userLOG'] if self.usr != "root" else root_log_file
                    new_log_file = updated_config['logs']['userLOG'] if self.usr != "root" else new_root_log_file

                    new_log = False
                    if ll_level != new_ll_level:
                        new_log = True
                    if log_file != new_log_file and self.usr != "root":
                        new_log = True
                    if root_log_file != new_root_log_file and self.usr == "root":
                        new_log = True
                    if new_log:
                        # log_path = self.lclhome / "logs" / new_log_file

                        _, log_path = change_logger(new_log_file, new_ll_level, process_label="mainwindow")
                        self.log_path = new_log_file
                        self.ui.hudt.appendPlainText("Log level: " + new_ll_level)
                        self.ui.hudt.appendPlainText("Log file: " + str(log_path))
                    new_downloads = updated_downloads != self.downloads

                    if zipPATH != self.zipPATH or new_downloads or popPATH != self.popPATH:
                        if not check_utility(zipPATH, updated_downloads, popPATH):
                            raise ConfigurationError

                    if new_downloads:
                        self.downloads = updated_downloads
                        self.load_find_file_combo()

                    if proteusPATH != self.proteusPATH or new_nogo != nogo or new_suppress_list != suppress_list:
                        if not check_config(proteusPATH, new_nogo, new_suppress_list):
                            raise ConfigurationError

                    dspPATH = self.dspPATH
                    if dspEDITOR != self.dspEDITOR or new_dspPATH != dspPATH_frm:
                        dspPATH = ""
                        if dspEDITOR:
                            dspEDITOR = multi_value(dspEDITOR)
                            dspEDITOR, dspPATH = resolve_editor(dspEDITOR, new_dspPATH, toml)
                            if not dspEDITOR and not dspPATH:
                                raise ConfigurationError

                    uuid = None
                    idx = basedir

                    if idx != self.basedir:
                        if idx != "/":
                            idx = parse_drive(basedir)
                            uuid = get_mount_partuuid(basedir)
                            if not uuid:
                                raise DriveLogicError(f"couldnt find uuid for {basedir}")

                        drive_not_indexed = True

                        ix = self.basedirs.index_of_uuid(uuid)
                        if ix != -1:
                            _, drive, _ = self.basedirs.get_item(ix)
                            drive_idx = drive.suffix

                            if idx == drive_idx:
                                drive_not_indexed = False
                                self.update_basedir(basedir, drive_idx, drive, ix)  # load the drive
                                self.ui.sbasediridx.blockSignals(True)
                                self.ui.sbasediridx.setValue(ix)
                                self.ui.sbasediridx.blockSignals(False)
                            else:
                                self.basedirs.remove_item(ix)  # changed mounts

                        if drive_not_indexed:
                            cache_moved = False

                            CACHE_S, systimeche, drive_idx, driveTYPE = setup_drive_cache(
                                basedir, self.lclhome, self.dbopt, self.dbtarget, self.sj, self.toml_file, self.CACHE_S_str, driveTYPE,
                                self.usr, self.email, self.compLVL, j_settings=self.j_settings, partuuid=uuid, iqt=True
                            )
                            if not CACHE_S or not drive_idx or not self.j_settings:
                                raise DriveLogicError(f"Failed to build cache file for {basedir} in setup_drive_cache")

                            if idx != drive_idx:
                                cache_moved = True  # changed mounts

                            di = self.j_settings.get(drive_idx, {})
                            if not di:
                                self.ui.hudt.appendPlainText(f"the json in memory wasnt updated to suffix {basedir}")
                                raise DriveLogicError("couldnt apply changes")
                            if idx in self.j_settings:
                                if cache_moved:
                                    raise DriveLogicError(f"drive changed mounts and wasnt properly updated check {self.sj} and set to {drive_idx} for uuid {uuid}")

                            drive_info = self.j_settings[drive_idx].copy()
                            drive_uuid = drive_info.get("drive_partuuid")
                            parent_device = drive_info.get("parent_device")
                            dtype = drive_info.get("drive_type")
                            psEXTN = drive_info.get("proteusEXTN")

                            drive = BasedirDrive(drive_idx, parent_device, drive_uuid, basedir, dtype, CACHE_S, systimeche, psEXTN)
                            self.basedirs.add_item((drive_uuid, drive, drive_info))
                            r = self.basedirs.items - 1
                            self.update_basedir(basedir, drive_idx, drive, r)  # load the drive
                            self.ui.sbasediridx.setMaximum(r)
                            self.ui.sbasediridx.blockSignals(True)
                            self.ui.sbasediridx.setValue(r)
                            self.ui.sbasediridx.blockSignals(False)
                            self.basedirs.set_current_index(r, self.ui.basedirButton, self.basedir)

                    if hudCOLOR != self.hudCOLOR or hudSZE != self.hudSZE or hudFNT != self.hudFNT:
                        self.hudCOLOR = hudCOLOR
                        self.hudSZE = hudSZE
                        self.hudFNT = hudFNT
                        self.change_format(True)

                    if extensions != self.extensions:
                        fill_extensions(self.ui.combffile, extensions, prev_extensions=self.user_extensions)

                    self.driveTYPE = driveTYPE
                    self.dspEDITOR = dspEDITOR
                    self.dspPATH = dspPATH
                    self.popPATH = popPATH
                    self.email = email
                    self.ANALYTICSECT = ANALYTICSECT
                    self.FEEDBACK = FEEDBACK
                    self.compLVL = compLVL
                    self.MODULENAME = MODULENAME

                    self.proteusEXTN = ["[no extension]" if p == "" else p for p in proteusEXTN]
                    self.proteusPATH = proteusPATH
                    self.checksum = checksum
                    self.proteusSHIELD = proteusSHIELD
                    self.xzm = xzm
                    self.is_xzm_profile = xzm if self.basedir == "/" else False
                    self.EXCLDIRS = EXCLDIRS
                    self.zipPROGRAM = zipPROGRAM
                    self.zipPATH = zipPATH
                    self.extensions = extensions

                    if config_changed:
                        self.ui.hudt.appendPlainText("Config changed")   # ctext = cprint.cyan("Config changed") # self.ui.hudt.append_colored_output("\033[1;32mConfig changed\033[0m")  # green

            except ConfigurationError:
                dump_toml(None, self.config, toml)
            except DriveLogicError as e:
                dump_toml(None, self.config, toml)
                self.ui.hudt.appendPlainText(f"{type(e).__name__} {str(e)}")
                self.ui.hudt.appendPlainText("")
            except Exception as e:
                dump_toml(None, self.config, toml)
                if e:
                    self.ui.hudt.appendPlainText(
                        f"original settings restored. A backup of initial config was made to {self.tomldefault}. {e} {type(e).__name__}"
                        f"\n error logged {self.lclhome}/logs"
                    )
                logging.error("couldnt change configs", exc_info=True)

        self.config = None
        self.tomldefault_imt = None
        self.isexec = False

    def edit_config(self):
        if not (self.dspEDITOR and self.dspPATH):
            return
        toml = self.toml_file
        if os.path.isfile(toml):
            if not self.job_running(True):
                return
            self.config = load_toml(toml)
            if not self.config:
                self.ui.hudt.appendPlainText("failed to store original config unable to continue")
                self.isexec = False
                return

            self.tomldefault_imt = toml.stat().st_mtime_ns
            shutil.copy2(self.toml_file, self.tomldefault)

            # send stdout stderr to hudt from QProcess
            # def handle_stdout(self):
            #     data = self.proc.readAllStandardOutput().data().decode()
            #     self.logger.write(data)
            # def handle_stderr(self):
            #     data = self.proc.readAllStandardError().data().decode()
            #     self.logger.write(data)
            # end stdout stdderr
            # see handle_stdout stderr for QProcess
            # #self.proc = QProcess(self)
            # #self.result = None
            # #self.exit_result = None
            # #self.proc.readyReadStandardOutput.connect(self.handle_stdout)
            # #self.proc.readyReadStandardError.connect(self.handle_stderr)
            # # self.proc_timeout_timer.start(45000)
            # #self.proc.finished.connect(self.shut_proc)
            # #self.proc.finished.connect(self.cleanup_proc)
            # #self.proc.finished.connect(self.on_exit)
            # #self.proc.start(self.dspEDITOR, [str(self.toml_file)])   # subprocess.run([self.dspPATH, toml], capture_output=True, check=True, text=True)

            self.setEnabled(False)
            self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
            self.open_proc()
            self.proc.complete.connect(lambda code, _: self.update_ui_sn.emit(code, "editor"))
            self.proc.complete.connect(lambda code, _: self.set_config(code))
            self.proc.start_tomledit(self.dspEDITOR, [str(self.toml_file)])

        else:
            print(f"{self.dspEDITOR} no such config file: {toml}")

    # overview of configuration also debug generalized
    def show_status(self):

        ps = False  # check if profile made
        if table_loaded(self.dbopt, self.sys_a, self.ui.hudt):
            ps = True

        stat_value = {}

        stat_value['Exhibit'] = self.distro_name

        drive_id = self.j_settings[self.suffix].get("drive_id_model")
        model_type = self.j_settings[self.suffix].get("model_type")
        drive_type = self.j_settings[self.suffix].get("drive_type")
        #     return (device_name, parent_device, drive_id_model, model_type, drive_type)
        drive_model = None
        if not drive_id:
            # drive_id = "Unknown"
            drive_info = current_drive_type_model_check(self.basedir)
            if drive_info:
                _, _, drive_name, drive_model, _ = drive_info
            if drive_name:
                drive_id = drive_name
                update_j_settings({"drive_id_model": drive_name, "model_type": drive_model}, self.j_settings, self.suffix, self.sj)

        if not model_type and drive_model:
            # model_type = "Unknown"
            model_type = drive_model

        typeModel = f"{drive_id} / {model_type}"
        # log_path = filename_of_handler()
        stat_value.update({
            "Drive or basedir:": self.basedir,
            "Drive name/Type": typeModel,
            "Drive type": drive_type,
            "Empty1":  "",
            "Proteus Shield active": str(ps),
            "Checksum and Caching": "y" if self.checksum else "n",
            "Empty1":  "",
            "Empty2":  "",
            "Database": self.dbopt,
            "Last table": self.table,
            "Logfile":  self.log_path,
            "Debug line1": f"self.db is {self.db}",  # debuger
            "Debug line2": f'worker is {"active" if self.worker else ""}'
        })

        hudt = self.ui.hudt.appendPlainText
        # self.ui.hudt.clear()

        for key, value in stat_value.items():
            if not key.startswith("Debug") and not value:
                hudt('')
            elif key == "Exhibit":
                hudt(value)
            else:
                hudt(f"{key} {value}")

        if self.result is not None:
            hudt(f"Last Return: {self.result}")
            if self.exit_result != -1:
                hudt("QProcess")
                hudt(f"QExitStatus: {self.exit_result}")
            else:
                hudt("Thread")

        hudt('\n')

        if ps:
            psEXTN = self.j_settings.get(self.suffix, {}).get("proteusEXTN")
            if psEXTN:
                self.ps_is_xzm = ps_profile_type(psEXTN)
                extn = profile_to_str(psEXTN, self.ps_is_xzm)
                hudt(f"proteusTYPE: {'xzm' if self.ps_is_xzm else 'extn'}")
                hudt("proteusEXTN: " + extn)

        # """ stored drive values """
        # hudt('\n')
        # hudt("mem")

        # uuid, drive, keys = self.basedirs.get_current_item()
        # hudt(drive.suffix)
        # hudt(f"drive_partuuid: {drive.part_uuid}")
        # hudt(f"mount_of_index: {drive.moi}")
        # hudt(f"drive_type: {drive.drive_type}")
        # hudt(drive.cache_s)
        # hudt(drive.systimeche)
        # if drive.psextn:
        #     ps_is_xzm = ps_profile_type(drive.psextn)
        #     extn = profile_to_str(drive.psextn, ps_is_xzm)
        #     hudt(f"proteusEXTN {extn}")
        # else:
        #     hudt("proteusEXTN: None")
        # """ stored drive info values """
        # hudt("\n")
        # hudt("spinner")

        # for key, v in keys.items():
        #     hudt(f'{key}: {v}')
        # print(f'\nindex: {self.basedirs.current_index}\n')

    def set_dirtybit(self):
        self.dirtybit = True

    def save_notes(self, isexit=False):
        notes = self.ui.textEdit.toPlainText()
        nc = cnc(self.dbopt, self.compLVL)
        user_data_to_database(notes, self.ui.hudt, self.dbopt, self.dbtarget, self.email, nc, isexit=isexit, parent=self)

    def save_user_data(self, isexit=False):

        self.save_notes(isexit)

        last_drive = self.ui.combd.currentText()
        sr = self.ui.stime.value()
        ffr = self.ui.sffile.value()
        sout_put = self.ui.combftimeout.currentText()
        compout_put = self.ui.combffileout.currentText()
        update_data = {
            "last_drive": last_drive,
            "search_range": sr,
            "find_range": ffr,
            "search_output": sout_put,
            "compress_output": compout_put
        }
        if sr == 0:
            update_data["search_range"] = None
        if ffr == 0:
            update_data["find_range"] = None
        update_j_settings(update_data, self.j_settings, None, self.sj)

        # if it didnt change then there is no need to save to toml
        b = self.basedir
        if b != self.oldbasedir:
            kp = {
                "search": {"drive": self.basedir, "driveTYPE": self.driveTYPE}
            }
            update_toml_values(kp, self.toml_file)
            self.oldbasedir = b

        self.lastdrive = last_drive

        self.dirtybit = False

    def load_user_data(self):

        self.ui.textEdit.blockSignals(True)
        self.user_extensions = user_data_from_database(self.ui.hudt, self.ui.textEdit, self.ui.combffile, self.extensions, self.dbopt, self)
        self.ui.textEdit.blockSignals(False)

    def open_resource(self):
        # self.doc_window = open_html_resource(self, self.lclhome)
        open_html_resource(self, self.lclhome)

    def open_file_dialog(self, start_dir=""):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a File",
            str(start_dir),
            "All Files (*);;Image Files (*.png *.jpg *.jpeg)"
        )
        return file_path

    def reset_settings(self, retry=0, max_ret=5):
        if self.isexec:
            if retry < max_ret:
                QTimer.singleShot(100, lambda: self.reset_settings(retry + 1, max_ret))
            return
        self.ui.progressBAR.setValue(0)
        self.ui.dbprogressBAR.setValue(0)  # pg_2

        self.ui.combftimeout.setCurrentIndex(0)  # output
        rng = self.j_settings.get("search_range", 0)
        if rng != 0:
            self.ui.stime.setValue(self.ui.stime.minimum())  # top search time
        rng = self.j_settings.get("find_range", 0)
        if rng != 0:
            self.ui.sffile.setValue(self.ui.stime.minimum())  # find file time

        self.ui.combt.setCurrentIndex(0)  # ntfilter

        self.ui.ntlineEDIT.clear()
        self.ui.ffilet.clear()
        self.ui.hudt.clear()

        self.ui.diffchka.setChecked(False)
        self.ui.diffchkb.setChecked(False)
        self.ui.diffchkc.setChecked(False)

        # pg_2
        self.ui.dbchka.setChecked(False)
        # disable signals
        # self.ui.combd.setCurrentIndex(0) # signals
        # end pg_2

        # combo
        self.ui.combffile.setCurrentIndex(0)  # extension

        ix = 0
        if self.downloads.strip():
            ix = self.ui.combffileout.findText(self.downloads)
        if ix != -1:
            self.ui.combffileout.setCurrentIndex(ix)

        last_drive = self.ui.combd.currentText()
        if last_drive != self.lastdrive:
            idx = self.ui.combd.findText(self.lastdrive)
            if idx != -1:
                self.ui.combd.setCurrentIndex(idx)
        # end combo

    '''  jpg / crest '''

    def refresh_jpg(self):
        pixmap = QPixmap(self.picture)
        if not pixmap.isNull():
            scaled = pixmap.scaled(533, 300, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

            self.ui.jpgv.setPixmap(scaled)
        else:
            self.ui.hudt.appendPlainText(f"Failed to load image: {self.picture}")

    def refresh_crest(self):
        pixmap = QPixmap(self.crest)
        if pixmap.isNull():
            self.ui.hudt.appendPlainText(f"Failed to load crest: {self.crest}")
            return
        self.ui.jpgcr.setPixmap(pixmap)  # Set the pixmap on the label
        self.ui.jpgcr.setScaledContents(True)

    def emboss(self):

        if self.lastdir == self.crestdir:
            self.lastdir = self.lclhome
        crest = self.open_file_dialog(self.lastdir)
        if crest:

            self.lastdir = Path(os.path.dirname(crest))
            if valid_crest(self, crest):
                flnm_frm, ext = os.path.splitext(crest)
                outpath = flnm_frm + "_raised" + ext
                i = 1
                while os.path.exists(outpath):
                    outpath = f"{flnm_frm}_raised_{i}{ext}"
                    i += 1

                raised_image(crest, outpath)

    def load_jpg(self):

        # def reset_default(default_path, default_file, target):
        #     defaultflnm = os.path.join(default_path, default_file)
        #     shutil.copy(defaultflnm, target)
        # copy .bak to .png

        res = select_custom(
            self,
            "Choose an Option",
            "Please select an option:",
            "Jpg",
            "Reset",
            "Crest",
            "Reset"
        )

        if res == "jpg":
            jpg = self.open_file_dialog(self.lastdir)
            if jpg:
                self.lastdir = Path(os.path.dirname(jpg))
                if os.path.abspath(jpg) != os.path.abspath(self.picture):
                    image = QImage(jpg)
                    if image.isNull():
                        QMessageBox.warning(self, "Invalid Image", f"Cannot open the selected file:\n{jpg}")
                        return
                    image.save(str(self.userpicture), "PNG")  # orig
                    self.picture = self.userpicture
                    self.refresh_jpg()
        elif res == "defjpg":
            self.lastdir = None
            self.picture = self.jpgdir / self.jpgdefault
            # reset_default(self.jpgdir, self.jpgdefault, self.picture)  # orig
            self.refresh_jpg()
        elif res == "crest":

            crest = self.open_file_dialog(self.crestdir)  # crest dir always
            if crest:

                file_root = Path(os.path.dirname(crest))
                if file_root != self.crestdir:
                    self.lastdir = file_root

                if os.path.abspath(crest) != os.path.abspath(self.crest):  # dont reemboss the same crest in use
                    if valid_crest(self, crest):
                        shutil.copy(crest, self.usercrest)  # original would write to app dir
                        self.crest = self.usercrest
                        self.refresh_crest()

        elif res == "defcrest":
            self.lastdir = None
            # reset_default(self.crestdir, self.crestdefault, self.crest)
            self.crest = self.crestdir / self.crestdefault
            self.refresh_crest()

        elif res == "emboss":
            self.emboss()

    ''' Combo boxes '''

    # download button combo box
    def load_last_drive(self, last_drive=None):

        def set_drive(target):
            idx = self.ui.combd.findText(target)
            if idx != -1:
                self.ui.combd.setCurrentIndex(idx)
                self.lastdrive = target
                return True
            return False

        if last_drive:
            return set_drive(last_drive)

        drive = self.j_settings.get("last_drive")

        if not drive or not set_drive(drive):
            self.lastdrive = self.suffix
            self.ui.combd.setCurrentIndex(0)
            update_j_settings({"last_drive": self.suffix}, self.j_settings, None, self.sj)

    # return drive cache glob and default name
    def get_cache_pattern(self):
        systimename = name_of(self.CACHE_S_str)
        systime_pattern = systimename + "*"

        pattern = os.path.join(self.lclhome, systime_pattern)
        return pattern, systimename

    # values
    def load_saved_indexes(self):
        pattern, systimename = self.get_cache_pattern()

        filepath = glob.glob(pattern)

        a_drives = []
        current_base = self.suffix

        a_drives.append(current_base)

        for path in filepath:
            fname = name_of(path)  # normalize

            is_base_drive = fname == systimename  # case where the basedir is not /
            if is_base_drive:
                if current_base != "/":
                    a_drives.append("/")
                continue
            drive_name = fname.split("_", 1)[-1]
            if drive_name != fname and drive_name != current_base:  # our basedir was already added first
                a_drives.append(drive_name)
        return a_drives, systimename

    def fill_download_combo(self, drives):  # fill download combo box values
        combo = self.ui.combd
        combo.clear()
        combo.addItems(drives)
        combo.setCurrentIndex(0)

    def load_drives(self):
        a_drives, systimename = self.load_saved_indexes()
        self.fill_download_combo(a_drives)
        self.load_last_drive()
        return a_drives, systimename
    # end download button combo box

    def clear_extensions(self):
        if not self.job_running(True):
            return
        if clear_extn_tbl(self.dbopt, False):
            self.user_extensions = []
            if encr(self.dbopt, self.dbtarget, self.email, no_compression=self.nc, dcr=True):
                fill_extensions(self.ui.combffile, self.extensions)
        self.isexec = False

    def new_extension(self):
        if not self.job_running(True):
            return
        new_extension = add_new_extension(self.extensions, self.ui.hudt, self.ui.combffile, self.dbopt, self.dbtarget, self.email, self.nc, parent=self)
        if new_extension:
            self.user_extensions.append(new_extension)
        self.isexec = False

    def tableview_loaded(self):
        mdl = self.ui.tableView.model()
        if isinstance(mdl, QSortFilterProxyModel):
            mdl = mdl.sourceModel()
        return bool(self.db and mdl and mdl.rowCount())

    def init_page2(self):
        if self.tableview_loaded():  # self.db (first load) and has model rows
            return True
        else:
            if not os.path.isfile(self.dbopt):
                if not load_gpg(self.dbopt, self.dbtarget, self.ui.dbmainlabel):
                    return False
            return self.display_db('logs', False, False)

    def show_page_2(self):

        if not self.init_page2():
            self.ui.dbmainlabel.setText("Status: offline")

        self.ui.stackedWidget.setCurrentWidget(self.ui.page_2)

    def show_page(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.page)

    ''' QProcess '''  # Thread ln2089

    # Process
    #  for search,tsearch,nt,ffile,sys idx, sys scan, find downloads

    def cleanup_proc(self):
        if self.proc:
            self.proc.deleteLater()
            self.proc = None

    def open_proc(self, timeout=0):
        self.ui.progressBAR.setValue(0)
        self.result = None
        self.exit_result = None

        if timeout:
            self.proc_timeout_timer.start(timeout)

        self.proc.progress.connect(self.increment_progress)
        self.proc.log.connect(self.append_log)  # self.append_colored_output
        self.proc.error.connect(self.append_log)
        self.stop_proc_sn.connect(self.proc.stop)
        self.proc.complete.connect(self.shut_proc)
        self.proc.complete.connect(self.cleanup_proc)
        self.isexec = True
        self.ui.sbasediridx.setEnabled(False)

    def proc_dbui(self):
        self.ui.dbprogressBAR.setValue(0)
        self.proc.progress.connect(self.increment_db_progress)
        self.proc.status.connect(self.update_db_status)

    @Slot(int, int)
    def shut_proc(self, exit_code, exit_status):
        if exit_code != 4:
            if self.proc_timeout_timer.isActive():
                self.proc_timeout_sn.emit()

        self.ui.sbasediridx.setEnabled(True)
        self.isexec = False

        self.is_user_abort = False

        self.result = exit_code
        self.exit_result = exit_status

        if exit_code != 0:  # and not exit_status != QProcess.NormalExit:
            exit_str = str(exit_status)
            if exit_code == 7:
                self.ui.hudt.appendPlainText(f"QProcess replied to exit request Exit status: {exit_str}")
            else:
                self.ui.hudt.appendPlainText(f"Exit code: {exit_code}, Exit status: {exit_str}")
        self.ui.resetButton.setEnabled(True)

    def proc_timeout(self):
        if getattr(self, "proc", None) and self.proc.is_running():

            self.ui.hudt.appendPlainText("Requesting process stop due to timeout...")
            self.stop_proc_sn.emit()

    #
    # End Process

    ''' Main search recentchangessearch.py'''

    # top search
    def search(self, output, THETIME, argf):
        if not self.job_running():
            return

        method = ""
        SRCDIR = "noarguser"

        if output == "/tmp":
            argone = THETIME
            THETIME = SRCDIR
            SRCDIR = "noarguser"
            method = "rnt"
        else:
            argone = "search"

        scanidx = self.ui.diffchkb.isChecked()
        postop = self.ui.diffchka.checkState() == Qt.CheckState.Checked
        showDiff = self.ui.diffchkc.isChecked()

        if postop:
            doctrine = os.path.join(self.USRDIR, "doctrine.tsv")
            if os.path.exists(doctrine):
                self.ui.hudt.appendPlainText("A file doctrine already exists skipping")

        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(360000)
        self.proc.set_task(self.file_out, self.dspEDITOR, self.dspPATH, self.tempdir)

        ismcore = True
        self.proc.set_mcore(ismcore)  # uses multicore dont cancel while those processes are running   between 21 - 59 % and 66 and 89%
        if postop or scanidx:
            self.proc.complete.connect(lambda code, _: self.update_ui_sn.emit(code, "search"))

        # s_path = os.path.join(self.lclhome, "recentchangessearch.py")
        args = [
            'recentchangessearch.py',
            str(argone),
            str(THETIME),
            str(self.usr),
            str(self.PWD),
            str(argf),
            str(method),
            "True",
            str(self.basedir),
            str(self.dbopt),
            str(self.CACHE_S),
            str(postop),
            str(scanidx),
            str(showDiff),
            str(self.dspPATH)
        ]

        is_search = False
        self.proc.start_pyprocess(str(self.dispatch), args, dbtarget=self.dbtarget, user=self.usr, email=self.email, is_search=is_search, is_postop=postop, is_scanIDX=scanidx, parent=self)

    # fork
    # 5 Min, 5 Min Filtered, Search by time and . Filtered
    def tsearch(self, clicked_button, filtered=None):
        output = ""
        argf = ""

        if filtered:
            output = "Desktop"
            argf = "filtered"

        if clicked_button == self.ui.stimebf or clicked_button == self.ui.stimeb:
            THETIME = self.ui.stime.value()
            if THETIME == 0:
                self.ui.hudt.appendPlainText("Time cant be 0.")
                return
        else:
            THETIME = "noarguser"

        if clicked_button == self.ui.stimeb or clicked_button == self.ui.ftimeb:
            output = self.ui.combftimeout.currentText()  # /tmp or Downloads
        # print(output)
        # return
        self.search(output, THETIME, argf)

    # fork
    def ntsearch(self):
        clicked_button = self.sender()
        if clicked_button == self.ui.ntbrowseb:
            fpath = self.open_file_dialog()  # Add folders button***
            #
            if fpath:
                self.ui.ntlineEDIT.setText(fpath)
            return
        elif clicked_button == self.ui.ntbrowseb2:
            fpath = QFileDialog.getExistingDirectory(self, "Select a folder")
            if fpath:
                self.ui.ntlineEDIT.setText(fpath)
            return

        fpath = self.ui.ntlineEDIT.text().strip()
        if not fpath:
            window_message(self, "Browse to select a file.", "No target")
            return
        elif not os.path.exists(fpath):
            window_message(self, "please enter valid filename.", "NSF")
            return

        output = "search"
        THETIME = fpath

        argf = self.ui.combt.currentText()
        if argf == "Filtered":
            argf = ""
        else:
            argf = "filtered"

        self.search(output, THETIME, argf)

    # Find file
    def ffile(self, compress, time_range=0):
        if not self.job_running():
            return

        extension = self.ui.combffile.currentText()
        if extension:
            if not extension.startswith("."):
                self.isexec = False
                self.ui.hudt.appendPlainText(f"invalid extension {extension}")
                return
        fpath = self.ui.ffilet.text().strip()
        if not (fpath or extension):
            self.isexec = False
            window_message(self, "please enter a filename and or extension")
            return

        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(120000)

        if compress:
            # print("compressing")
            downloads = self.ui.combffileout.currentText()
            if downloads == "Downloads":
                downloads = self.USRDIR
            # else:
            #     downloads = self.lclhome

            self.proc.set_compress(self.zipPROGRAM, self.zipPATH, self.USRDIR, downloads)  # compress button?
        else:
            range_value = self.ui.sffile.value()
            if range_value:
                try:
                    range_float = time_convert(int(range_value), 60, 2)
                except ValueError:
                    self.ui.hudt.appendPlainText("Invalid number")
                    return
                if range_float:
                    time_range = range_float
                    # elif ok:
                    #     self.ui.hudt.appendPlainText("specify 0 to compress all results. or enter a time range to compress")

        self.proc.set_range(str(time_range))
        self.proc.set_task(self.file_out, self.dspEDITOR, self.dspPATH, self.tempdir)

        # cmd = os.path.join(self.lclhome, "findfile.py")  # this example would be run python on findfile.py if not using polkit  # Note: "src",  # find script source if meipath ect. qt doesnt run as root and uses polkit helper\wrapper.
        # using polkit set_recent_helper

        self.proc.start_pyprocess(str(self.dispatch), ["findfile.py", fpath, extension, self.basedir, self.usr, self.dspEDITOR, self.dspPATH, self.tempdir], dbtarget=self.dbtarget, user=self.usr, email=self.email)

    # compress
    def ffcompress(self):
        fpath = self.ui.ffilet.text().strip()
        extension = self.ui.combffile.currentText()
        if not (fpath or extension):
            return

        zip_pth = None

        zipPROGRAM = self.zipPROGRAM
        if not zipPROGRAM:
            self.ui.hudt.appendPlainText("No zipPROGRAM specified")
            return

        if not self.zipPATH:
            if zipPROGRAM == "zip":
                zip_pth = shutil.which("zip")

            elif zipPROGRAM == "tar":
                zip_pth = shutil.which("tar")

            if zip_pth:
                self.zipPATH = zip_pth
            else:
                window_message(self, "no zipPATH specified and failed to find a path for zip or tar on system", "Info")
                return

        time_range = self.ui.sffile.value()
        # range_value
        # if range_value:
        #     time_range = range_value
        # else:
        # time_range, ok = window_input(self, "Enter search time", "Seconds:")
        # if ok and time_range:
        # elif ok:
        #     self.ui.hudt.appendPlainText("specify 0 to compress all results. or enter a time range to compress")
        #     return
        try:
            range_float = time_convert(int(time_range), 60, 2)
            if range_float == 0:
                uinpt = window_prompt(self, "Compress archive", "You have entered 0. This will compress all file matches. Continue", "Yes", "No")
                if not uinpt:
                    return
            self.ffile(True, range_float)
        except ValueError:
            self.ui.hudt.appendPlainText("Invalid number")
            return
    #
    # End Find file

    def get_newdrive(self):
        dialog = DriveSelectorDialog(self.basedir, self.j_settings, parent=self)

        if dialog.exec():
            target, uuid = dialog.selected_drive()
            if os.path.exists(target):
                return target, uuid
            else:
                window_message(self, f"selected {target} not found.")
        return None

    ''' Proteus Shield / System Profile '''

    # Main db task
    # Set hardlinks
    # also contains Index drive aka Find Downloads
    # System profile / Proteus Shield
    # page_2
    # fork set hardlinks button

    def set_hardlinks(self):
        if not self.job_running(True):
            return
        if not table_loaded(self.dbopt, 'logs', self.ui.hudt) or not has_log_data(self.dbopt, self.ui.hudt, parent=self):
            self.isexec = False
            return

        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(120000)
        self.proc_dbui()  # label/pbar
        self.proc.status.connect(self.update_db_status)  # reset label

        self.proc.complete.connect(lambda code, _: self.reload_database_sn.emit(code, False, ("logs",)))

        args = [
            'dirwalker.py',
            'hardlink',
            self.dbopt,
            self.dbtarget,
            self.basedir,
            self.usr,
            str(self.uid),
            str(self.gid),
            self.tempdir,
            self.email,
            str(self.compLVL)
        ]
        # print(args)
        # self.isexec = False
        # return
        self.proc.start_pyprocess(str(self.dispatch), args, database=self.dbopt, dbtarget=self.dbtarget, user=self.usr, email=self.email, status_message="Set hardlinks")

    # Build IDX &
    # Drive index
    #
    # Moved here as database integrated. central hub for core feature system index.   QProcess start logic above. Thread start logic below

    # Main Scan IDX
    def scan_idx(self):
        if not self.job_running():
            return

        if not dbtable_has_data(self.dbopt, self.sys_a):
            self.isexec = False
            return  # check if a sys profile exists

        basedir = self.basedir
        email = self.email
        diff_file = get_diff_file(self.USRDIR, self.MODULENAME)

        showDiff = self.ui.dbchka.isChecked()

        self.ui.hudt.append_colored_output("\033[1;32m\nSystem index scan..\033[0m")

        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(300000)
        self.proc_dbui()
        self.proc.complete.connect(lambda code, _: self.update_ui_sn.emit(code, "scan"))
        ismcore = True
        self.proc.set_mcore(ismcore)  # os.scandir workers cant be stopped flag. leave process open until complete
        # self.proc.status.connect(self.update_db_status)

        args = [
            'dirwalker.py',
            'scan',
            self.dbopt,
            self.dbtarget,
            basedir,
            self.usr,
            diff_file,
            self.CACHE_S,
            email,
            str(self.ANALYTICSECT),
            str(showDiff),
            str(self.compLVL),
            'True',
            'True'
        ]
        # cmd = os.path.join(self.lclhome, "dirwalker.py")  # , "src"
        self.ui.dbmainlabel.setText("Scanning idx")
        self.proc.start_pyprocess(str(self.dispatch), args, database=self.dbopt, dbtarget=self.dbtarget, user=self.usr, email=self.email, status_message="Index scan")

    # Main Build IDX
    def run_build_idx(self, basedir, CACHE_S, stsmsg, tables, idx_drive=False, drive_value=None):

        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(300000)

        ismcore = True
        drive_idx = None

        if idx_drive:
            drive_idx = drive_value
            self.proc.complete.connect(lambda code, _, d_value=drive_value: self.reload_drives(code, None, d_value))

        else:  # connect pg_2
            self.proc_dbui()  # label/pbar
            # self.proc.status.connect(self.update_db_status)  # reset label

        self.proc.complete.connect(lambda code, _, table_tuple=tables: self.reload_database_sn.emit(code, False, table_tuple))
        self.proc.complete.connect(lambda code, _: self.reload_sj_sn.emit(code, drive_idx, 'add', False))
        self.proc.set_mcore(ismcore)  # cant stop until some point

        # cmd = os.path.join(self.lclhome, "dirwalker.py")
        # sysprofiletwo.py
        args = [
            'dirwalker.py',
            'build',
            self.dbopt,
            self.dbtarget,
            basedir,
            self.usr,
            CACHE_S,
            self.email,
            str(self.ANALYTICSECT),
            str(idx_drive),
            str(self.compLVL),
            'True'
        ]

        self.proc.start_pyprocess(str(self.dispatch), args, database=self.dbopt, dbtarget=self.dbtarget, user=self.usr, email=self.email, status_message=stsmsg)

    # fork build button pg2
    def build_idx(self):
        if not self.job_running():
            return

        rlt = has_sys_data(self.dbopt, self.ui.hudt, self.sys_a, "Previous sys profile has to be cleared. Continue?", parent=self)  # prompt to delete
        if rlt is None:
            self.isexec = False
            return

        if self.is_xzm_profile:
            self.xzm_obj = XzmProfile(self.basedir)  # create a reference build it see if it errors before starting thread. commit profile after checking return

        tables = (self.sys_a, self.sys_b, self.cache_table, self.systimeche)

        self.ui.hudt.appendPlainText("Hashing system profile...")
        turbo = 'mc' if self.driveTYPE.lower() == "ssd" else 'default'  # grab it from j_settings?
        self.ui.hudt.appendPlainText(f"Turbo is: {turbo}\n")

        self.ui.dbmainlabel.setText("Building profile")
        self.run_build_idx(self.basedir, self.CACHE_S, "System profile", tables)

    # fork       pg1
    # add index button page 1 '''
    def idx_drive(self):
        if self.isexec:
            window_message(self, "there is a current job started.", "Execution")
            return
        drive_info = self.get_newdrive()
        if not drive_info:
            return
        drive, drive_uuid = drive_info
        if not drive:
            return
        if drive == self.basedir:
            self.ui.hudt.appendPlainText(f"{drive} sys basedir Requires build idx on db page")
            return

        idx_suffix = "/"
        if drive != "/":
            uuid = drive_uuid
            idx_suffix = get_new_idx_suffix(drive, self.j_settings)

        CACHE_S, systimeche, _ = get_cache_s(drive, self.CACHE_S_str, idx_suffix)
        sys_tables, cache_table, _ = get_idx_tables(drive, self.CACHE_S_str, idx_suffix)

        tables = (*sys_tables, cache_table, systimeche)  # for updating ui elements

        if dbtable_has_data(self.dbopt, sys_tables[0]):
            self.ui.hudt.appendPlainText(f"drive {drive} has sys profile. switch basedir in config.toml and then clear IDX and rebuild on page2")
            return

        if drive != "/":
            update_dict({"drive_partuuid": uuid}, self.j_settings, idx_suffix)

        drive_type = setup_drive_settings(drive, idx_suffix, None, None, user_json=self.sj, j_settings=self.j_settings, idx_drive=True)
        if drive_type is None:
            update_j_settings(None, self.j_settings, idx_suffix, self.sj)
            self.ui.hudt.appendPlainText(f"Unable to locate drive. quitting {drive}")
            return

        self.isexec = True
        self.ui.hudt.appendPlainText(f"Indexing {drive}")
        self.run_build_idx(drive, CACHE_S, f"Drive {drive} profile", tables, True, idx_suffix)

    # remove index button page 1 '''
    def rmv_idx_drive(self):
        drive = self.ui.combd.currentText()
        if drive == self.suffix or drive == "/":
            return

        idx = self.ui.combd.currentIndex()

        idx_suffix = self.j_settings.get(drive, {})
        if idx_suffix:
            CACHE_S, systimeche_table, _ = get_cache_s(drive, self.CACHE_S_str, drive)
            sys_tables, cache_table, _ = get_idx_tables(drive, self.CACHE_S_str, drive)

            self.clear_sys(drive, CACHE_S, sys_tables, cache_table, systimeche_table, idx)  # remove the drive cache .gpg file. call a thread as the database delete can freeze ui

        else:
            self.ui.combd.removeItem(idx)
            systimeche = name_of(self.CACHE_S_str)
            cache_file = systimeche + f"_{drive}.gpg"
            cache_file = os.path.join(self.lclhome, cache_file)
            removefile(cache_file)
            self.load_last_drive()

    # downloads button page 1
    # find downloads or files with the directory cache. os.scandir recursion
    def find_downloads(self, basedir="/"):
        if not self.job_running():
            return

        is_idx = False

        CACHE_S = self.CACHE_S
        systimeche = self.systimeche

        drive = self.ui.combd.currentText()  # index selected

        mnt = None
        if drive != self.suffix:

            is_idx = True

            if drive not in self.j_settings:
                self.isexec = False
                self.ui.hudt.appendPlainText(f"Failed to find {drive} in {self.sj}")
                return

            CACHE_S, systimeche, _ = get_cache_s(drive, self.CACHE_S_str, drive)
            basedir = "/"
            if drive != "/":
                uuid = self.j_settings.get(drive, {}).get("drive_partuuid")
                mnt = get_mount_from_partuuid(uuid) if uuid else None
                if mnt:
                    basedir = mnt  # if the mount point changed you can rename it with a prompt but its easy enough to reindex
                else:
                    self.isexec = False
                    self.ui.hudt.appendPlainText(f"couldnt find drive mount for {drive} partuuid: {uuid}")
                    return

        if not dbtable_has_data(self.dbopt, systimeche):  # indexed?
            self.isexec = False
            msg = f"{basedir} not indexed."
            if not is_idx:
                self.ui.hudt.appendPlainText(f"{msg} requires Build idx")
            else:
                self.ui.hudt.appendPlainText(msg)
            return

        if not os.path.isfile(CACHE_S):  # missing cache?
            self.ui.hudt.appendPlainText(f"Error cache not found. {'re index drive' if is_idx else 'requires rebuild IDX'}, file not found: {CACHE_S}")
            self.isexec = False
            if is_idx:  # dont remove / or basedir
                ix = self.ui.combd.findText(drive)
                if ix != -1:
                    self.ui.combd.removeItem(ix)
                    update_j_settings({"last_drive": self.suffix}, self.j_settings, None, self.sj)
                    if self.ui.combd.count() > 0:
                        self.ui.combd.setCurrentIndex(0)
            return

        drive_type = self.j_settings.get(drive, {}).get("drive_type")
        if not drive_type:
            drive_type = "HDD"

        # cmd = os.path.join(self.lclhome, "dirwalker.py")  # "src",
        self.proc = ProcessHandler(self.lclhome, self.xdg_runtime, self.ui.dbmainlabel.text(), self.is_polkit)
        self.open_proc(120000)
        self.proc.set_task(self.file_out, self.dspEDITOR, self.dspPATH, self.tempdir)

        # disable stop button ****
        ismcore = True
        self.proc.set_mcore(ismcore)
        args = [
            'dirwalker.py',
            'downloads',
            self.dbopt,
            self.dbtarget,
            basedir,
            self.usr, drive_type,
            self.tempdir,
            CACHE_S,
            self.dspEDITOR,
            self.dspPATH,
            self.email,
            str(self.ANALYTICSECT),
            str(self.compLVL)
        ]

        self.proc.start_pyprocess(str(self.dispatch), args, database=self.dbopt, dbtarget=self.dbtarget, user=self.usr, email=self.email)

        #
        # End Main db task
        #
    ''' Database '''

    # database

    # populate a table in tableView on pg_2
    #
    # first start the .db decrypted from __init__. Primary focus is to minimally load the database.
    # only load the main elements once and set self.db to True. Then user selects tables from the drop
    # down box to reload.
    #
    # methods can reload the page or the table selector. switching to page 2 only will load once.
    #
    def display_db(self, table="logs", refresh=False, only_combo=False):

        sender = self.sender()
        dybit = self.dirtybit

        if sender != self.ui.combdb and self.tableview_loaded() and not refresh:
            return True
        if not self.job_running(database=True, no_popup=True):
            return False
        if not only_combo:
            self.ui.combdb.setEnabled(False)
            # QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        def load_combdb():
            cd = self.ui.combdb
            c_text = cd.currentText()
            cd.blockSignals(True)
            cd.clear()
            tbl = sort_right(tables, self.cache_table, self.systimeche, self.suffix)
            cd.addItems(tbl)

            ix = cd.findText('extn')  # dont display extn table
            if ix != -1:
                cd.removeItem(ix)

            ix = cd.findText(c_text)  # restore prev setting
            if ix != -1:
                cd.setCurrentIndex(ix)
            else:
                if cd.count() > 0:
                    cd.setCurrentIndex(0)
                    self.table = cd.currentText()
            cd.blockSignals(False)

        # set initial no compression
        if self.nc is None and self.db:
            self.nc = cnc(self.dbopt, self.compLVL)

        db = None
        query = None
        res = False

        try:

            db, err = get_conn(self.dbopt, "sq_7")
            if err:
                self.ui.hudt.appendPlainText(f"Failed to display {table} table: {err}")
                self.ui.tableView.setModel(None)
            else:
                self.ui.dbmainb2.setEnabled(False)
                if table == "sys" or table.startswith("sys_") or table.startswith("cache"):
                    self.sys_step = table
                    self.ui.dbmainb2.setEnabled(True)

                tables = db.tables()
                if tables:

                    res = True
                    self.db = True
                    load_combdb()  # Update combobox

                    if not only_combo:
                        self.table = table
                        self.init_table_model_proxy()
                        self.init_dbstreamer(table, batch_size=500)
                        self.worker2.start()

                    if dybit:  # Anything to append?
                        query = QSqlQuery(db)
                        self.dirtybit = False
                        # last_drive = self.ui.combd.currentText()  # just save notes dont overwrite saved settings
                        # update_j_settings({"last_drive": last_drive}, self.j_settings, None, self.sj)
                        notes = self.ui.textEdit.toPlainText()
                        self.nc = cnc(self.dbopt, self.compLVL)
                        commit_note(self.ui.hudt, notes, self.email, query)

        except Exception as e:
            res = False
            self.ui.hudt.appendPlainText(f"failure in display_db err: {e} \n {traceback.format_exc()}")

        finally:
            if query:
                del query
            if db:
                db.close()

        if res and dybit:  # Released the connection above to append, otherwise locked out
            if not encr(self.dbopt, self.dbtarget, self.email, no_compression=self.nc, dcr=True):
                self.ui.hudt.appendPlainText("Problem rencrypting notes.")

        if not (refresh or only_combo):  # Only update connection status on combo selection
            if self._status_reset_timer.isActive():
                self._status_reset_timer.stop()
            self.ui.dbmainlabel.setText("Status: Connected" if res else "Status: offline")

        if not (only_combo or res) and getattr(self, 'worker2', None) is None:
            self.isexec = False
            self.ui.combdb.setEnabled(True)
            # QApplication.restoreOverrideCursor()
        elif only_combo:
            self.isexec = False
        return res

    # db and db Sql helpers
    def init_dbstreamer(self, table, sys_tables=None, cache_tables=None, superimpose=False, batch_size=500):

        self.result = None
        self.exit_result = -1
        self.worker2 = DbWorkerIncremental(self.dbopt, table, sys_tables, cache_tables, superimpose=superimpose, batch_size=batch_size)
        self.worker2.log.connect(self.append_log)
        self.worker2.exception.connect(
            lambda t, v, tb: sys.excepthook(t, v, tb)
        )
        self.worker2.headers_ready.connect(lambda headers, tname=table: self.on_header_values(headers, tname))
        self.worker2.batch_ready.connect(self.append_rows_to_model)
        self.worker2.finished_loading.connect(
            lambda code, tname=table: self.on_load_finished(tname, code)
        )
        self.worker2.finished.connect(self.worker2.deleteLater)

    def init_table_model_proxy(self):
        self.model = QStandardItemModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.ui.tableView.setModel(self.proxy)
        self.ui.tableView.setSortingEnabled(False)

    # main dn draw set appropriate sizes
    def on_header_values(self, headers, table):
        self.model.setHorizontalHeaderLabels(headers)
        header = self.ui.tableView.horizontalHeader()
        # header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # uniform width for all columns
        # fixed_width = 150
        # for i in range(len(headers)):
        # header.resizeSection(i, fixed_width)

        # maximum width 1000

        if table in ('sqlite_sequence', "stats"):
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            for i in range(len(headers)):
                width = header.sectionSize(i)
                if width > 1000:
                    header.resizeSection(i, 1000)
        else:
            systimeche = name_of(self.CACHE_S_str)
            if 'cache_' in table or systimeche in table:
                column_widths = [60, 135, 1100, 75, 75, 75, 75, 215]

            else:
                # per-table per-column width list
                column_widths = [60, 135, 1100, 135, 130, 135, 215, 75, 50, 115, 115, 50, 50, 135, 135, 70]
            # else:
                # column_widths = [100] * len(headers)
            for i, w in enumerate(column_widths):
                if i < len(headers):
                    header.resizeSection(i, w)

    @Slot(list)
    def append_rows_to_model(self, rows):
        for row_data in rows:
            items = []
            for val in row_data:
                item = QStandardItem(str(val))
                if isinstance(val, (int, float)):
                    item.setData(val, Qt.ItemDataRole.DisplayRole)
                items.append(item)
            self.model.appendRow(items)

    def on_load_finished(self, table, code):
        if code != 7:
            # if table == "logs":
            #     self.ui.tableView.sortByColumn(0, Qt.SortOrder.AscendingOrder)
            self.ui.tableView.setSortingEnabled(True)
            self.proxy.sort(-1)
        self.result = code
        self.ui.combdb.setEnabled(True)
        # QApplication.restoreOverrideCursor()
        self.worker2 = None
        self.isexec = False

    def reload_table(self):
        self.display_db(self.table, True, False)

    def super_impose(self):
        if not self.job_running(database=True, no_popup=True):
            return
        if not self.sys_step:
            return

        cache_tables = None
        sys_tables = None

        # self.ui.combdb.setEnabled(False)
        # QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:

            self.init_table_model_proxy()

            s = self.sys_step
            prefix, key = parse_suffix(s)

            if s.startswith("cache"):
                cache_table = s

                systimeche = name_of(self.CACHE_S_str)
                if key:
                    systimeche = systimeche + "_" + key

                cache_tables = (s, systimeche)
                table = cache_table + "_" + systimeche
            else:
                sys_a = s
                # sys_sda3
                # sys2_sda3
                sys_b = sys_a + "2"
                if key:
                    sys_b = prefix + "2" + "_" + key  # sys_b + "_" + key
                sys_tables = (sys_a, sys_b)
                table = sys_a + "_" + sys_b
            combo = self.ui.combdb
            if table not in [combo.itemText(i) for i in range(combo.count())]:
                combo.blockSignals(True)
                combo.addItem(table)
                ix = combo.findText(table)
                if ix != -1:
                    combo.setCurrentIndex(ix)
                combo.blockSignals(False)
        except Exception:
            logging.error("an error occured in super_impose", exc_info=True)
            self.isexec = False
            self.ui.combdb.setEnabled(True)
            # QApplication.restoreOverrideCursor()
            return

        self.init_dbstreamer(table, sys_tables, cache_tables, superimpose=True, batch_size=500)
        self.worker2.start()

    # end Sql helpers

    ''' Thread '''

    # Thread
    #
    def job_running(self, database=False, no_popup=False):
        if not self.isexec:
            self.isexec = True
            if database:
                if os.path.isfile(self.dbopt):
                    return True
                else:
                    self.isexec = False
                    self.ui.hudt.appendPlainText("No database loaded.")
            else:
                return True
        else:
            if not no_popup:
                window_message(self, "there is a current job started.", "Execution")
        return False

    def cleanup_thread(self):
        if self.worker_thread:
            self.worker_thread.deleteLater()
            self.worker_thread = None
        if self.worker:
            self.worker = None

    def init_thread(self):
        self.worker.log.connect(self.append_log)
        self.worker.complete.connect(lambda code: self.finalize(code))
        self.worker.complete.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.cleanup_thread)

    def open_trd(self, timeout=60000):
        self.isexec = True
        self.ui.sbasediridx.setEnabled(False)
        self.result = None
        self.exit_result = -1
        self.timeout_timer.start(timeout)

        self.stop_worker_sn.connect(self.worker.stop)  # type: ignore
        self.worker_thread.start()

    @Slot(int)
    def finalize(self, code):
        if code != 4:
            if self.timeout_timer.isActive():
                self.worker_timeout_sn.emit()  # stop the timer from main gui

        try:
            self.stop_worker_sn.disconnect()
        except (TypeError, RuntimeError):
            pass

        self.is_user_abort = False

        self.result = code

        if code != 0:
            # 7 stop requested return
            #
            hudt = self.ui.hudt
            if code == 7:
                hudt.appendPlainText("worker replied to stop")
            elif code != 4:
                hudt.appendPlainText(f"Exit code {code}")
            else:
                hudt.appendPlainText(f"Worker exited with error code {code}")
        # self.worker = None
        self.ui.sbasediridx.setEnabled(True)
        self.isexec = False

    def thread_timeout(self):
        t = getattr(self, "worker_thread", None)
        if getattr(self, "worker", None) and isinstance(t, QThread) and t.isRunning():
            self.ui.hudt.appendPlainText("Thread time out forcing quit")
            self.stop_worker_sn.emit()
            t.quit()
            QTimer.singleShot(5000, self._fk_thread)
        else:
            self.ui.hudt.appendPlainText("Thread closed unexpectedly")
            self.finalize(4)

    def _fk_thread(self):
        try:
            t = getattr(self, "worker_thread", None)
            if isinstance(t, QThread) and t.isRunning():
                self.ui.hudt.appendPlainText("Thread did not quit after timeout")
                QTimer.singleShot(2000, self._fk_thread)
                return

        except (RuntimeError, AttributeError) as e:
            logging.error("Error in _fk_thread on thread timeout: %s", e, exc_info=True)
        self.finalize(4)
    #
    # end Thread

    # Thread types

    # Db
    def start_cleartrd(self):
        self.worker_thread = QThread()
        self.worker = ClearWorker(self.lclhome, self.home_dir, self.dbopt, self.dbtarget, self.usr, self.email, self.flth, self.compLVL)
        self.worker.moveToThread(self.worker_thread)

        self.worker.progress.connect(self.increment_db_progress)
        self.worker.no_compression.connect(self.set_nc)
        self.ui.dbprogressBAR.setValue(0)
        self.worker.exception.connect(
            lambda t, v, tb: sys.excepthook(t, v, tb)
        )
        self.init_thread()
    # end Thread types

    # general tasks db

    def _run_clear_task(self, worker_method, set_task=None):

        self.worker_thread.started.connect(worker_method)
        if set_task:  # pass in
            self.worker.set_task(*set_task)
        self.open_trd()

    # fork query button
    def execute_query(self):
        if not self.job_running(True):
            return
        if self.table == "logs" and not self.tableview_loaded() or not table_loaded(self.dbopt, 'logs', self.ui.hudt):
            self.isexec = False
            return
        self.start_cleartrd()
        self.worker.progress.connect(self.increment_progress)
        self.worker.status.connect(self.update_db_status)
        self.ui.hudt.appendPlainText("\n")
        self._run_clear_task(self.worker.run_query)

    # fork cache clear button
    def clear_cache(self):
        if not self.job_running(True):
            return
        if not table_loaded(self.dbopt, 'logs', self.ui.hudt):
            self.isexec = False
            return
        self.start_cleartrd()
        self.worker.status.connect(self.update_db_status)  # db label pg2
        self.worker.complete.connect(lambda code: self.reload_database_sn.emit(code, False, ("logs",)))  # db reload pg2
        self._run_clear_task(self.worker.run_cacheclr, None)

    # fork clear IDX button
    # From _pg2 or remove index button on page 1. the former is a basedir the latter is a drive index from find downloads
    def clear_sys(self, drive, cache_s=None, sys_tables=None, cache_table=None, systimeche=None, idx=None):
        if not self.job_running(True):
            return False
        prompt_v = "Previous sys profile has to be cleared. Continue?" if not idx else f"drive {drive} has a sys profile and has to be cleared. Continue?"

        cache_s = cache_s or self.CACHE_S
        sys_tables = sys_tables or (self.sys_a, self.sys_b)
        cache_table = cache_table or self.cache_table
        systimeche = systimeche or self.systimeche

        sys_a = sys_tables[0]
        sys_b = sys_tables[1]

        tables = (sys_a, sys_b, cache_table, systimeche)

        # if it is basedir is there anything to clear?
        if drive == self.suffix:
            if not table_loaded(self.dbopt, sys_tables[0], self.ui.hudt):
                self.isexec = False
                return

        # if it is a drive index that is another basedir it could have a system profile. prompt to delete or exit. if an error exit
        drive_idx = None
        is_ps = False
        if idx:
            drive_idx = drive
            is_ps = has_sys_data(self.dbopt, self.ui.hudt, sys_tables[0], prompt_v, parent=self)
            if is_ps is None:
                self.isexec = False
                return

        self.start_cleartrd()
        self.worker.status.connect(self.update_db_status)  # db label pg2
        self.worker.complete.connect(lambda code, tables=tables: self.reload_database_sn.emit(code, True, tables))

        if idx:
            self.worker.complete.connect(lambda code, idx=idx: self.reload_drives_sn.emit(code, idx, drive))

        self.worker.complete.connect(lambda code: self.reload_sj_sn.emit(code, drive_idx, 'rmv', is_ps))

        self._run_clear_task(self.worker.run_sysclear, [cache_s, sys_tables, cache_table, systimeche])

    #
    # end general tasks db

    # On completion Database Helpers

    # On completion of a db task either update the table or only combo depending if the user is on that page
    @Slot(int, bool, object)
    def reload_database(self, code, is_remove=False, tables=('logs',)):
        if code == 0:

            only_combo = False
            current_table = self.ui.combdb.currentText()  # if the user is on the selected table we want to reload it.

            if is_remove:
                only_combo = True
            else:
                if current_table not in tables:
                    only_combo = True  # the user is not on that table just refresh combobox selector

            drt = self.database_reload_timer
            if not drt.isActive():
                if self._reload_connection is not None:
                    drt.timeout.disconnect(self._reload_connection)

                self._reload_connection = drt.timeout.connect(
                    lambda: self.display_db(current_table, refresh=True, only_combo=only_combo)
                )
                drt.start(5000)

        elif code == 52:
            self.ui.hudt.appendPlainText("A problem saving changes was detected everything preserved. Diagnose if there are any gpg related problems.")
            # loadgpg(self.dbopt, self.dbtarget, self.ui.dbmainlabel) # roll back on failure. database integrity is fine
    # end On completion Database Helpers

    # General Helpers

    # Main search 5 min, search, 5 min filtered, filtered search update ui on completion
    @Slot(int, str)
    def update_ui_settings(self, code, action_type):

        if action_type == "editor":
            self.setEnabled(True)

        if code == 0:
            if action_type == "search":
                self.ui.diffchka.setChecked(False)
                self.ui.diffchkb.setChecked(False)
                self.ui.diffchkc.setChecked(False)
            elif action_type == "scan":
                self.ui.dbchka.setChecked(False)

    # pg 1 index combo
    @Slot(int, int, str)
    def reload_drives(self, code, idx=None, drive=None):
        if code == 0:

            if idx and idx > 0:  # removed index

                self.ui.combd.removeItem(idx)

                self.load_last_drive()

            elif drive:  # added index

                idx_suffix = self.j_settings.get(drive, {})

                if idx_suffix:
                    cache_s, _, _ = get_cache_s(drive, self.CACHE_S_str, drive)
                    if os.path.isfile(cache_s):
                        self.ui.combd.addItem(drive)
                        ix = self.ui.combd.findText(drive)
                        if ix != -1:
                            self.ui.combd.setCurrentIndex(ix)
                    else:
                        self.ui.hudt.appendPlainText(f"Drive not found {drive}")
                else:
                    self.ui.hudt.appendPlainText(f"Failed to find {drive} in {self.sj}")
            else:
                self.ui.hudt.appendPlainText("Invalid argument no drive specified, reload_drives")

    # manage json
    @Slot(int, str, str, bool)
    def manage_sj(self, code, drive_idx, locale, is_ps):
        if code == 0:
            if drive_idx:  # drive is not basedir
                if locale == 'add':

                    self.lastdrive = drive_idx
                    update_dict({"last_drive": drive_idx}, self.j_settings)

                if locale == 'rmv':

                    # drive index with proteus shield
                    if is_ps:

                        e = self.basedirs.index_of_suffix(drive_idx)
                        if e != -1:
                            self.ui.sbasediridx.setEnabled(False)  # remove drive from basedirButton combo so it retains only drives with psEXTN
                            r = self.basedirs.remove_item(e)
                            self.ui.sbasediridx.setValue(r)
                            self.ui.sbasediridx.setMaximum(self.basedirs.items - 1)
                            self.ui.sbasediridx.setEnabled(True)

                    update_dict(None, self.j_settings, drive_idx)  # remove drive info for index

                    last_drive_value = self.j_settings.get("last_drive")

                    if last_drive_value:
                        if last_drive_value == drive_idx:
                            update_dict({"last_drive": self.suffix}, self.j_settings)  # set to default as index removed

                dump_j_settings(self.j_settings, self.sj)

            else:  # add or remove proteus EXTN from usrprofile.json for basedir

                if locale == 'add':

                    if self.xzm_obj:
                        extn = self.xzm_obj.create_xzm_baseline(self.suffix, self.sj)
                        self.xzm_obj = None

                    else:

                        extn = self.proteusEXTN
                        paths = self.proteusPATH
                        extn += paths

                    if extn:

                        self.basedirs.update_current_item(extn, proteusEXTN=extn)
                        update_j_settings({"proteusEXTN": extn}, self.j_settings, self.suffix, self.sj)
                        self.psEXTN = extn
                        self.ps_is_xzm = self.is_xzm_profile
                        extn = profile_to_str(extn, self.is_xzm_profile)
                        self.ui.hudt.appendPlainText(f'Profile drive {self.suffix} saved profile: {extn}\n')

                    else:

                        self.ui.hudt.appendPlainText(f'Failed to load proteusEXTN from {self.sj}\n')

                if locale == 'rmv':

                    self.basedirs.update_current_item(None, proteusEXTN=None)
                    update_j_settings({"proteusEXTN": None}, self.j_settings, self.suffix, self.sj)

        else:

            if drive_idx:
                if locale == 'add':
                    update_j_settings(None, self.j_settings, drive_idx, self.sj)  # remove preliminary drive info as add index had failed

            else:
                if code == 52:
                    if locale == 'add':
                        if not table_loaded(self.dbopt, self.sys_a, self.ui.hudt):  # make sure json and db are in sync on failure
                            self.ui.hudt.appendPlainText('profile removed successfully before failure syncing current data to usrprofile.')
                            self.basedirs.update_current_item(None, proteusEXTN=None)
                            update_j_settings({"proteusEXTN": None}, self.j_settings, self.suffix, self.sj)

    # end General Helpers
    #
    # end page_2


def start_main_window():

    # original_user = os.environ.get('SUDO_USER')
    # os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"

    appdata_local = Path(sys.argv[0]).resolve().parent  # software install aka workdir # find_install()
    # bundle_dir = Path(getattr(sys, "_MEIPASS", appdata_local))
    toml_file, json_file, home_dir, xdg_config, xdg_runtime, usr, uid, gid = get_config(appdata_local)

    log_dir = home_dir / ".local" / "state" / "recentchanges" / "logs"
    iconPATH = appdata_local / "Resources" / "48.png"

    pst_data = home_dir / ".local" / "share" / "recentchanges"
    dbtarget_frm = pst_data / "recent.gpg"
    CACHE_S_frm = pst_data / "systimeche.gpg"
    dbtarget = str(dbtarget_frm)
    CACHE_S = str(CACHE_S_frm)
    CACHE_S_str = str(CACHE_S_frm)  # used for reference

    config = load_toml(toml_file)
    if not config:
        return 1
    email = config['backend']['email']
    email_name = config['backend']['name']
    downloads = config['compress']['downloads'].rstrip('/')
    zipPATH = config['compress']['zipPATH']
    dspEDITOR = config['display']['dspEDITOR']
    dspPATH_frm = config['display']['dspPATH'].rstrip('/')
    dspPATH = ""
    if dspEDITOR:  # user wants results output in text editor
        dspEDITOR = multi_value(dspEDITOR)
        dspEDITOR, dspPATH = resolve_editor(dspEDITOR, dspPATH_frm, toml_file)  # verify we have a working one
        if not dspEDITOR and not dspPATH:
            return 1
    popPATH = config['display']['popPATH'].rstrip('/')
    basedir = config['search']['drive']
    driveTYPE = config['search']['driveTYPE']
    compLVL = config['logs']['compLVL']
    ll_level = config['logs']['logLEVEL'].upper()
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if usr != "root" else root_log_file
    proteuspaths = config['shield']['proteusPATH']
    nogo = user_path(config['shield']['nogo'], usr)
    suppress_list = user_path(config['shield']['filterout'], usr)

    # startup/initialize

    # check ps paths have to be relative. check certain paths exist. check the config file for mismatches.
    if not check_config(proteuspaths, nogo, suppress_list) or not check_utility(zipPATH, downloads, popPATH):
        return 1

    os.makedirs(log_dir, mode=0o755, exist_ok=True)
    log_path = log_dir / log_file
    check_log_perms(log_path)
    setup_logger(log_path, ll_level, process_label="mainwindow")

    with tempfile.TemporaryDirectory() as tempdir:
        # tempfile perms are 700
        try:
            app = QApplication(sys.argv)
            # print("Available styles:", QtWidgets.QStyleFactory.keys())
            app.setStyle("Fusion")
            palette = QPalette()
            # window background
            palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
            # text input
            palette.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
            palette.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
            palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
            palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.Highlight, QColor(185, 185, 185))
            # palette.setColor(QPalette.ColorRole.HighlightedText, QColor(20, 20, 20))
            palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
            palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
            palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
            app.setStyle("Fusion")
            app.setPalette(palette)
            gnupg_home = os.getenv("GNUPGHOME")
            if not gnupg_home:
                gnupg_home = home_dir / ".gnupg"
            gpg_path = shutil.which("gpg")
            if not gpg_path:
                QMessageBox.critical(None, "Error", "Unable to verify gpg in path. Likely path was partially initialized. quitting")  # QMessageBox.warning(None, "")
                return 1
            else:
                gpg_path = Path(gpg_path).resolve()

            is_key, err = iskey(email)
            if is_key is False:

                is_polkit = polkit_check()
                if not is_polkit:
                    fstr = (
                        "org.freedesktop.set_recent_helper policy not found. Ensure policy file is in right location to use polkit.\n"
                        "commands will be run as sudo and prompted in terminal"
                    )
                    QMessageBox.warning(None, "polkit check", fstr)

                res = False
                # from PySide6.QtWidgets import QInputDialog, QLineEdit
                # pawd, ok = QInputDialog.getText(None, "Enter new GPG Password", "Password:", QLineEdit.EchoMode.Password)
                icon = str(appdata_local / "Resources" / "gnupg-streamline.png")
                key_error = False
                dlg = PassphraseDialog(icon_path=icon)
                if not dlg.exec():
                    key_error = True

                pawd = dlg.get_password()

                res = genkey(appdata_local, usr, email, email_name, tempdir, is_polkit, pawd)
                if res:
                    rlt = test_gpg_agent(email)
                    if rlt is None:

                        cfg = parse_gpg_agent_conf(gnupg_home)
                        pinentry = cfg.get("pinentry-program")
                        is_curses = False
                        if pinentry and ("tty" in pinentry or "curses" in pinentry):
                            is_curses = any(x in pinentry.lower() for x in ("tty", "curses"))

                        fstr = (
                            "test gpg prompt failed in this session; GUI pinentry is recommended.\n"
                            + (f"current config is set to {pinentry}\n" if is_curses else "")
                            + "pinentry-gtk, pinentry-gtk-2, pinentry-gnome3 or pinentry-qt in .gnupg/gpg-agent.conf \n"
                        )
                        QMessageBox.warning(None, "curses", fstr)
                    print("Got password (hidden):", "*" * len(pawd) + "\n")
                if key_error or not res:
                    QMessageBox.critical(None, "Error", "Failed to generate key")
                    return 1
            elif is_key is None:
                QMessageBox.critical(None, "Error", err)
                return 1

            # decrypt recent.gpg db
            output = os.path.splitext(os.path.basename(dbtarget))[0]
            dbopt = os.path.join(tempdir, output + '.db')

            if os.path.isfile(dbtarget):
                res = decr(dbtarget, dbopt)
                if not res:
                    if res is None:
                        QMessageBox.critical(None, "Error", f"There is no key for {dbtarget}.")
                    else:
                        QMessageBox.critical(None, "Error", "Decryption failed .gpg could be corrupt. exitting.")
                    return 1

            # if drive is not "/" resolve partuuid. store info in json under suffix ie sda3
            j_settings = {}  # load it once. dump often to avoid desync but saves on unecessary reads

            CACHE_S, systimeche, suffix, driveTYPE = setup_drive_cache(
                basedir, appdata_local, dbopt, dbtarget, json_file, toml_file,
                CACHE_S_str, driveTYPE, usr, email, compLVL, j_settings=j_settings, iqt=True
            )
            if not CACHE_S or not suffix or not j_settings:
                return 1

            distro_name = j_settings.get("/", {}).get("distro_name")
            if not distro_name:
                _, distro_name = get_linux_distro()
                if distro_name:
                    update_dict({"distro_name": distro_name}, j_settings, "/")
            # end startup/initialize

            print("Qt database in ", tempdir)
            icon_path = str(iconPATH)

            def excepthook(exc_type, exc_value, exc_traceback):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

                app_inst = QApplication.instance()
                if app_inst is not None:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Icon.Critical)
                    msg.setWindowTitle("Error")
                    msg.setText(f"An unexpected error occurred:\n{exc_value}")
                    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                    msg.exec()
                # else:
                    # app_inst = QApplication(sys.argv)

                log_pth = os.path.join(appdata_local, "logs", "errs.log")
                print(f"Unhandled exception {exc_type.__name__} stack trace logged to: {log_pth}")
                sys.exit(1)
            sys.excepthook = excepthook

            exit_code = 0

            window = MainWindow(
                appdata_local, home_dir, xdg_runtime, pst_data, config, j_settings, toml_file, json_file, log_path, driveTYPE, distro_name, dbopt, dbtarget,
                CACHE_S, CACHE_S_str, systimeche, suffix, gpg_path, gnupg_home, dspEDITOR, dspPATH, popPATH,
                downloads, email, usr, uid, gid, tempdir
            )
            window.setWindowIcon(QIcon(icon_path))
            window.show()
            exit_code = app.exec()

            sys.exit(exit_code)

        except Exception as e:
            em = "Failed to initialize qt app:"
            print(f"{em} {type(e).__name__} err: {e} \n {traceback.format_exc()}")
            QMessageBox.critical(None, "Error", f"{e}")
            logging.error(em, exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    sys.exit(start_main_window())
