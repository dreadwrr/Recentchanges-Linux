#!/usr/bin/env python3
#   Porteus                                                                           02/08/2026
#   recentchanges. Developer buddy      recentchanges and recentchanges search
#   Provide ease of pattern finding ie what files to block we can do this a number of ways
#   1) if a file was there (many as in more than a few) and another search lists them as deleted its either a sys file or not but unwanted nontheless
#   2) Is a system file inherent to the specifc platform
#   3) intangibles ie trashed items that may pop up infrequently and are not known about
#
#   This script is called by two methods. recentchanges and recentchanges search. The former is discussed below
#
#   recentchanges
#           Searches are saved in /tmp. make xzm
#           1. Search results are unfiltered and copied files for the .xzm are from a filter.
#
#           The purpose of this script is to save files ideally less than 5 minutes old. So when compiling or you dont know where some files are
#   or what changed on your system. So if you compiled something you call this script to build a module of it for distribution. If not using for developing
#   call it a file change snapshot
#   We use the find command to list all files 5 minutes or newer. Filter it and then get to copying the files in a temporary staging directory.
#   Then take those files and make an .xzm. It will be placed in   /tmp  along with a transfer log to staging directory and file manifest of the xzm
#
#   recentchanges search
#           Searches are saved in /home/{user}/Downloads
#
#           This has the same names as `recentchanges` but also includes /tmp files and or a filesearch.
#           1. old searches can be grabbed from /Downloads, /tmp or /tmp/{MODULENAME}_MDY. for convenience if there is no differences it displays the old search for specified search criteria
#           2. The search is unfiltered and a filesearch is filtered.
#           2. rnt search inverses the results. For a standard search it will filter the results. For a file search it removes the filter.
#
#  Also borrowed script features from various scripts on porteus forums
import logging
import os
import re
import signal
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from . import processha
from .configfunctions import check_config
from .configfunctions import find_install
from .configfunctions import get_config
from .configfunctions import load_toml
from .configfunctions import update_toml_values
from .dirwalker import scan_system
from .dirwalkerfunctions import get_base_folders
from .filterhits import update_filter_csv
from .gpgcrypto import decr_ctime
from .gpgcrypto import encr_cache
from .inotifyfunctions import init_recentchanges
from .logs import setup_logger
from .pstsrg import main as pst_srg
from .pyfunctions import cprint
from .pyfunctions import user_path
from .qtdrivefunctions import setup_drive_cache
from .recentchangessearchparser import build_parser
from .rntchangesfunctions import build_tsv
from .rntchangesfunctions import change_perm
from .rntchangesfunctions import check_stop
from .rntchangesfunctions import clear_logs
from .rntchangesfunctions import copy_files
from .rntchangesfunctions import filter_lines_from_list
from .rntchangesfunctions import filter_output
from .rntchangesfunctions import find_files
from .rntchangesfunctions import get_diff_file
from .rntchangesfunctions import get_runtime_exclude_list
from .rntchangesfunctions import hsearch
from .rntchangesfunctions import logic
from .rntchangesfunctions import name_of
from .rntchangesfunctions import porteus_linux_check
from .rntchangesfunctions import removefile
from .rntchangesfunctions import time_convert


# Globals
stopf = False
is_mcore = False


def sighandle(signum, frame):
    global stopf
    global is_mcore
    if signum in (signal.SIGINT, signal.SIGTERM):
        if signum == 2:
            print("Exit on ctrl-c", flush=True)
            sys.exit(0)
        stopf = True
        # print("Sending stop request", flush=True)
        # if is_mcore:
        # else:
        #     print("Exit on ctrl-c", flush=True)
        #     sys.exit(0)


'''
 init 0 - 20 %
 main search 20 - 60 %
 processing 60 - 65%
 pstsrg 65% - 90%
 pstsrg with POSTOP 65 - 85%
 pstsrg with scanIDX 65 - 80%
 pstsrg with POSTOP and scanIDX 65 - 75%
'''


