import logging
import os
import re
import requests
import shutil
import signal
import sqlite3
import subprocess
import traceback
import webbrowser
from datetime import datetime
from packaging import version
from pathlib import Path
from PySide6.QtCore import QDateTime
from PySide6.QtGui import QIcon, QFontDatabase, QImage
from PySide6.QtSql import QSqlDatabase, QSqlQuery
from PySide6.QtWidgets import QVBoxLayout, QDialog, QPushButton, QLabel, QInputDialog, QMessageBox, QHBoxLayout
from .config import update_j_settings
from .dbmexec import DBConnectionError
from .dbmexec import DBMexec
from .gpgcrypto import decr
from .gpgcrypto import decrypt_from_text
from .gpgcrypto import encr
from .gpgcrypto import encrypt_to_text
from .pyfunctions import is_integer
from .pysql import clear_conn
from .rntchangesfunctions import to_bool
from .rntchangesfunctions import porteus_linux_check
# 07/10/2026


def polkit_check(action_id="org.freedesktop.set_recent_helper"):
    # 127 no policy 2 if no -u
    # pid = os.getpid()
    # "pkcheck", "--action-id", action_id, "--process", str(pid)  # , "-u"
    pkcheck_command = ["pkaction", "--action-id", action_id]
    try:
        result = subprocess.run(pkcheck_command, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def polkit_authorized(uid, action_id="org.freedesktop.set_recent_helper", prompt_user=False):
    pid = os.getpid()
    with open(f"/proc/{pid}/stat", "r", encoding="utf-8") as f:
        start_time = f.read().split()[21]  # proc stat field 22
    # uid = os.getuid()

    cmd = [
        "pkcheck",
        "--action-id", action_id,
        "--process", f"{pid},{start_time},{uid}",
    ]
    if prompt_user:
        cmd.append("--allow-user-interaction")  # -u

    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode, res.stderr.strip()


def window_prompt(parent, title, message, affirm, reject):  # y/n
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    # msg_box.setWindowIcon(QIcon("/usr/local/recentchanges/Resources/cleo.png"))
    import_button = msg_box.addButton(affirm, QMessageBox.ButtonRole.AcceptRole)
    default_button = msg_box.addButton(reject, QMessageBox.ButtonRole.RejectRole)  # noqa: F841
    msg_box.exec()
    return msg_box.clickedButton() == import_button


def window_message(parent, message, title="Status", default=True):  # ok
    msg = QMessageBox(parent)
    if default:
        msg.setIcon(QMessageBox.Icon.Warning)
    else:
        msg.setIcon(QMessageBox.Icon.Information)
    msg.setWindowTitle(title)
    msg.setText(message)
    msg.setWindowIcon(QIcon("/usr/local/recentchanges/Resources/48.png"))
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg.exec()


def window_input(parent, title, value_title):
    return QInputDialog.getText(parent, title, value_title)


def profile_to_str(ps, is_xzm_profile):
    sep = '\n' if is_xzm_profile else ', '
    return sep.join(ps)


def ps_profile_type(profile):
    if not profile:
        return False
    if len(profile) > 2:
        if "binary" in profile[0] and "path" in profile[1] and len(profile) == 3:
            return True
    return False


def sort_right(tables, cache_table, systimeche, suffix):
    a, b, c, tbl = [], [], [], []
    # systime = self.systimeche.split("_", 1)[-1]  # sys_delim = systime + "_"
    is_basedir = suffix == "/"
    if is_basedir:
        for t in tables:
            if "sys" in t and "_" in t:
                b.append(t)
            elif "cache" in t and t != cache_table:
                b.append(t)
            else:
                a.append(t)
        tbl = a + b
    else:
        for t in tables:
            if t.startswith("sys"):
                if suffix in t:
                    if t == systimeche:
                        c.append(t)  # major long string goes to c
                    else:
                        a.append(t)  # major
                else:
                    b.append(t)
            elif t.startswith("cache"):
                if t == cache_table:
                    c.append(t)  # minor goes to c
                else:
                    b.append(t)
            else:
                tbl.append(t)  # reg sql table
        tbl = tbl + a + c + b
    return tbl


def select_custom(parent):

    title = "Choose an Option"
    msg = "Please select an option:"

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)

    layout = QVBoxLayout(dlg)

    label = QLabel(msg)
    layout.addWidget(label)

    # Jpg
    row1 = QHBoxLayout()
    btn_importjpg = QPushButton("Jpg")
    btn_resetjpg = QPushButton("Reset")
    # Alarm One
    btn_alarmone = QPushButton("Alarm set")
    btn_resetalarmone = QPushButton("Reset")

    # row1.addStretch()  # original
    row1.addWidget(btn_importjpg)
    row1.addWidget(btn_resetjpg)
    row1.addWidget(btn_alarmone)
    row1.addWidget(btn_resetalarmone)
    # row1.addStretch()  # .
    layout.addLayout(row1)

    # Crest
    row2 = QHBoxLayout()
    btn_importcrest = QPushButton("Crest")
    btn_resetcrest = QPushButton("Reset")
    # Alarm Two
    btn_alarmtwo = QPushButton("Alarm sound")
    btn_resetalarmtwo = QPushButton("Reset")

    # row2.addStretch()  # .
    row2.addWidget(btn_importcrest)
    row2.addWidget(btn_resetcrest)
    row2.addWidget(btn_alarmtwo)
    row2.addWidget(btn_resetalarmtwo)
    # row2.addStretch()  # .
    layout.addLayout(row2)

    row3 = QHBoxLayout()
    btn_embosscrest = QPushButton("Emboss Crest")
    # row3.addStretch()  # .
    row3.addWidget(btn_embosscrest)
    # row3.addStretch()  # .
    layout.addLayout(row3)

    result = {"value": None}
    buttons = [btn_importjpg, btn_resetjpg, btn_alarmone, btn_resetalarmone, btn_importcrest, btn_resetcrest, btn_alarmtwo, btn_resetalarmtwo, btn_embosscrest]
    max_w = max(b.sizeHint().width() for b in buttons)
    max_h = max(b.sizeHint().height() for b in buttons)

    for b in buttons:
        b.setFixedSize(max_w, max_h)

    # Connect buttons to results
    btn_importjpg.clicked.connect(lambda: (result.update(value="jpg"), dlg.accept()))
    btn_resetjpg.clicked.connect(lambda: (result.update(value="defjpg"), dlg.accept()))
    btn_alarmone.clicked.connect(lambda: (result.update(value="alarmone"), dlg.accept()))
    btn_resetalarmone.clicked.connect(lambda: (result.update(value="defalarmone"), dlg.accept()))
    btn_importcrest.clicked.connect(lambda: (result.update(value="crest"), dlg.accept()))
    btn_resetcrest.clicked.connect(lambda: (result.update(value="defcrest"), dlg.accept()))
    btn_alarmtwo.clicked.connect(lambda: (result.update(value="alarmtwo"), dlg.accept()))
    btn_resetalarmtwo.clicked.connect(lambda: (result.update(value="defalarmtwo"), dlg.accept()))
    btn_embosscrest.clicked.connect(lambda: (result.update(value="emboss"), dlg.accept()))

    dlg.exec()
    return result["value"]


