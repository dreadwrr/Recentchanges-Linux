import fnmatch
import os
import re
import subprocess
import sys
import threading
import traceback
import zipfile
from collections import Counter
from .configfunctions import find_install
from .configfunctions import get_config
from .configfunctions import load_toml
from .findfileparser import build_parser
from .pyfunctions import cprint
from .pyfunctions import escf_py
from .pyfunctions import unescf_py
from .pyfunctions import user_path
from .rntchangesfunctions import filter_lines_from_list
from .rntchangesfunctions import get_runtime_exclude_list
from .rntchangesfunctions import removefile

# 02/20/2026


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
def encase_line(target_files, temp_dir, arch_exclude, USR, MODULENAME):
    results = []
    newline_char = False

    # exclude any search results from this app using fn match
    search_files = f"*{MODULENAME}*.txt"

    try:
        # apply filter.py
        escaped_user = re.escape(USR)
        n_line = filter_lines_from_list(target_files, escaped_user, idx=0)

        # target_out = archive + ".txt"
        # target_out = os.path.join(temp_dir, target_files)   # if using file archive

        # with open('/tmp/encoded', "w", encoding='utf-8') as f:

        for line in n_line:

            line_path = line.lower()

            # filter out inclusions from the app
            if any(line_path.startswith(excl.lower()) for excl in arch_exclude):
                continue
            # filter out result files
            if fnmatch.fnmatch(line, search_files):
                continue
            # encased_line = f'"{line}"'
            if '\\\\n' in line:
                newline_char = True
            encased_line = unescf_py(line)

            # f.write(encased_line + "\n")
            results.append(encased_line)

        return (results, newline_char)
    except Exception as e:
        print(f"problem in encase_line {e} {type(e).__name__}")
        return None, False


def comp_archive(target_files, archive, temp_dir, downloads, arch_exclude, USR, MODULENAME, zipPROGRAM, zipPATH, tarclvl, zipcmode, ziplevel, strip):

    if zipPROGRAM == "zip":
        relative_flg = "-j"  # junk files  # original relative_flg = "-@"  a filee archive would miss files with newline character
        archflnm = archive + ".zip"

    elif zipPROGRAM == "tar":
        if tarclvl == "tar":
            relative_flg = "-cf"
        elif tarclvl == "gz":
            relative_flg = "-czf"
        elif tarclvl == "bz2":
            relative_flg = "-cjf"
        elif tarclvl == "xz":
            relative_flg = "-cJf"
        elif tarclvl == "zstd":
            relative_flg = "-cf"
        suffix = '.tar' if tarclvl == "tar" else f'.tar.{tarclvl}'
        archflnm = archive + suffix
    else:
        print("Unrecognized zip program skipping archive.")
        return 1

    xdata, newline_char = encase_line(target_files, temp_dir, arch_exclude, USR, MODULENAME)
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

        if zipPROGRAM == "zip" and (len(xdata) > 50 or newline_char or strip):
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
                result = subprocess.run(
                    cmd,
                    input=data,
                    capture_output=True,
                    text=False
                )
                file_list = uniques
                if archive_failure_blk(result, file_list) == 0:
                    res = 0
                # would miss files with newline character as zip is new line delimited
                # cmd += [f"-{zipcmode}", out_file, relative_flg]
                # data = "\n".join(xdata).encode("utf-8")

            elif zipPROGRAM == "tar":

                # write only duplicates to qt temp dir this way to avoid exceeding memory size if the data  is too great
                archflnm_two = archive + "_duplicate" + suffix
                out_two = os.path.join(downloads, archflnm_two)

                if strip and duplicates:
                    removefile(out_two)
                    cm_dupes = cmd.copy()
                    if tarclvl == "zstd":
                        cm_dupes += ["--zstd"]
                    cm_dupes += [relative_flg, out_two, "--null", "-T", "-"]
                    data = b"\0".join(f.encode() for f in duplicates) + b"\0"

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
                    if tarclvl == "zstd":
                        cmd += ["--zstd"]

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


