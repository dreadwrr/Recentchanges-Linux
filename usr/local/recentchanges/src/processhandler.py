import subprocess
import time
from PySide6.QtCore import QObject, Signal, QProcess, QTimer, QThread, Slot
from .rntchangesfunctions import display
from .gpgcrypto import start_gpg_agent
from .qtclasses import GpgPromptWorker


# QProcess scripts
class ProcessHandler(QObject):

    progress = Signal(float)
    log = Signal(str)
    error = Signal(str)
    status = Signal(str)
    complete = Signal(int, int)

    def __init__(self, lclhome, xdg_runtime, dblabel_text, use_polkit=True):
        super().__init__()

        self.lclhome = lclhome
        self.xdg_runtime = xdg_runtime
        self.dblabel_text = dblabel_text
        self.is_polkit = use_polkit

        self.icon = str(lclhome / "Resources" / "gnupg-streamline.png")

        self.process = QProcess(self)

        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.is_terminating = False
        self.is_prompt_timer = False

        self.is_compress = False

        self.prog_v = 0

        self.comm = None
        self.script = None
        self.pid = None

        self.database = None  # start_pyprocess
        self.statusmsg = None
        self.is_search = False
        self.is_postop = False
        self.is_scanIDX = False

        self.rangeVALUE = None  # set_compress  findfile wsl/pwsh
        self.zipPROGRAM = None
        self.zipPATH = None
        self.USRDIR = None
        self.downloads = None

        self.tgt_file = None  # set_task for, popup text editor
        self.dspEDITOR = None  # 2.
        self.dspPATH = None
        self.temp_dir = None

        self.ANALYTICSECT = None  # process duration display
        self.st_time = 0  # .
        self.result_path = None  # result path from stdout
        self._stdout_buffer = ""
        self.gpg_thread = None
        self.gpg_worker = None

    def set_compress(self, zipPROGRAM, zipPATH, USRDIR, downloads):  # For compress button. pass ins
        self.is_compress = True
        self.zipPROGRAM = zipPROGRAM
        self.zipPATH = zipPATH
        self.USRDIR = USRDIR
        self.downloads = downloads

    def set_task(self, tgt_file, dspEDITOR, dspPATH, tmp_dir):  # Opening results in text editor. pass ins
        self.tgt_file = tgt_file  # output results. filepaths or for popup dspEDITOR
        self.dspEDITOR = dspEDITOR  # 2.
        self.dspPATH = dspPATH
        self.temp_dir = tmp_dir

    def set_mcore(self, ismcore):  # pass in # Handles not stopping if processes are running at certain range or stage in multicore
        self.ismcore = ismcore

    def set_range(self, rangeVALUE):
        self.rangeVALUE = rangeVALUE

    @Slot(bool)
    def _on_gpg_prompt_finished(self, ok):
        if ok:
            if self.is_prompt_timer:
                # if self.prompt_timer.isActive():
                self.prompt_timer.stop()
                self.prompt_timer.deleteLater()
                self.prompt_timer = None
                self.is_prompt_timer = False
            self.status.emit(self.dblabel_text)
            self._start_dispatch_process()
        else:
            self.complete.emit(7, QProcess.ExitStatus.NormalExit.value)

    @Slot()
    def _cleanup_gpg_thread(self):
        self.gpg_thread = None
        self.gpg_worker = None

    def is_running(self):
        return self.process.state() == QProcess.ProcessState.Running

    def stop(self):

        if not self.database:
            # delegate to stopf in recentchangessearch to avoid corruption. dirwalker dont close it. anything else close it
            self.terminate_process()

    def _prompt_tty(self):
        str_val = None
        if self.gpg_thread:
            str_val = "gpg passphrase"
        elif not self.is_polkit:
            str_val = "root password"
        if str_val:
            self.log.emit(f"Please enter {str_val} in terminal")
            self.status.emit(f"Please enter {str_val} in terminal")

    def terminate_process(self):
        if self.is_terminating:
            return
        self.is_terminating = True
        # self.process.kill()
        if self.is_running():
            subprocess.run([
                self.comm,
                self.script,
                "run",
                "kill",
                str(self.pid)
            ])
        #     self.log.emit("Process killed forcefully")
        else:
            self.is_terminating = False

    def _start_prompt_timer(self):
        self.prompt_timer = QTimer(self)
        self.prompt_timer.setSingleShot(True)
        self.prompt_timer.start(12000)
        self.prompt_timer.timeout.connect(self._prompt_tty)
        self.is_prompt_timer = True

    def _start_dispatch_process(self):
        self._start_prompt_timer()
        self.process.start(self.comm, self.script_list + self.args)
        self.pid = int(self.process.processId())

    def start_tomledit(self, cmd, args=None):
        self.process.start(cmd, args)
        self.pid = int(self.process.processId())

    def start_pyprocess(self, script, args=None, database=None, dbtarget=None, user=None, email=None, status_message=None, is_search=False, is_postop=False, is_scanIDX=False, ANALYTICSECT=None, parent=None):

        self.script = script
        self.script_list = [script]
        self.database = database
        self.dbtarget = dbtarget
        self.statusmsg = status_message
        self.is_search = is_search
        self.is_postop = is_postop
        self.is_scanIDX = is_scanIDX
        if ANALYTICSECT:
            self.st_time = time.time()
            self.ANALYTICSECT = True

        args = list(args) if args else []  # args = [str(a) for a in args if a is not None]

        if "findfile.py" in args:
            if self.rangeVALUE is not None:
                args += [self.rangeVALUE]
            if self.is_compress:
                args += [self.zipPROGRAM, self.zipPATH, self.USRDIR, self.downloads]
        self.args = args

        if self.is_polkit:
            self.comm = "pkexec"
        else:
            # hudt prompt to use terminal if polkit isnt installed
            self.comm = "sudo"
            self.script_list = ["env", f"XDG_RUNTIME_DIR={self.xdg_runtime}", script]

        # qt prompt
        rlt = start_gpg_agent(email)  # refresh the passphrase.
        if rlt is False:  # if the passphrase has expired
            self.gpg_thread = QThread(self)
            self.gpg_worker = GpgPromptWorker(dbtarget, user)
            self.gpg_worker.moveToThread(self.gpg_thread)
            self.gpg_thread.started.connect(self.gpg_worker.run)
            self.gpg_worker.finished.connect(self._on_gpg_prompt_finished)
            self.gpg_worker.finished.connect(self.gpg_thread.quit)
            self.gpg_worker.finished.connect(self.gpg_worker.deleteLater)
            self.gpg_thread.finished.connect(self.gpg_thread.deleteLater)
            self.gpg_thread.finished.connect(self._cleanup_gpg_thread)
            self._start_prompt_timer()
            # from PySide6.QtWidgets import QApplication
            # QApplication.processEvents()
            self.gpg_thread.start()

        else:
            self._start_dispatch_process()

    def process_finished(self, exit_code, exit_status):

        if self._stdout_buffer.strip():
            self.process_stdout_line(self._stdout_buffer.rstrip())
        self._stdout_buffer = ""

        if exit_code == 0:

            if self.dspEDITOR and self.result_path:

                display(self.dspEDITOR, self.result_path, True, self.dspPATH)  # open text editor?

            if self.ANALYTICSECT:  # powershell scripts
                el = time.time() - self.st_time
                self.log.emit(f'Search took {el:.3f} seconds')

            if self.database:  # sys index updates
                self.status.emit(f"{self.statusmsg} completed")

        else:
            if self.database:
                self.status.emit(f"{self.statusmsg} failed exit code {exit_code}")

        es_int = exit_status.value if isinstance(exit_status, QProcess.ExitStatus) else exit_status
        self.complete.emit(exit_code, es_int)

    def handle_progress(self, line):

        try:
            value_str = line.split("Progress:")[1].strip()
            percent_str = value_str.split('%')[0].strip()
            percent = int(float(percent_str))
            self.prog_v = percent
            self.progress.emit(percent)

            if percent >= 90.0 and self.database:
                self.status.emit("Waiting remaining worker(s) to finish")

        except ValueError:
            self.log.emit(f"Malformed progress line: {line}")

    def process_stdout_line(self, line):

        if "Progress:" in line:
            if self.is_prompt_timer:
                if self.prompt_timer.isActive():
                    self.prompt_timer.stop()
                self.is_prompt_timer = False

            self.handle_progress(line)
        elif line.startswith("RESULT:") and self.result_path is None:
            self.result_path = line.split(":", 1)[1].strip()
        else:
            if line.strip():
                self.log.emit(line)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        if not text:
            return

        self._stdout_buffer += text
        lines = self._stdout_buffer.split("\n")
        self._stdout_buffer = lines.pop()

        for line in lines:
            self.process_stdout_line(line.rstrip())

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf-8", errors="replace")
        if not stderr:
            return

        if stderr.strip():
            self.error.emit(stderr)