def valid_crest(parent, crest_path):
    img = QImage(crest_path)

    if img.isNull():
        QMessageBox.warning(parent, "Error", "Invalid image file.")
        return False

    w = img.width()
    h = img.height()

    if w > 255 or h > 333:
        window_message(parent, f"Image size must be 250x333 or less.\n\nSelected image: {w}x{h}", "Invalid size")
        return False
    return True


# QSql
def get_conn(db_path, conn_name):
    if QSqlDatabase.contains(conn_name):
        db = QSqlDatabase.database(conn_name)
    else:
        db = QSqlDatabase.addDatabase("QSQLITE", conn_name)
        db.setDatabaseName(db_path)

    if not db.isOpen():
        if not db.open():
            return None, f"Failed to open database: exit {db.lastError().text()}"
    return db, None


# if sys table has data prompt before continuing
# sys  for / sys_n for n drive
# cache_s for / or cache_sdx for device     directories at time of profile
# systimeche - systimeche_sdx   these are dirs as cache is updated
def has_sys_data(dbopt, logger, sys_table, prompt, parent=None):
    db = query = None
    conn_nm = "sq_1"
    db_name = os.path.basename(dbopt)

    try:
        db, err = get_conn(dbopt, conn_nm)
        if err:
            logger.appendPlainText(f"could not connect to {db_name} database {err}")
        else:
            query = QSqlQuery(db)
            if sys_table in db.tables():
                query.prepare(f"SELECT 1 FROM {sys_table} LIMIT 1")
                if query.exec():
                    if query.next():
                        uinpt = window_prompt(parent, "Confirm Action", prompt, "Yes", "No")
                        if uinpt:
                            return True
                        if not uinpt:
                            return None
                else:
                    err = query.lastError()
                    if err.isValid():
                        error_message = f"query failed: {query.lastError().text()}"
                        logger.appendPlainText(error_message)
                        return None

            return False
    except Exception as e:
        mg = f"query error {type(e).__name__}: {e}"
        print(mg)
        if query:
            mg = mg + f"{query.lastError().text()}\n"
        logger.appendPlainText(mg)
        logging.error(mg, exc_info=True)
    finally:
        if db:
            db.close()
    return None