def main(filename, extension, basedir, USR, dspEDITOR, dspPATH, temp_dir, cutoffTIME=None, zipPROGRAM=None, zipPATH=None, USRDIR=None, downloads=None):

    if not (filename or extension):
        print("Invalid input. exiting.")
        return 1

    localappdata = find_install()
    log_path = localappdata / "logs" / "errs.log"

    toml, json_file, home_dir, xdg_config, xdg_runtime, USR, uid, gid = get_config(localappdata, USR)
    config = load_toml(toml)
    if not config:
        return 1
    EXCLDIRS = user_path(config['search']['EXCLDIRS'], USR)
    MODULENAME = config['paths']['MODULENAME']
    tarclvl = config['compress']['tarclvl']
    zipcmode = config['compress']['zipcmode']
    ziplevel = config['compress']['ziplevel']
    strip = config['compress']['strip']

    archive = MODULENAME
    tgt_file = archive + 'xfindfiles.txt'

    recent_files = os.path.join(temp_dir, tgt_file)  # result output

    target_files = []

    tmn = str(cutoffTIME)

    res = 1

    try:

        arge = []

        F = ["find", basedir]

        PRUNE = ["("]
        for i, d in enumerate(EXCLDIRS):
            PRUNE += ["-path", os.path.join(basedir, d.replace('$', '\\$'))]
            if i < len(EXCLDIRS) - 1:
                PRUNE.append("-o")
        PRUNE += [")", "-prune", "-o"]

        TAIL = ["-not", "-type", "d"]

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

        result_inclusion = ".txt" in filename or ".txt" in extension

        is_progress = True
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

        print('Running command:', ' '.join(find_command))
        print()

        stderr_thread = None
        stderr_output = []
        proc = subprocess.Popen(find_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def process_stderr(stderr_pipe, sink):
            try:
                for raw in iter(stderr_pipe.readline, b''):
                    text = raw.decode("utf-8", errors="replace").strip()
                    if text:
                        sink.append(text)
            finally:
                stderr_pipe.close()

        if proc.stderr is not None:
            stderr_thread = threading.Thread(target=process_stderr, args=(proc.stderr, stderr_output), daemon=True)
            stderr_thread.start()

        buffer = b''

        with open(recent_files, "w", encoding="utf-8") as f1:
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
                            for i, prefix in enumerate(base_folder_paths, start=1):
                                if otline.startswith(prefix):
                                    if is_progress:
                                        print(f"Progress: {round((i / y) * 100, 2)}", flush=True)
                                        break

                            if not (result_inclusion and otline == recent_files):

                                if downloads is not None:
                                    cline = escf_py(otline.rstrip('\n'))
                                    target_files.append(cline)
                                print(otline)
                                f1.write(otline + '\n')

            if buffer.strip():
                try:
                    otline = buffer.decode('utf-8', errors='replace')
                    if os.path.isfile(otline):
                        if cutoffTIME is not None:
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

        res = 0

        if res == 0 and os.path.isfile(recent_files) and os.path.getsize(recent_files) != 0:
            print()
            if target_files and downloads is not None:
                pst_data = home_dir / ".local" / "share" / "recentchanges"
                flth_frm = pst_data / "flth.csv"  # filter hits
                dbtarget_frm = pst_data / "recent.gpg"
                CACHE_F_frm = pst_data / "ctimecache.gpg"
                CACHE_S_frm = pst_data / "systimeche.gpg"
                file_out = xdg_runtime / "file_output"
                flth = str(flth_frm)
                dbtarget = str(dbtarget_frm)
                CACHE_F = str(CACHE_F_frm)
                CACHE_S = str(CACHE_S_frm)
                CACHE_S, _ = os.path.splitext(CACHE_S)  # to match all profiles and index drives

                # exclude certain files from .rar/.zip. app inclusions and temp work area
                #
                #
                arch_exclude = get_runtime_exclude_list(USRDIR, MODULENAME, USR, str(file_out), flth, dbtarget, CACHE_F, CACHE_S, str(log_path), recent_files)  # dbopt=None, temp_dir=None

                res = comp_archive(target_files, archive, temp_dir, downloads, arch_exclude, USR, MODULENAME, zipPROGRAM, zipPATH, tarclvl, zipcmode, ziplevel, strip)

            elif downloads is not None and cutoffTIME is not None:
                res = 1
                print("no archive path list: target_files. couldnt compress")

            print(f"RESULT: {recent_files}")

            # display(dspEDITOR, recent_files, True, dspPATH)  # cant open as root for compatibility and security *

        if res == 0:
            print("Progress: 100%")
        return res

    except Exception as e:
        print(f'An error occurred in findfile: {type(e).__name__} err: {e} \n {traceback.format_exc()}')
        return 1


def main_entry(argv):
    parser = build_parser()
    args = parser.parse_args(argv)

    calling_args = [
        args.filename,
        args.extension,
        args.basedir,
        args.user,
        args.dspEDITOR,
        args.dspPATH,
        args.temp_dir,
        args.cutoffTIME,
        args.zipPROGRAM,
        args.zipPATH,
        args.USRDIR,
        args.downloads
    ]
    result = main(*calling_args)
    sys.exit(result)