def main(argone, argtwo, USR, pwrd, argf="bnk", method="", iqt=False, drive=None, dbopt=None, CACHE_S=None, POST_OP=False, scan_idx=False, showDiff=False, dspPATH=None):

    # has_tty = sys.stdin.isatty() and sys.stderr.isatty()
    # if has_tty:
    #     print("tty from qt")
    # else:
    #     print("No tty")

    signal.signal(signal.SIGINT, sighandle)
    signal.signal(signal.SIGTERM, sighandle)

    if argf not in ("bnk", "filtered", ""):
        print("please call from /usr/local/bin/recentchanges")
        sys.exit(1)
    if method != "rnt" and argone.lower() != "search":
        print("exiting not a search")
        sys.exit(1)
    if not iqt:
        caller_script = Path(sys.argv[0]).resolve()
        launcher = os.path.basename(caller_script)
        if str(launcher) != "rntchanges.py":
            print("please call from recentchanges from /usr/local/bin")
            sys.exit(1)

    global is_mcore

    appdata_local = find_install()  # appdata software install aka workdir
    toml_file, json_file, home_dir, xdg_config, xdg_runtime, USR, uid, gid = get_config(appdata_local, USR)

    script_dir = appdata_local / "scripts"
    inotify_creation_file = Path("/tmp/file_creation_log.txt")
    pst_data = home_dir / ".local" / "share" / "recentchanges"
    flth_frm = pst_data / "flth.csv"  # filter hits
    dbtarget_frm = pst_data / "recent.gpg"
    CACHE_F_frm = pst_data / "ctimecache.gpg"
    CACHE_S_frm = pst_data / "systimeche.gpg"
    toml_default = home_dir / ".config" / "config.bak"
    file_out = xdg_runtime / "file_output"  # holds result filename for bash
    flth = str(flth_frm)
    dbtarget = str(dbtarget_frm)
    CACHE_F = str(CACHE_F_frm)
    CACHE_S_str = str(CACHE_S_frm)

    config = load_toml(toml_file)
    if not config:
        return 1
    FEEDBACK = config['analytics']['FEEDBACK']
    ANALYTICS = config['analytics']['ANALYTICSECT']
    ANALYTICSECT = config['analytics']['ANALYTICSECT']
    email = config['backend']['email']
    autooutput = config['src']['autooutput']
    xzmname = config['src']['xzmname']
    cmode = config['src']['cmode']
    checksum = config['diagnostics']['checkSUM']
    cdiag = config['diagnostics']['cdiag']
    scanIDX = config['diagnostics']['scanIDX']
    suppress_browser = config['diagnostics']['supbrw']
    suppress = config['diagnostics']['suppress']
    POSTOP = config['diagnostics']['POSTOP']
    ps = config['shield']['proteusSHIELD']  # proteus shield
    show_diff = config['diagnostics']['showDIFF']
    compLVL = config['logs']['compLVL']
    MODULENAME = config['paths']['MODULENAME']
    archivesrh = config['search']['archivesrh']
    basedir = config['search']['drive']  # main drive for search
    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if USR != "root" else root_log_file
    EXCLDIRS = user_path(config['search']['EXCLDIRS'], USR)
    xRC = config['search']['xRC']
    driveTYPE = config['search']['driveTYPE']
    if driveTYPE.lower() == "ssd":
        is_mcore = True
    # email_name = config['backend']['name']
    # dspEDITOR = config['display']['dspEDITOR']
    # if dspEDITOR:
    #     dspEDITOR = multi_value(dspEDITOR)
    # dspPATH_frm = config['display']['dspPATH'].rstrip('/')

    # make a named tuple or dict for args and to pass less args for clarity
    user_setting = {
        'USR': USR,
        'email': email,
        'driveTYPE': driveTYPE,
        'FEEDBACK': FEEDBACK,
        'ANALYTICS': ANALYTICS,
        'ANALYTICSECT': ANALYTICSECT,
        'checksum': checksum,
        'ps': ps,
        'cdiag': cdiag,
        'compLVL': compLVL
    }

    # init

    if iqt:
        basedir = drive
        show_diff = showDiff
        POSTOP = POST_OP
        scanIDX = scan_idx
    else:

        # opening editor as root is disabled
        # dspPATH = ""
        # if dspEDITOR:  # user wants results output in text editor
        #       dspEDITOR, dspPATH = resolve_editor(dspEDITOR, dspPATH_frm, toml_file)  # verify we have a working one
        #       if not dspEDITOR and not dspPATH:
        #           return 1

        outfile = name_of(dbtarget, '.db')
        dbopt = os.path.join(pst_data, outfile)

        if ps or scanIDX:
            proteusPATH = config['shield']['proteusPATH']
            nogo = user_path(config['shield']['nogo'], USR)
            suppress_list = user_path(config['shield']['filterout'], USR)
            if not check_config(proteusPATH, nogo, suppress_list):
                return 1

        # if the drive type is not set auto detect it and update toml. look in json for partuuid and build CACHE_S
        #
        # if for some reason the mount changed for the drive update the json, rename the cache files and rename database tables

        j_settings = None
        if argone == "downloads":
            j_settings = {}

        CACHE_S, _, suffix, driveTYPE = setup_drive_cache(basedir, appdata_local, dbopt, dbtarget, json_file, toml_file, CACHE_S_str, driveTYPE, USR, email, compLVL, j_settings=j_settings)
        if not CACHE_S or not suffix:
            return 1

    # end init

    # VARS
    log_file = home_dir / ".local" / "state" / "recentchanges" / "logs" / log_file
    escaped_user = re.escape(USR)

    TMPOUTPUT = []  # holding
    # Searches
    RECENT = []  # main results
    tout = []  # ctime results
    SORTCOMPLETE = []  # combined
    TMPOPT = []  # filtered from sortcomplete

    # NSF
    COMPLETE_1, COMPLETE_2 = [], []
    COMPLETE = []  # combined

    # Diff file
    difference = []
    ABSENT = []  # actions
    rout = []  # actions from ha

    cfr = {}  # cache dict
    RECENTNUL = b""  # filepaths `recentchanges`

    start = end = cstart = cend = ag = 0
    validrlt = tmn = filename = search_time = search_paths = None

    diffrlt = False
    nodiff = False
    syschg = False
    flsrh = False
    is_porteus = True

    dcr = False  # means to remove after encrypting.

    flnm = ""
    parseflnm = ""
    diff_file = ""

    filepath = ""
    DIRSRC = ""

    tsv_doc = "doctrine.tsv"

    proval = 20  # progress
    endval = 30

    fmt = "%Y-%m-%d %H:%M:%S"

    USRDIR = os.path.join(home_dir, "Downloads")
    os.makedirs(USRDIR, mode=0o755, exist_ok=True)

    F = ["find", basedir]

    search_list = []
    try:

        baselen = len(EXCLDIRS)
        PRUNE = ["("]
        for i, d in enumerate(EXCLDIRS):
            PRUNE += ["-path", os.path.join(basedir, d.replace('$', '\\$'))]
            if i < baselen - 1:
                PRUNE.append("-o")
        PRUNE += [")", "-prune",  "-o"]

        # build the folders that are searched to output to user

        EXCLDIRS_FULLPATH = [os.path.join(basedir, d) for d in EXCLDIRS]
        base_folders, _ = get_base_folders(basedir, EXCLDIRS_FULLPATH)
        for folder in base_folders:
            if folder == "/":
                continue
            search_list.append(folder)

    except Exception as e:
        print("Problem with EXCLDIRS setting. using default search", toml_file)
        print("Error: ", e)
        if basedir != "/":
            sys.exit(1)
        F = [
            "find",
            "/bin", "/etc", "/home", "/lib", "/lib64", "/opt", "/root", "/sbin", "/tmp", "/usr",  "/var"
        ]
        PRUNE = []
        search_list = []

    TAIL = ["-not", "-type", "d", "-printf", "%T@ %A@ %C@ %i %M %n %s %u %g %m %p\\0"]

    mmin = []
    cmin = []

    TEMPD = tempfile.gettempdir()

    with tempfile.TemporaryDirectory(dir=TEMPD) as tempwork:

        scr = os.path.join(tempwork, "scr")  # feedback
        cerr = os.path.join(tempwork, "cerr")  # priority

        logging_values = (log_file, ll_level, appdata_local, tempwork)

        setup_logger(log_file, logging_values[1], "MAIN")
        change_perm(log_file, uid, gid)

        start = time.time()

        cfr = decr_ctime(CACHE_F, USR, iqt)

        # initialize

        # load ctime or files created or copied with preserved metadata.
        # if xRC
        tout = init_recentchanges(script_dir, home_dir, xdg_runtime, inotify_creation_file, cfr, xRC, checksum, MODULENAME, log_file)

        if argone != "search":
            THETIME = argone
        else:
            THETIME = argtwo

        # search criteria
        if THETIME != "noarguser":
            p = 60
            try:
                argone = int(THETIME)
                tmn = time_convert(argone, p, 2)
                search_time = tmn
                cprint.cyan(f"Searching for files {argone} seconds old or newer")

            except ValueError:  # its a file search

                argone = ".txt"
                if not os.path.isdir(pwrd):
                    print(f'Invalid argument {pwrd}. PWD required.')
                    sys.exit(1)
                os.chdir(pwrd)

                filename = argtwo  # sys.argv[2]
                if not os.path.isfile(filename) and not os.path.isdir(filename):
                    print('No such directory, file, or integer.')
                    sys.exit(1)

                parseflnm = os.path.basename(filename)
                if not parseflnm:  # get directory name
                    parseflnm = filename.rstrip('/').split('/')[-1]
                if parseflnm.endswith('.txt'):
                    argone = ""
                cprint.cyan(f"Searching for files newer than {filename}")
                flsrh = True
                ct = int(time.time())
                frmt = int(os.stat(filename).st_mtime)
                ag = ct - frmt
                ag = time_convert(ag, p, 2)
                search_time = ag

        else:
            tmn = search_time = argone = 5
            cprint.cyan('Searching for files 5 minutes old or newer')

        if iqt:
            print(f"Progress: {proval}", flush=True)

        # sys.stdout.flush()

        # Main search

        current_time = datetime.now()
        search_start_dt = (current_time - timedelta(minutes=search_time))
        logger = logging.getLogger("FSEARCH")

        if tout:
            mmin = ["-mmin", f"-{search_time}"]
            if search_list:
                search_paths = 'Running command:' + ' '.join(["find"] + search_list + mmin + TAIL)

            find_command_mmin = F + PRUNE + mmin + TAIL
            init = True
            endval += 30

            RECENT, COMPLETE_1, RECENTNUL, end, cstart = find_files(
                find_command_mmin, search_paths, "main", RECENT, COMPLETE_1, RECENTNUL, init, cfr,
                search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, strt=proval, endp=endval, logger=logger
            )

        else:
            cmin = ["-cmin", f"-{search_time}"]
            current_time = datetime.now()
            if search_list:
                search_paths = 'Running command:' + ' '.join(["find"] + search_list + cmin + TAIL)  # Windows

            find_command_cmin = F + PRUNE + cmin + TAIL
            init = True

            tout, COMPLETE_2, RECENTNUL, end, cstart = find_files(
                find_command_cmin, search_paths, "ctime", tout, COMPLETE_2, RECENTNUL, init, cfr,
                search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, strt=proval, endp=endval, logger=logger
            )

            cmin_end = time.time()
            cmin_start = current_time.timestamp()
            cmin_offset = time_convert(cmin_end - cmin_start, 60, 2)
            check_stop(stopf)
            mmin = ["-mmin", f"-{search_time + cmin_offset:.2f}"]
            if search_list:
                search_paths = 'Running command:' + ' '.join(["find"] + search_list + mmin + TAIL)
            find_command_mmin = F + PRUNE + mmin + TAIL
            proval += 10
            endval += 30
            init = False

            RECENT, COMPLETE_1, RECENTNUL, end, cstart = find_files(
                find_command_mmin, search_paths, "main", RECENT, COMPLETE_1, RECENTNUL, init, cfr,
                search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, strt=proval, endp=endval, logger=logger
            )

        cend = time.time()

        # end Main search

        check_stop(stopf)
        if RECENT:
            if cfr:

                encr_cache(cfr, CACHE_F, USR, uid, gid, email, compLVL)
        else:
            cprint.cyan("No new files found")
            if iqt:
                print("Progress: 100.00%")
            return 0

        COMPLETE = COMPLETE_1 + COMPLETE_2  # nsf append to rout in pstsrg before stat insert
        proval = 60  # current progress
        endval = 90  # next

        SORTCOMPLETE = RECENT

        SORTCOMPLETE.sort(key=lambda x: x[0])  # get everything from the start time

        SRTTIME = SORTCOMPLETE[0][0]  # store the start time
        merged = SORTCOMPLETE[:]

        for entry in tout:
            if not entry:
                continue
            tout_dt = entry[0]
            if tout_dt >= SRTTIME:
                merged.append(entry)
        merged.sort(key=lambda x: x[0])

        seen = {}

        for entry in merged:
            if len(entry) < 11:
                continue

            filepath = entry[1]
            cam_flag = entry[10]

            key = filepath

            if key not in seen:
                seen[key] = entry
            else:
                existing_entry = seen[key]
                existing_cam = existing_entry[10]

                if existing_cam == "y" and cam_flag is None:
                    seen[key] = entry

        deduped = list(seen.values())

        # inclusions from this script /  sort -u
        patts = get_runtime_exclude_list(USRDIR, MODULENAME, USR, str(file_out), flth, dbtarget, CACHE_F, CACHE_S, str(log_file), str(toml_default))

        exclude_patterns = [p for p in patts if p]

        def filepath_included(filepath, exclude_patterns):
            filepath = filepath.lower()
            return not any(filepath.startswith(p.lower()) for p in exclude_patterns)

        SORTCOMPLETE = [
            entry for entry in deduped
            if filepath_included(entry[1], exclude_patterns)
        ]

        # get everything before the end time to exclude weird files created in the future. Doesnt happen on windows **
        if not flsrh:
            start_dt = SRTTIME
            range_sec = 300 if THETIME == 'noarguser' else int(THETIME)
            end_dt = start_dt + timedelta(seconds=range_sec)
            lines = [entry for entry in SORTCOMPLETE if entry[0] <= end_dt]
        else:
            lines = SORTCOMPLETE

        # filter out the /tmp files
        patterns = tuple(p for p in ('/tmp',) if isinstance(p, str) and p)
        tmp_lines = []
        non_tmp_lines = []

        for entry in lines:
            if entry[1].startswith(patterns):
                tmp_lines.append(entry)
            else:
                non_tmp_lines.append(entry)

        # tmp_lines = [entry for entry in lines if entry[1].startswith("/tmp")]  # original
        # non_tmp_lines = [entry for entry in lines if not entry[1].startswith("/tmp")]

        SORTCOMPLETE = non_tmp_lines
        TMPOUTPUT = tmp_lines

        filtered_lines = []
        for entry in SORTCOMPLETE:
            if len(entry) >= 16:
                ts_str = entry[0]
                filepath = entry[16]
                filtered_lines.append((ts_str, filepath))

        TMPOPT = filtered_lines  # human readable
        RECENT = TMPOPT[:]

        # Apply filter. RECENT is unfiltered all data to store in db
        TMPOPT = filter_lines_from_list(TMPOPT, escaped_user)

        logf = []
        logf = RECENT
        if tmn:
            logf = RECENT  # all files
        if method != "rnt":
            if argf == "filtered" or flsrh:
                logf = TMPOPT  # filtered
                if argf == "filtered" and flsrh:
                    logf = RECENT   # all files. dont filter inverse

        # Merge/Move old searches
        if SORTCOMPLETE:

            # Copy files `recentchanges` and move old searches. if it is not porteus and some how enters bash script it just moves old files.
            if method == 'rnt':
                check_stop(stopf)

                res = porteus_linux_check()
                if res:
                    validrlt = copy_files(RECENT, RECENTNUL, TMPOPT, argone, THETIME, argtwo, USR, tempwork, archivesrh, autooutput, xzmname, cmode, fmt, script_dir)
                elif res is not None:
                    is_porteus = False
                else:
                    validrlt = copy_files(RECENT, RECENTNUL, TMPOPT, argone, THETIME, argtwo, USR, tempwork, archivesrh, autooutput, xzmname, cmode, fmt, script_dir)

            OLDSORT = []
            if flsrh:
                flnm = f'xNewerThan_{parseflnm}{argone}'
                flnmdff = f'xDiffFromLast_{parseflnm}{argone}'
            elif argf == "filtered":
                flnm = f'xFltchanges_{argone}'
                flnmdff = f'xFltDiffFromLastSearch_{argone}'
            else:
                flnm = f'xSystemchanges{argone}'
                flnmdff = f'xSystemDiffFromLastSearch{argone}'

            if method == "rnt":
                DIRSRC = "/tmp"  # 'recentchanges'

                if not is_porteus:  # if it wasnt porteus from above move old searches.
                    validrlt = clear_logs(USRDIR, DIRSRC, 'rnt', '/tmp', MODULENAME, archivesrh)
            else:
                DIRSRC = USRDIR  # 'recentchanges search'

            # is old search?
            result_output = os.path.join(DIRSRC, f'{MODULENAME}{flnm}')

            if os.path.isfile(result_output):
                with open(result_output, 'r') as f:
                    OLDSORT = f.readlines()

            # try /tmp for previous search
            if not OLDSORT and not flsrh and argf != "filtered" and method != "rnt":
                fallback_path = f'/tmp/{MODULENAME}{flnm}'
                if os.path.isfile(fallback_path):
                    with open(fallback_path, 'r') as f:
                        OLDSORT = f.readlines()

            # try `recentchanges` searches /tmp/MODULENAME_MDY*
            if not OLDSORT and not flsrh and argf != "filtered":
                hsearch(OLDSORT, MODULENAME, argone)

            target_path = None
            # output /tmp file results
            if method != "rnt":
                # Reset. move old searches
                validrlt = clear_logs(USRDIR, DIRSRC, method, '/tmp', MODULENAME, archivesrh)
                # send /tmp results to user
                if TMPOUTPUT:
                    # b_argone = '' if parseflnm.endswith('.txt') else str(argone)
                    target_filename = f"{MODULENAME}xSystemTmpfiles{parseflnm}{argone}"
                    target_path = os.path.join(USRDIR, target_filename)
                    with open(target_path, 'w') as dst:
                        for entry in TMPOUTPUT:
                            tss = entry[0].strftime(fmt)
                            fp = entry[1]
                            dst.write(f'{tss} {fp}\n')

            diff_file = os.path.join(DIRSRC, MODULENAME + flnmdff)

            # Difference file
            if OLDSORT:
                nodiff = True

                clean_oldsort = [line.strip() for line in OLDSORT]
                clean_logf_set = set(f'{entry[0].strftime(fmt)} {entry[1]}' for entry in logf)
                difference = [line for line in clean_oldsort if line not in clean_logf_set]

                if difference:
                    diffrlt = True
                    removefile(diff_file)
                    with open(diff_file, 'w') as file2:
                        for entry in difference:
                            print(entry, file=file2)
                        file2.write("\n")

                    # preprocess before db/ha. The differences before ha and then sent to processha after ha
                    processha.isdiff(SORTCOMPLETE, ABSENT, rout, diff_file, difference, flsrh, SRTTIME, fmt)

            # Send search result SORTCOMPLETE to user
            removefile(result_output)
            with open(result_output, 'w') as f:
                for entry in logf:
                    tss = entry[0].strftime(fmt)
                    fp = entry[1]
                    f.write(f'{tss} {fp}\n')

            proval = 65  # - 90%   normal for finishing pstsrg

            # file doctrine
            if POSTOP:
                endval = 85  # adjust 65% - 85%

            if scanIDX or iqt:
                dcr = True  # leave open as there is a system scan after
                if scanIDX:
                    endval = 80  # adjust 65% - 80%

            if POSTOP and scanIDX:
                endval = 75

            check_stop(stopf)
            if iqt:
                print(f"Progress: {proval}", flush=True)
            # Backend
            dbopt = pst_srg(
                dbopt, dbtarget, basedir, SORTCOMPLETE, COMPLETE, rout, scr, cerr, CACHE_S, user_setting, logging_values,
                dcr=dcr, iqt=iqt, strt=proval, endp=endval
            )
            # dbopt return from pst_srg is either path, encr_error, new_profile or None
            proval = endval
            endval = 100
            if not iqt and scanIDX:
                dcr = False  # for command line reset to default False. This means to remove db after system scan. qt remains open for gui
            if not dbopt:
                print("There is a problem in pst_srg no return value. likely database wasnt created, path to database did not exist or permission issue")
                return 1
            # if dbopt and dbopt != "encr_error":
            #     if os.path.isfile(dbtarget):
            #         change_perm(dbtarget, uid, gid, 0o644)

            if ANALYTICSECT:
                el = end - start
                print(f'Search took {el:.3f} seconds')
                if checksum:
                    el = cend - cstart
                    print(f'Checksum took {el:.3f} seconds')
                print()

            # Diff output to user
            csum = processha.processha(rout, ABSENT, diff_file, cerr, flsrh, argf, SRTTIME, escaped_user, suppress_browser, suppress)

            # Filter hits
            update_filter_csv(RECENT, flth, escaped_user)
            sys.stdout.flush()

            # File doctrine
            if POSTOP:
                outpath = os.path.join(USRDIR, tsv_doc)
                if not os.path.isfile(outpath):
                    if build_tsv(SORTCOMPLETE, rout, outpath):
                        change_perm(outpath, uid, gid)
                        cprint.green(f"File doctrine.tsv created {USRDIR}/{tsv_doc}")
                elif not iqt:
                    update_toml_values({'diagnostics': {'POSTOP': False}}, toml_file)  # if one was already made disable the setting

            # Terminal output process scr/cer
            if not csum and not suppress:
                if os.path.exists(scr):
                    filter_output(scr, escaped_user, 'Checksum', 'no', 'blue', 'yellow', 'scr', suppress_browser)

            if csum:
                if os.path.isfile(cerr):
                    with open(cerr, 'r') as src, open(diff_file, 'a') as dst:
                        dst.write("\ncerr\n")
                        for line in src:
                            if line.startswith("Warning File"):
                                continue
                            dst.write(line)
                    removefile(cerr)
            # end Terminal output

            if os.path.isfile(result_output) and os.path.getsize(result_output) != 0:
                syschg = True
                change_perm(result_output, uid, gid)  # 0o600

                if iqt:
                    print(f"RESULT: {result_output}")
                    # print(result_output)
                else:
                    # write search file location to open as non root
                    with open(file_out, 'w') as f1:
                        f1.write(result_output)
                    change_perm(file_out, uid, gid)

            # Cleanup
            if os.path.isfile(scr):
                removefile(scr)

            if target_path:
                change_perm(target_path, uid, gid)

            change_perm(flth, uid, gid)

        try:

            logic(syschg, nodiff, diffrlt, validrlt, THETIME, argone, argf, result_output, filename, flsrh, method)  # feedback
            # display(dspEDITOR, result_output, syschg, dspPATH)  # open text editor? handled in wrapper

        except Exception as e:
            print(f"Error in logic or display {type(e).__name__} : {e}")

        if dbopt not in ("new_profile", "encr_error") and scanIDX:  # Scan system index. If it is from the command line and a new profile was just made dont scan it. Encryption failure dont scan as there is a problem.

            cprint.green('Running POSTOP system index scan.')

            # append to old or use new default
            diff_file = diff_file if diffrlt else get_diff_file(USRDIR, MODULENAME)

            check_stop(stopf)
            rlt = scan_system(dbopt, dbtarget, basedir, USR, diff_file, CACHE_S, email, ANALYTICSECT, show_diff, compLVL, dcr=dcr, iqt=iqt, strt=proval, endp=endval)
            if not iqt:  # if commandline, turn off so doesnt scan every time
                update_toml_values({'diagnostics': {'scanIDX': False}}, toml_file)
            if rlt != 0:
                if rlt == 1:
                    print("Post op index scan failed scan_system dirwalker.py")
                    return 1
                if rlt == 7:
                    if not iqt:
                        print("No profile created. set proteusSHIELD to create profile")
                    else:
                        print("No profile created. run build IDX on pg2")
                else:
                    print(f"Unexpected error scan_system : error code {rlt}")
                    return rlt

        change_perm(diff_file, uid, gid)

        if syschg:
            if iqt:
                print("Progress: 100%", flush=True)
            return 0
        return 1


def main_entry(argv):
    parser = build_parser()
    args = parser.parse_args(argv)

    calling_args = [
        args.argone,
        args.argtwo,
        args.USR,
        args.PWD,
        args.argf,
        args.method,
        args.iqt,
        args.drive,
        args.db_output,
        args.cache_file,
        args.POST_OP,
        args.scan_idx,
        args.showDiff,
        args.dspPATH
    ]

    result = main(*calling_args)
    sys.exit(result)