# check if there actually is a table before trying to do anything
def table_loaded(dbopt, table_nm, logger):
    try:
        if os.path.isfile(dbopt):
            with DBMexec(dbopt, "sq_1", ui_logger=logger) as dmn:
                if dmn.table_has_data(table_nm):
                    return True
    except DBConnectionError as e:
        logger.appendPlainText(f"Database table_loaded error: {e}")
    except Exception as e:
        emsg = f"err while checking table in table_loaded: {type(e).__name__} {e}"
        logger.appendPlainText(emsg)
        logging.error(f"{emsg} \n{traceback.format_exc()}")
    return False


def has_log_data(dbopt, logger, parent=None):
    try:
        with DBMexec(dbopt, "sq_1", ui_logger=logger) as dmn:  # dmn.table_has_data(table_nm):
            sql = "SELECT COUNT(*) FROM logs WHERE hardlinks IS NOT NULL AND hardlinks != ''"
            result = dmn.execute(sql)
            if result:
                result.next()
                count = result.value(0)
                if count > 0:
                    uinpt = window_prompt(parent, "Confirm Action", "Previous 'hardlinks' data has to be cleared. Continue? (y/n): ", "Yes", "No")
                    if not uinpt:
                        return False
                return True
            else:
                logger.appendPlainText("Query failed hlinks function")
    except DBConnectionError as e:
        err_msg = f"Database connection error sq_1 {dbopt} in hlinks error: {e}"
        logger.appendPlainText(err_msg)
        logging.error(err_msg, exc_info=True)
    except Exception as e:
        err_msg = f"Error while setting hardlinks {type(e).__name__} {e}"
        logger.appendPlainText(err_msg)
        logging.error(err_msg, exc_info=True)
    return False


def commit_note_history(logger, notes, saved_history, email, query):
    try:
        encrypted_data = encrypt_to_text(notes, email)
        if encrypted_data is None:
            print("Problem encrypting notes aborting")
            return False
        # gpg = gnupg.GPG()
        # encrypted_data = gpg.encrypt(notes, recipients=[email])
        # if not encrypted_data.ok:
        #     print(encrypted_data.stderr)
        #     print("Problem encrypting notes aborting")
        #     return False
            # raise RuntimeError(f"Encryption failed: {encrypted_data.status}")
        ciphertext = str(encrypted_data)

        query.prepare("""
            INSERT INTO extn (id, notes, history)
            VALUES (1, :notes, :history)
            ON CONFLICT(id) DO UPDATE SET
                notes = excluded.notes,
                history = excluded.history
        """)
        query.bindValue(":notes", ciphertext)
        query.bindValue(":history", saved_history)
        if query.exec():
            return True
        else:
            err = query.lastError()
            if err and err.isValid():
                logger.appendPlainText(f"commit_note query err: {err.text()}\n")
            logger.appendPlainText("Failed to save notes to db")
    except Exception as e:
        logger.appendPlainText(f"Unable update notes savenote qtfunctions {type(e).__name__} err: {e} \n{traceback.format_exc()}")
    return False


