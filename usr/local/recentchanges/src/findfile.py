import fnmatch
import os
import re
import subprocess
import sys
import threading
import traceback
import zipfile
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path
from .config import load_toml
from .configfunctions import get_config
from .dirwalkerfunctions import files_search
from .dirwalkerfunctions import get_base_folders
from .dirwalkerfunctions import get_relavant_mounts
from .dirwalkerfunctions import MOUNT_FOLDERS
from .findfileparser import build_parser
from .logs import setup_logger
from .pyfunctions import cprint
from .pyfunctions import escf_py
from .pyfunctions import unescf_py
from .pyfunctions import user_path
from .rntchangesfunctions import filter_lines_from_list
from .rntchangesfunctions import get_runtime_exclude_list
from .rntchangesfunctions import removefile
# 06/16/2026


def archive_failure_blk(result, file_list):
    rlt = result.returncode
    if rlt != 0:
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        missing = [f for f in file_list if not os.path.isfile(f)]
        if missing:
            print(f"debug: {len(missing)}/{len(file_list)} target files were not found")
            for item in missing:
                print(item)
        err = stdout + "\nstderr: " + stderr
        print(err)
        return 1
    return 0


# all in one for .zip using standard library. if strip duplicate retain absolute path
def zip_(complete, zipcmode, ziplevel, strip, zip_name="archive.zip"):

    modes = [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA]

    def comp_chart(user_choice):
        user_choice = max(1, min(user_choice, 9))
        index = int(round((user_choice - 1) / 8 * (len(modes) - 1)))
        return modes[index]

    compression = comp_chart(zipcmode)

    with zipfile.ZipFile(zip_name, "w", compression=compression, compresslevel=ziplevel) as zipf:
        for src, arcname in complete.items():
            if os.path.isfile(src):
                zipf.write(src, arcname=arcname)
            else:
                print(f"target skipped (not a file): {src}")

    return zip_name


def has_content(recent_files):
    try:
        with open(recent_files, 'r', encoding='utf-8') as f:
            return f.readline().strip() != ''
    except OSError:
        return False


# apply filter.py, filter out inclusions and decode any newline characters
# windows would add " " quotes to the paths for 7zip winrar
def encase_line(target_files, temp_dir, arch_exclude, usr, moduleNAME):
    results = []
    newline_char = False

    # exclude any search results from this app using fn match
    search_files = f"*{moduleNAME}*.txt"

    try:

        # apply user filter
        rows = [(p,) for p in target_files]

        escaped_user = re.escape(usr)
        n_line = filter_lines_from_list(rows, escaped_user, idx=0)
        if n_line is None:
            return None

        for row in n_line:
            line = row[0]
            if not line:
                continue

            line_path = line.lower()

            # filter out inclusions from the app
            if any(line_path.startswith(excl) for excl in arch_exclude):
                continue

            if fnmatch.fnmatch(line, search_files):
                continue

            if '\\\\n' in line:
                newline_char = True
            encased_line = unescf_py(line)

            results.append(encased_line)

        return (results, newline_char)
    except Exception as e:
        print(f"problem in encase_line {e} {type(e).__name__}")
        return None, False