# end QSql


def clear_cache(conn, cur, cachermPATTERNS, log_fn=print):

    files_d = cachermPATTERNS
    filename_pattern = None
    try:
        for filename_pattern in files_d:
            cur.execute("DELETE FROM logs WHERE filename LIKE ?", (filename_pattern,))
            cur.execute("DELETE FROM stats WHERE filename LIKE ?", (filename_pattern,))
        if filename_pattern is not None:
            conn.commit()
        log_fn("Cache files cleared.")
        return True
    except sqlite3.Error as e:
        conn.rollback()
        log_fn(f"cache_clear query.py failed to write to db. on {filename_pattern if filename_pattern else ''} {e} {type(e).__name__}")
    except Exception as e:
        conn.rollback()
        log_fn(f'General failure in query.py clear_cache: {e}')
    return False


def clear_from_extn_tbl(dbopt, extn_or_hist, quiet):
    conn = None
    cur = None
    try:
        conn = sqlite3.connect(dbopt)
        cur = conn.cursor()
        if extn_or_hist:
            out_str = "extn table cleared."
            cur.execute("DELETE FROM extn WHERE ID != 1")
        else:
            out_str = "history cleared."
            saved_history = ""
            cur.execute("""
                INSERT INTO extn (id, history)
                VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    history = excluded.history;
            """, (saved_history,))

        conn.commit()
        if not quiet:
            print(out_str)
        return True
    except Exception as e:
        print("Reencryption failed extension table clear")
        if conn:
            conn.rollback()
        print(f"failure clear_from_extn_tbl func {type(e).__name__}: {e}")
        return False
    finally:
        clear_conn(conn, cur)


def load_gpg(dbopt, dbtarget, user, logger):
    if os.path.isfile(dbtarget):
        res, err = decr(dbtarget, dbopt)
        if res:
            return True
        print(err)
    else:
        logger.setText("No database to load")
    return False


def open_html_resource(parent, lclhome):
    fp_ = os.path.join(lclhome, "Resources", "Welcomefile.html")
    fpth = os.path.abspath(fp_)

    html_file = Path(fpth).resolve()
    webbrowser.open(html_file.as_uri())
    # win = QMainWindow(parent)  # web engine is 200mb
    # central = QWidget()
    # layout = QVBoxLayout(central)
    # win.setCentralWidget(central)
    # browser = QWebEngineView()
    # browser.setUrl(QUrl.fromLocalFile(fpth))
    # layout.addWidget(browser)
    # win.resize(800, 600)
    # win.show()
    # win.raise_()
    # win.activateWindow()
    # return win


def show_cmddoc(cmddoc, lclhome, pst_data, gpg_path, gnupg_home, email, example_gpg, hudt):

    hudt.clear()
    fingerprint = None

    # custom quick commands
    if os.path.isfile(cmddoc):
        with open(cmddoc, 'r') as f:
            content = f.read()
            hudt.appendPlainText(content)
            # for line in f:
            #     print(line.strip())

    # gpg info
    hudt = hudt.appendPlainText
    hudt("\n")

    gpg_command = str(gpg_path)
    command = [gpg_command]

    command += ['--list-secret-keys']
    try:

        result = subprocess.run(command, capture_output=True, text=True)
        pattern = r'\s+([A-F0-9]{40})\n.*?uid\s+\[.*?\]\s+([^\n<]+<([^>]+)>)'

        output = result.stdout
        matches = re.findall(pattern, output)
        for match in matches:

            user_email = match[2]
            if user_email == email:
                fingerprint = match[0]
                break

    except Exception:
        hudt("An error occurred while trying to list GPG keys.")
        pass

    # gpg_install_l = str(gpg_path).lower()

    if fingerprint:
        hudt(f"Delete a GPG key for: {email}\n")
        hudt(f"gpg --delete-secret-key {fingerprint}")
        hudt(f"gpg --delete-key {fingerprint}")

    gpg_command = "gpg"

    hudt("\n")
    hudt("decrypt something (example check a cache file) from app directory")
    hudt(
        f"{gpg_command} -o myfile.txt --decrypt {pst_data}/{example_gpg}.gpg"
    )
    # end gpg info


def available_fonts(hudt):
    hudt.appendPlainText("System installed fonts\n")
    fonts = QFontDatabase.families()
    for f in fonts:
        hudt.appendPlainText(f)


def get_help(lclscripts, resources, hudt):
    def show_help():
        with open(fp_, 'r') as f:
            for line in f:

                if line.startswith("#"):
                    continue
                # line = line.replace("\\t", "\t")
                hudt.appendPlainText(line.rstrip("\n"))
    hudt.clear()
    script = "versionquery"
    # fp_ = lclscripts / script
    # cmd = [str(fp_), "-h"]
    return_code = 1
    # try:
    #     result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    #     print("result", result)
    #     for r in result.stdout.splitlines():
    #         hudt.appendPlainText(r)
    #     print(f'Bash script failed {fp_}. error code: {result.returncode}')
    # except subprocess.CalledProcessError as e:
    #     return_code = e.returncode
    # except Exception:
    #     hudt.appendPlainText("Error in get_help function")
    #     return
    if return_code != 0:
        fp_ = resources / script
        show_help()


def get_latest_github_release(user, repo):
    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        latest_version = data["tag_name"].lstrip("v")  # # .removesuffix("-py1")
        download_url = data["html_url"]
        return latest_version, download_url
    except Exception as e:
        print("Failed to fetch latest release:", e)
        return None, None


def check_for_updates(app_version, user, repo, parent=None):

    latest_version, _ = get_latest_github_release(user, repo)
    if latest_version and version.parse(latest_version) > version.parse(app_version):
        window_message(parent, f"New version available: {latest_version}", "Update msg", default=False)
    else:
        window_message(parent, f"You are running the latest version. {app_version}", "Update msg", default=False)


def show_licensing(lclhome, hudt):
    hudt.clear()
    l_folder = os.path.join(lclhome, "Licenses")
    if not os.path.isdir(l_folder):
        return
    for filename in os.listdir(l_folder):
        fp = os.path.join(l_folder, filename)

        if not os.path.isfile(fp):
            continue
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            contents = f.read()
        hudt.appendPlainText(contents)
        hudt.appendPlainText("\n")


def help_about(lclhome, hudt, version_no):
    dlg = QDialog()
    dlg.setWindowTitle("About Recent Changes")

    layout = QVBoxLayout()
    # layout.setSpacing(15)
    # layout.setContentsMargins(20, 20, 20, 20)

    label = QLabel(f"{version_no}\n\nCreated by Colby Saigeon\nh&k enterprisez\n\nFind recent files using find or python.")
    # label.setWordWrap(True)
    layout.addWidget(label)

    run_btn = QPushButton("Licensing")
    run_btn.clicked.connect(lambda: show_licensing(lclhome, hudt))
    run_btn.setFixedWidth(run_btn.sizeHint().width() + 20)
    layout.addWidget(run_btn)  # alignment=Qt.AlignHCenter

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.close)
    close_btn.setFixedWidth(run_btn.sizeHint().width() + 20)
    layout.addWidget(close_btn)

    dlg.setLayout(layout)
    dlg.exec()


def return_terminal():
    terminals = []

    term_env = os.environ.get("TERMINAL")
    if term_env:
        terminals.append(term_env)

    terminals.extend([
        "x-terminal-emulator", "mate-terminal", "gnome-terminal", "terminator", "xfce4-terminal", "urxvt", "rxvt",
        "termit", "Eterm", "aterm", "uxterm", "xterm", "roxterm", "termite", "lxterminal", "terminology", "st",
        "qterminal", "lilyterm", "tilix", "terminix", "konsole", "kitty", "guake", "tilda", "alacritty", "hyper", "wezterm",
        "rio",
    ])

    for terminal in terminals:
        if shutil.which(terminal):
            return terminal
    return None
    # raise RuntimeError("No terminal emulator found")