def comp_archive(target_files, archive, temp_dir, downloads, arch_exclude, usr, moduleNAME, zipPROGRAM, zipPATH, tarcmode, tarclevel, zipcmode, ziplevel, strip):

    archflnm = archive + ".zip"
    if zipPROGRAM == "zip":
        relative_flg = "-j"  # junk files  # original relative_flg = "-@"  a filee archive would miss files with newline character
    elif zipPROGRAM == "tar":
        tar_filter = None
        prog = None
        if tarcmode == "tar":
            relative_flg = "-cf"
        elif tarcmode == "gz":
            relative_flg = "-czf"
            prog = "gzip"
        elif tarcmode == "bz2":
            relative_flg = "-cjf"
            prog = "bzip2"
        elif tarcmode == "xz":
            relative_flg = "-cJf"
            prog = tarcmode
        elif tarcmode == "zstd":
            relative_flg = "-cf"
            prog = tarcmode
        if tarclevel and tarcmode != "tar":
            relative_flg = "-cf"
            if tarcmode == "zstd":
                if tarclevel > 22:
                    tarclevel = 22
            else:
                if tarclevel > 9:
                    tarclevel = 9
            tar_filter = f"{prog} -{tarclevel}"
        suffix = '.tar' if tarcmode == "tar" else f'.tar.{tarcmode}'
        archflnm = archive + suffix
    elif zipPROGRAM != "zipfile":
        print("Unrecognized zip program skipping archive.")
        return 1

    xdata, newline_char = encase_line(target_files, temp_dir, arch_exclude, usr, moduleNAME)
    if xdata is None:
        return 1
    elif not xdata:
        return 0

    res = 1

    out_file = os.path.join(downloads, archflnm)
    removefile(out_file)
    out_two = ""
    try:

        # if there is a newline in filename or too many args use zipfile
        # if strip use zipfile. any duplicate uses absolute path
        # for tar find the duplicates and create a second .tar file
        duplicates = []
        uniques = []
        complete = {}

        bases = [os.path.basename(p) for p in xdata]
        counts = Counter(bases)

        for filepath, base in zip(xdata, bases):
            if counts[base] == 1:
                uniques.append(filepath)
                complete[filepath] = base
            else:
                duplicates.append(filepath)
                complete[filepath] = filepath

        if (
            zipPROGRAM == "zipfile" or
            (zipPROGRAM == "zip" and (len(xdata) > 50 or newline_char or strip))
        ):
            print("using zipfile")
            zip_(complete, zipcmode, ziplevel, strip, zip_name=out_file)
            res = 0
        else:

            cmd = [zipPATH]

            # at this point for zip its not strip
            if zipPROGRAM == "zip":
                uniques = list(xdata)
                if strip:
                    cmd += [relative_flg]
                cmd += [f"-{zipcmode}", out_file] + uniques
                data = None
                print('Running command:', ' '.join(cmd), flush=True)
                print()
                result = subprocess.run(
                    cmd,
                    input=data,
                    capture_output=True,
                    text=False
                )
                file_list = uniques
                if archive_failure_blk(result, file_list) == 0:
                    res = 0
                # would miss files with newline character as zip is new line delimited and filenames passed from stdin
                # cmd += [f"-{zipcmode}", out_file, relative_flg]
                # data = "\n".join(xdata).encode("utf-8")

            elif zipPROGRAM == "tar":

                # theory which would be ideal only write the duplicates to a temp dir this way to avoid exceeding memory size if the data  is too great
                # with hardware today this isnt so much of a problem. Windows copies files to a temp dir if strip option is true.
                #
                # this implementation write duplicates to a seperate .tar archive if strip is true. no temp dir required

                archflnm_two = archive + "_duplicate" + suffix
                out_two = os.path.join(downloads, archflnm_two)

                if strip and duplicates:
                    removefile(out_two)
                    cm_dupes = cmd.copy()
                    if tarcmode == "zstd" and not tarclevel:
                        cm_dupes += ["--zstd"]
                    if tar_filter:
                        cm_dupes += ["-I", tar_filter]
                    cm_dupes += [relative_flg, out_two, "--null", "-T", "-"]
                    data = b"\0".join(f.encode() for f in duplicates) + b"\0"

                    print('Running command:', ' '.join(cm_dupes), flush=True)
                    print()
                    result = subprocess.run(
                        cm_dupes,
                        input=data,
                        capture_output=True,
                        text=False
                    )
                    if archive_failure_blk(result, duplicates) != 0:
                        return 1

                    if os.path.isfile(out_two):
                        res = 0
                        print(f"duplicates appended to {archflnm_two}")

                if not strip or (strip and uniques):
                    if res != 0:
                        removefile(out_two)
                    res = 1
                    if tarcmode == "zstd":
                        cmd += ["--zstd"]
                    if tar_filter:
                        cmd += ["-I", tar_filter]
                    cmd += ["--ignore-failed-read"]

                    if strip:
                        cmd += ["--transform=s:.*/::"]

                    cmd += [relative_flg, out_file, "--null", "-T", "-"]

                    if not strip:
                        file_list = complete
                        data = b"\0".join(f.encode() for f in complete) + b"\0"
                    else:
                        file_list = uniques
                        data = b"\0".join(f.encode() for f in uniques) + b"\0"

                    print('Running command:', ' '.join(cmd), flush=True)
                    print()
                    result = subprocess.run(
                        cmd,
                        input=data,
                        capture_output=True,
                        text=False
                    )
                    if archive_failure_blk(result, file_list) == 0:
                        res = 0

        if res == 0:
            if (
                (os.path.isfile(out_file) and os.path.getsize(out_file) > 0)
                or (zipPROGRAM == "tar" and (os.path.isfile(out_two) and os.path.getsize(out_two) > 0))
            ):
                cprint.cyan(f"Archive created in: {out_file}")

    except FileNotFoundError as e:
        print(f"The file list for the archive is missing {target_files}. Error running zip program {zipPROGRAM} at {zipPATH} err: {e}")
    except Exception as e:
        print(f"An unexpected error happened while trying to compress {out_file}. {type(e).__name__} {e} traceback:\n {traceback.format_exc()}")

    return res