def run_set_helper(script_path, args=None, is_polkit=False, input_data=None):

    result = 0
    comm = "pkexec" if is_polkit else "sudo"
    cmd = [
        comm,
        str(script_path),
    ]
    if args:
        if isinstance(args, (list, tuple)):
            cmd += list(map(str, args))
        else:
            raise TypeError("args must be a list or tuple of strings")
    script_dir = os.path.dirname(script_path)
    result = subprocess.run(
        cmd,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=script_dir,
    )
    stdout = result.stdout.decode(errors="replace")
    stderr = result.stderr.decode(errors="replace")
    if result.returncode != 0:
        result = 1
        stdout = "STDOUT:\n" + stdout  # print any debug
        stderr = "STDERR:\n" + stderr  # gpg prints to stderr
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    return result


def load_konsole(lclhome, popPATH=None):

    work_area = lclhome if not popPATH else popPATH

    konsole = return_terminal()
    if konsole:
        if isinstance(konsole, str):
            konsole = [konsole]

        subprocess.Popen(
            konsole,
            cwd=work_area,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # text=True,
        # _, stderr_text = res.communicate()
        # if res.returncode != 0:
        #     print(stderr_text, end="")
        #     return res.returncode
    return 0


# "env",
# f"DISPLAY={os.environ.get('DISPLAY', '')}",
# f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}",
# f"PATH={os.environ.get('PATH', '')}",
# f"PORTDIR={os.environ.get('PORTDIR', '')}",
# f"BOOTDEV={os.environ.get('BOOTDEV', '')}",
#
#     env = os.environ.copy()
#     # env["PATH"] = r";" + env["PATH"]
#     # env=env,
def load_file_manager(lclhome, popPATH=None):
    cmd = []
    has_dbus_run = shutil.which("dbus-run-session") is not None
    if has_dbus_run:
        cmd += ["dbus-run-session"]

    work_area = lclhome if not popPATH else popPATH
    cmd += ["xdg-open", str(Path(work_area).resolve())]

    subprocess.Popen(
        cmd,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def kill_process(pid):
    try:
        os.kill(int(pid), signal.SIGTERM)
        # print(f"Sent SIGTERM to PID {pid}")
        # time.sleep(1)
        # os.kill(int(pid), 0)
        # os.killpg(int(pid), signal.SIGKILL)
        # print(f"Sent SIGKILL to PID {pid}")
    except TypeError:
        print("kill_process failed on invalid arg")
    except PermissionError:
        print(f"operation not permitted cannot close PID {pid}")
    except ProcessLookupError:
        # print(f"PID {pid} does not exist")
        pass


def get_timezone(j_settings: dict, json_file: Path) -> str:
    region = zone = None
    timezone = j_settings.get("time_zone")
    if timezone:
        parts = timezone.split("/")
        if len(parts) == 2:
            region, zone = parts
            timezone = f'{region}/{zone}'
        else:
            print("time_zone was malformed in json clearing")
            timezone = None
            update_j_settings({"time_zone": None}, j_settings, None, json_file)
    return timezone, region, zone


def set_clock(region, zone, distro, sync_clock, dual_boot):
    if not (region and zone):
        print("<region> <zone> required")
        return 1
    if not os.path.exists("/etc/localtime.bak"):
        ret = os.system("cp /etc/localtime /etc/localtime.bak")
        if ret == 0:
            print("/etc/localtime backed up to /etc/localtime.bak")
    rz = f'{region}/{zone}'
    tz_file = f"/usr/share/zoneinfo/{rz}"
    if not os.path.isfile(tz_file):
        print(f"Timezone file not found: {tz_file}")
        return
    if os.path.exists("/etc/localtime"):
        os.remove("/etc/localtime")
    os.symlink(tz_file, "/etc/localtime")
    print(f"Timezone set to {rz}")
    sync_clock = to_bool(sync_clock)
    dual_boot = to_bool(dual_boot)

    ret = 0
    if sync_clock:
        # currently if the distro is "" its not nemesis or porteus
        # if case of "None" was passed
        if distro == "None":
            distro = porteus_linux_check()  # returns porteus or nemesis or False None

        if distro == "nemesis":
            result = subprocess.run(["rc-service", "ntpd", "status"], capture_output=True, text=True)
            if result.returncode == 0:
                print("rc-service ntpd running")
            # os.system("rc-service ntpd stop")
            # os.system("ntpdate pool.ntp.org")
            # os.system("rc-service ntpd start")
            pass
        elif distro == "porteus":
            out_str = "ntpdate pool.ntp.org"
            print(out_str)
            ret = os.system(out_str)
            if ret != 0:
                print(out_str, "had failed")
        else:
            out_str = f"timedatectl set-timezone {rz}"
            print(out_str)
            ret = os.system(out_str)
            if ret == 0:
                out_str = "timedatectl set-ntp true"
                print(out_str)
                ret = os.system("timedatectl set-ntp true")
                if ret != 0:
                    print(f"{out_str} had failed")
            else:
                print(out_str, "had failed")

        if ret == 0:
            hw_str = "hwclock -wl" if dual_boot else "hwclock -uw"
            print(hw_str)
            ret = os.system(hw_str)
            if ret != 0:
                print(hw_str, "had failed")
    return ret


def add_new_extension(default_extensions, logger, combffile, dbopt, dbtarget, email, nc, parent=None):

    res = False
    extension_value, ok = window_input(parent, 'Add ext', 'extension:')
    if ok:
        if not re.fullmatch(r'\.[A-Za-z0-9_-]+', extension_value):
            window_message(parent, "Improper syntax for an extension")
            return res
        else:

            ix = combffile.findText(extension_value)
            if ix == -1:

                try:
                    with DBMexec(dbopt, "sq_1", ui_logger=logger) as dmn:  # dmn.table_has_data(table_nm):

                        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
                        sql = "INSERT OR IGNORE INTO extn (extension, timestamp) VALUES (:extn, :timestamp)"
                        params = {"extn": extension_value, "timestamp": ts}
                        if dmn.execute(sql, params):
                            prev_items = [combffile.itemText(i) for i in range(1, combffile.count())]
                            # if extension_value:
                            #     combffile.insertItem(0, extension_value) changes format use below
                            index = fill_extensions(combffile, default_extensions, extension_value, prev_items)
                            if is_integer(index) and index >= 0:
                                combffile.setCurrentIndex(index)
                            res = True
                        else:
                            logger.appendPlainText(f"Query failed add_extension for extension: {extension_value}")
                except DBConnectionError as e:
                    err_msg = f"Database connection error sq_1 {dbopt} in addext error: {e}"
                    logger.appendPlainText(err_msg)
                    logging.error(err_msg, exc_info=True)
                except Exception as e:
                    err_msg = f"Error while inserting extensions {type(e).__name__} {e}"
                    logger.appendPlainText(err_msg)
                    logging.error(err_msg, exc_info=True)

            else:
                logger.appendPlainText("Extension already listed")
    if res:
        if encr(dbopt, dbtarget, email, None, nc, True):
            return extension_value
        else:
            res = False
            print("Failed to encrypt changes while saving extension. from add_extension qtfunctions")
    return res


def fill_extensions(combffile, default_extensions, new_extension=None, prev_extensions=None, query=None):
    rlt = False
    c_text = combffile.currentText()

    combffile.clear()
    combffile.addItem("")
    if query:
        extns = []
        while query.next():
            extension = query.value(0)
            combffile.addItem(extension)
            extns.append(extension)
        combffile.addItems(default_extensions)
        return extns
    elif new_extension:
        combffile.addItem(new_extension)
        combffile.addItems(prev_extensions)
        index = combffile.findText(new_extension)
        return index
    elif prev_extensions:
        combffile.addItems(prev_extensions)
        ix = combffile.findText(c_text)
        if ix != -1:
            combffile.setCurrentIndex(ix)
        else:
            if combffile.count() > 0:
                combffile.setCurrentIndex(0)
    combffile.addItems(default_extensions)
    return rlt


def user_data_to_database(notes, saved_history, logger, dbopt, dbtarget, email, nc, isexit=False, parent=None):
    db = None
    res = False
    try:
        print(notes, saved_history)
        db, err = get_conn(dbopt, "sq_9")
        if err:
            print("Failed to connect to database in save_user_data")
        else:
            query = QSqlQuery(db)
            res = commit_note_history(logger, notes, saved_history, email, query)  # save last used drive index to json

    except (FileNotFoundError, Exception) as e:
        logger.appendPlainText(f"unable to save user data save_user_data err:{type(e).__name__} {e}")
    finally:
        if db:
            db.close()
            del db
    if res:
        if encr(dbopt, dbtarget, email, nc, True):
            if not isexit:
                logger.appendPlainText("Settings saved.")
            return True

    window_message(parent, "There was a problem rencrypting notes.", "Status")
    return False


def user_data_from_database(logger, textEdit, combffile, extensions, dbopt, is_startup=False, parent=None):
    query = None
    extension_data = []
    saved_history = ""

    data_name = ""
    try:
        with DBMexec(dbopt, "sq_1", ui_logger=logger) as dmn:

            # this is called when the app is started store the current time so later can check if app has been started after system boot
            if is_startup:

                last_start = int(datetime.now().timestamp())  # to compare later to system start time to see if the app is launched for the first time **
                sql = """
                    INSERT INTO analytics (id,last_start)
                    VALUES (1, :last_start)
                    ON CONFLICT(id) DO UPDATE SET
                        last_start = excluded.last_start;
                """
                query = dmn.execute(sql, {"last_start": str(last_start)})
                if not query:
                    logger.appendPlainText("Query failed analytics table in user_data_from_database while starting up")

            data_name = "extn"
            sql = "SELECT extension FROM extn WHERE id != 1"
            query = dmn.execute(sql)
            if query:
                extension_data = fill_extensions(combffile, extensions, query=query)
            else:
                logger.appendPlainText("Query failed extn table in user_data_from_database.")

            # get encrypted notes
            data_name = "notes"
            sql = "SELECT notes, history FROM extn WHERE id = 1"
            query = dmn.execute(sql)
            if query and query.exec() and query.next():
                if query.value(0):
                    # if using gnupg package but disabled as not needed for minimum dependencies
                    # logging.getLogger('gnupg').setLevel(logging.CRITICAL)
                    # gpg = gnupg.GPG()
                    encrypted_blob = query.value(0)
                    decrypted_data = decrypt_from_text(encrypted_blob)
                    if decrypted_data or decrypted_data == "":
                        notes = str(decrypted_data)
                        textEdit.setPlainText(notes)
                    # decrypted_data = gpg.decrypt(encrypted_blob)
                    # if decrypted_data.ok:
                    #     notes = str(decrypted_data)
                    #     textEdit.setPlainText(notes)
                    elif decrypted_data is None:
                        print("Could not decrypt notes")
                        # passphrase, ok = QInputDialog.getText(parent, "Decrypt Notes", "Enter GPG passphrase:", echo=QLineEdit.EchoMode.Password)
                        # if ok and passphrase:
                        #     decrypted_data = gpg.decrypt(
                        #         encrypted_blob,
                        #         passphrase=passphrase,
                        #         extra_args=["--pinentry-mode", "loopback"]
                        #     )
                        #     if decrypted_data.ok:
                        #         notes = str(decrypted_data)
                        #         textEdit.setPlainText(notes)
                        # else:
                        #     logger.appendPlainText(decrypted_data.stderr)
                        #     print("Could not decrypt notes")
                if query.value(1):
                    saved_history = query.value(1)

            return extension_data, saved_history
    except DBConnectionError as e:
        err = ""
        if query:
            err = f":{query.lastError().text()}"
        err_msg = f'Database failed to load user data loading {data_name}  last query error: {err} error : {e}'
        logger.appendPlainText(err_msg)
        logging.error(err_msg, exc_info=True)
    except Exception as e:
        err = ""
        if query:
            err = f":{query.lastError().text()}"
        err_msg = f"err while loading user data table extn loading {data_name} fail: {type(e).__name__} {e} query err: {err}"
        logger.appendPlainText(err_msg)
        logging.error(err_msg, exc_info=True)
    return []


def get_history_view(saved_history, calculator):
    """ fetch results any results to append to saved history """
    c = calculator
    if c and c.last_history_view:
        saved_history = saved_history + c.last_history_view
        c.last_history_view = ""
    return saved_history