def main(localappdata, action, filename, extension, basedir, usr, dspEDITOR, dspPATH, temp_dir, log_path, cutoffTIME=None, zipPROGRAM=None, zipPATH=None, usrDIR=None, downloads=None):

    if not (filename or extension):
        print("Invalid input. exiting.")
        return 1

    current_time = datetime.now()

    localappdata = Path(localappdata)

    toml, json_file, home_dir, xdg_config, xdg_runtime, usr, uid, gid = get_config(localappdata, usr, platform="Linux")
    config = load_toml(toml)
    if not config:
        return 1
    exclDIRS = user_path(config['search']['exclDIRS'], usr)
    moduleNAME = config['paths']['moduleNAME']
    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if usr != "root" else root_log_file
    # dspEDITOR = config['display']['dspEDITOR']
    # if dspEDITOR:
    #     dspEDITOR = multi_value(dspEDITOR)
    tarcmode = config['compress']['tarcmode']
    tarclevel = config['compress']['tarclevel']
    zipcmode = config['compress']['zipcmode']
    ziplevel = config['compress']['ziplevel']
    strip = config['compress']['strip']

    log_file = home_dir / ".local" / "state" / "recentchanges" / "logs" / log_file

    archive = moduleNAME
    tgt_file = archive + 'xfindfiles.txt'

    recent_files = os.path.join(temp_dir, tgt_file)  # result output

    search_list = []
    target_files = []

    tmn = str(cutoffTIME)

    res = 1

    try:
        exclDIRS_fullpath = [os.path.join(basedir, d) for d in exclDIRS]

        if action == "find":
            arge = []

            F = ["find", basedir, "-xdev"]

            baselen = len(exclDIRS_fullpath)
            skipped = [os.path.join(basedir, m) for m in MOUNT_FOLDERS]  # using xdev skip the mount excludes
            PRUNE = ["("]
            for i, d in enumerate(exclDIRS_fullpath):
                if d in skipped:
                    continue
                PRUNE += ["-path", d]
                if i < baselen - 1:
                    PRUNE.append("-o")
            PRUNE += [")", "-prune", "-o"]

            TAIL = ["-not", "-type", "d"]

            # build the folders that are searched to output to user

            base_folders, _ = get_base_folders(basedir, exclDIRS_fullpath)
            for folder in base_folders:
                # if folder == "/":
                #     continue
                search_list.append(folder)

            mounts = get_relavant_mounts(exclDIRS_fullpath)

            find_command = F + PRUNE

            # zero means compress all results
            if cutoffTIME is not None:
                if cutoffTIME != '0':
                    find_command += ["-mmin", f"-{tmn}"]

            if filename and not extension:
                arge = ["-iname", filename + "*", "-print0"]
            elif not filename and extension:
                arge = ["-name", f"*{extension}", "-print0"]
            elif filename and extension:
                has_ext = bool(os.path.splitext(filename)[1])
                if has_ext:
                    print(f"Searching for {filename}{extension}\n")
                arge = ["-iname", f"{filename}*{extension}", "-print0"]

            find_command += TAIL
            find_command += arge

            secondary = []
            if mounts:
                secondary = ["find", *mounts] + TAIL + arge

            result_inclusion = ".txt" in filename or ".txt" in extension

            is_progress = True
            total_count = 1
            base_folder_paths = []
            try:
                for item in os.listdir(basedir):
                    b_path = os.path.join(basedir, item)
                    if os.path.isdir(b_path):
                        base_folder_paths.append(b_path)
            except (OSError, PermissionError):
                is_progress = False

            y = len(base_folder_paths)
            is_progress = y > 0

            search_paths = 'Running command:' + ' '.join(["find"] + search_list + TAIL + arge)
            print(search_paths)
            # print('Running command:', ' '.join(find_command), flush=True) # debug
            print()

            comm = [find_command]
            if secondary:
                comm.append(secondary)
                total_count = 2

            def process_stderr(stderr_pipe, sink):
                try:
                    for raw in iter(stderr_pipe.readline, b''):
                        text = raw.decode("utf-8", errors="replace").strip()
                        if text:
                            sink.append(text)
                finally:
                    stderr_pipe.close()

            open(recent_files, "w").close()

            x = 0
            last_progress = 0
            stderr_thread = None
            stderr_output = []
            for cmd in comm:

                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.stderr is not None:
                    stderr_thread = threading.Thread(target=process_stderr, args=(proc.stderr, stderr_output), daemon=True)
                    stderr_thread.start()

                buffer = b''

                emitted = set()
                with open(recent_files, "a", encoding="utf-8") as f1:
                    while True:
                        if proc.stdout is None:
                            break
                        chunk = proc.stdout.read(8192)
                        if not chunk:
                            break
                        buffer += chunk
                        while b'\0' in buffer:
                            part, buffer = buffer.split(b'\0', 1)
                            if part.strip():

                                otline = part.decode("utf-8", errors="replace")
                                if otline:

                                    if is_progress and x == 0:
                                        for i, prefix in enumerate(base_folder_paths, start=1):
                                            if otline.startswith(prefix):
                                                if i not in emitted:
                                                    last_progress = round(((i / y) * 100) / total_count, 2)
                                                    print(f"Progress: {last_progress}", flush=True)
                                                    emitted.add(i)
                                                break

                                    if not (result_inclusion and otline == recent_files):

                                        # if downloads is not None:
                                        cline = escf_py(otline.rstrip('\n'))
                                        target_files.append(cline)

                                        f1.write(otline + '\n')
                                        print(otline, flush=True)

                    if buffer.strip():
                        try:
                            otline = buffer.decode('utf-8', errors='replace')
                            if os.path.isfile(otline):

                                cline = escf_py(otline.rstrip('\n'))
                                target_files.append(cline)
                                print(otline)
                        except Exception as e:
                            print(f"fault in trailing buffer ignored. {type(e).__name__} {e}")
                            pass

                if proc.stdout is not None:
                    proc.stdout.close()
                proc.wait()
                if stderr_thread is not None:
                    stderr_thread.join()

                if proc.returncode not in (0, 1):
                    errors = "\n".join(stderr_output)
                    if errors:
                        print(errors)
                    print()
                    print("Find failed unable to continue. quitting")
                    return proc.returncode
                if is_progress and x > 0:
                    if last_progress < 90:
                        print("Progress: 90%", flush=True)
                stderr_thread = None
                proc = None
                x += 1

        elif action == "python":

            out_text = ""

            logging_values = (localappdata, ll_level)
            logger = setup_logger(log_file, logging_values[1], "FINDFILE")

            search_start_dt = None
            if cutoffTIME is not None:
                if cutoffTIME != '0':
                    search_start_dt = (current_time - timedelta(minutes=tmn))  # if zero is specified means to compress all results dont filter by time if zero

            if filename and not extension:
                mode = 1
                out_text = f"filename: {filename}"
            elif not filename and extension:
                mode = 2
                out_text = f"extn: {extension}"
            if filename and extension:
                out_text = filename + extension
                has_ext = bool(os.path.splitext(filename)[1])
                if has_ext:
                    print(f"Searching for {out_text}\n")
                mode = 3
            print(f'Running os.scandir for {out_text}', flush=True)
            feedback = True
            iqt = True

            target_files, _ = files_search(basedir, search_start_dt, feedback, exclDIRS, exclDIRS_fullpath, filename, extension, mode, iqt, logger, strt=0, endp=100)

            if target_files:
                with open(recent_files, "w", encoding="utf-8") as f1:
                    for otline in target_files:
                        print(otline, file=f1)

        if target_files is None:
            return 1
        elif target_files and os.path.isfile(recent_files) and os.path.getsize(recent_files) != 0:
            print()

            if cutoffTIME is not None and downloads:

                pst_data = home_dir / ".local" / "share" / "recentchanges"
                flth_frm = pst_data / "flth.csv"  # filter hits
                dbtarget_frm = pst_data / "recent.gpg"
                cache_f_frm = pst_data / "ctimecache.gpg"
                cache_s_frm = pst_data / "systimeche.gpg"
                file_out = xdg_runtime / "file_output"
                flth = str(flth_frm)
                dbtarget = str(dbtarget_frm)
                cache_f = str(cache_f_frm)
                cache_s = str(cache_s_frm)
                cache_s, _ = os.path.splitext(cache_s)  # to match all profiles and index drives

                gnupg_home = None
                # exclude certain files from .rar/.zip. app inclusions and temp work area

                arch_exclude = get_runtime_exclude_list(
                    usrDIR, moduleNAME, usr, str(file_out), flth, dbtarget, cache_f,
                    cache_s, gnupg_home, str(log_path), recent_files
                )

                res = comp_archive(
                    target_files, archive, temp_dir, downloads, arch_exclude, usr,
                    moduleNAME, zipPROGRAM, zipPATH, tarcmode, tarclevel,
                    zipcmode, ziplevel, strip
                )

            # elif downloads and cutoffTIME is not None:
            #     res = 1
            #     print(f"no archive path list: {target_files} couldnt compress")
            print(f"RESULT: {recent_files}")
            # display(dspEDITOR, recent_files, dspPATH, True)  # cant open as root for compatibility and security *
            if res != 0:
                pass
                # return 1
        print("Progress: 100%")
        return 0

    except Exception as e:
        print(f'An error occurred in findfile: {type(e).__name__} err: {e} \n {traceback.format_exc()}')
        return 1


def main_entry(argv):
    parser = build_parser()
    args = parser.parse_args(argv)

    calling_args = [
        args.appdata,
        args.action,
        args.filename,
        args.extension,
        args.basedir,
        args.user,
        args.dspEDITOR,
        args.dspPATH,
        args.temp_dir,
        args.log_path,
        args.cutoffTIME,
        args.zipPROGRAM,
        args.zipPATH,
        args.usrDIR,
        args.downloads
    ]
    result = main(*calling_args)
    sys.exit(result)
