#!/usr/bin/env python3
#   Porteus                                                                           06/16/2026
#   recentchanges. Developer buddy      recentchanges/ recentchanges search
#   Provide ease of pattern finding ie what files to block we can do this a number of ways
#   1) if a file was there (many as in more than a few) and another search lists them as deleted its either a sys file or not but unwanted nontheless
#   2) Is a system file inherent to the specifc platform
#   3) intangibles ie trashed items that may pop up infrequently and are not known about
#
#   This script is called by two methods. recentchanges and recentchanges search. The former is discussed below

#   recentchanges
#           Searches are saved in /tmp and are unfiltered.
#           old search can be grabbed from /tmp/{moduleNAME}_MDY/
#
#   recentchanges search
#           Output to Downloads
#           The search is unfiltered and a filesearch is filtered.
#           old searches can be grabbed from /tmp or /tmp/{moduleNAME}_MDY/ for convenience
#           if there is no differences it displays the old search for specified search criteria
#
#   rnt inverses the results. from symlink rnt or rnt search will filter the results. For a file search it removes the filter.
#   Also borrowed script features from various scripts on porteus forums
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
from .config import dump_toml
from .config import load_toml
from .configfunctions import check_config
from .configfunctions import find_install
from .configfunctions import get_config
from .dirwalkerfunctions import get_base_folders
from .dirwalkerfunctions import get_relavent_mounts
from .dirwalkerfunctions import MOUNT_FOLDERS
from .filterhits import update_filter_csv
from .gpgcrypto import decr_ctime
from .gpgcrypto import encr_cache
from .inotifyfunctions import init_recentchanges
from .logs import setup_logger
from .pstsrg import main as pst_srg
from .pyfunctions import cache_clear_patterns
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
from .rntchangesfunctions import find_scan
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
 pstsrg with postop 65 - 85%
 pstsrg with scanIDX 65 - 80%
 pstsrg with postop and scanIDX 65 - 75%
'''


def main(argone, argtwo, usr, pwrd, argf="bnk", method="", iqt=False, drive=None,  dtype=None, dbopt=None, cache_s=None, post_OP=False, gnupg_home=None):

    # has_tty = sys.stdin.isatty() and sys.stderr.isatty()
    # if has_tty:
    #     print("tty from qt")
    # else:
    #     print("no tty")

    signal.signal(signal.SIGINT, sighandle)
    signal.signal(signal.SIGTERM, sighandle)

    if argf not in ("bnk", "filtered", ""):
        print("please call from /usr/local/bin/recentchanges")
        sys.exit(1)
    if method != "rnt" and argone.lower() != "search":
        print("exiting not a search")
        sys.exit(1)
    # if not iqt:
    #     caller_script = Path(sys.argv[0]).resolve()
    #     launcher = os.path.basename(caller_script)
    #     if str(launcher) != "rntchanges.py":
    #         print("please call from recentchanges from /usr/local/bin")
    #         sys.exit(1)

    global is_mcore

    appdata_local = find_install()  # appdata software install aka workdir
    toml_file, json_file, home_dir, xdg_config, xdg_runtime, usr, uid, gid = get_config(appdata_local, usr, platform="Linux")

    script_dir = appdata_local / "scripts"
    inotify_creation_file = Path("/tmp/file_creation_log.txt")
    pst_data = home_dir / ".local" / "share" / "recentchanges"
    flth_frm = pst_data / "flth.csv"  # filter hits
    dbtarget_frm = pst_data / "recent.gpg"
    cache_f_frm = pst_data / "ctimecache.gpg"
    cache_s_frm = pst_data / "systimeche.gpg"
    toml_default = home_dir / ".config" / "config.bak"
    file_out = xdg_runtime / "file_output"  # holds result filename for bash
    flth = str(flth_frm)
    dbtarget = str(dbtarget_frm)
    cache_f = str(cache_f_frm)
    cache_s_str = str(cache_s_frm)

    j_settings = {}  # convenience for commandline if basedir other than C:\\ always have available.
    # if basedir is "/" doesnt not touch json for speed as its set that way most of the time **
    config = load_toml(toml_file)
    if not config:
        return 1
    feedback = config['analytics']['feedback']
    analytics = config['analytics']['analytics']
    email = config['backend']['email']
    autooutput = config['src']['autooutput']
    xzmname = config['src']['xzmname']
    cmode = config['src']['cmode']
    cachermPATTERNS = config['backend']['cachermPATTERNS']  # cache clear patterns
    cachermPATTERNS = cache_clear_patterns(usr, cachermPATTERNS)
    checksum = config['diagnostics']['checkSUM']
    cdiag = config['diagnostics']['cdiag']
    suppress_browser = config['diagnostics']['supbrw']
    supbrwLIST = config['diagnostics']['supbrwLIST']
    suppress = config['diagnostics']['suppress']
    postop = config['diagnostics']['postop']
    ps = config['shield']['proteusSHIELD']  # proteus shield
    compLVL = config['logs']['compLVL']
    moduleNAME = config['paths']['moduleNAME']
    archivesrh = config['search']['archivesrh']
    basedir = config['search']['drive']  # main drive for search
    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if usr != "root" else root_log_file
    exclDIRS = user_path(config['search']['exclDIRS'], usr)
    xRC = config['search']['xRC']
    driveTYPE_frm = config['search']['driveTYPE']
    python = config['search']['python']
    # email_name = config['backend']['name']
    # dspEDITOR = config['display']['dspEDITOR']
    # if dspEDITOR:
    #     dspEDITOR = multi_value(dspEDITOR)
    # dspPATH_frm = config['display']['dspPATH'].rstrip('/')

    escaped_user = re.escape(usr)

    # suppress browser list in config. regex
    supbrwLIST = [
        p.replace("{{user}}", escaped_user)
        for p in supbrwLIST
    ]

    # init

    if iqt:
        basedir = drive
        driveTYPE = driveTYPE_frm
        if dtype in ("HDD", "SSD"):
            driveTYPE = dtype
        else:
            print("driveTYPE for drive", basedir, " was null check json file", json_file)

        postop = post_OP
    else:

        gnupg_home = os.getenv("GNUPGHOME")
        if not gnupg_home:
            gnupg_home = home_dir / ".gnupg"

        # opening editor as root is disabled
        # dspPATH = ""
        # if dspEDITOR:  # user wants results output in text editor
        #       dspEDITOR, dspPATH = resolve_editor(dspEDITOR, dspPATH_frm, toml_file)  # verify we have a working one
        #       if not dspEDITOR and not dspPATH:
        #           return 1

        outfile = name_of(dbtarget, '.db')
        dbopt = os.path.join(pst_data, outfile)

        if ps:
            proteusPATH = config['shield']['proteusPATH']
            nogo = user_path(config['shield']['nogo'], usr)
            suppress_list = user_path(config['shield']['filterout'], usr)
            if not check_config(proteusPATH, nogo, suppress_list):
                return 1

        # if the drive type is not set auto detect it and update toml. look in json for partuuid and build cache_s
        # if for some reason the mount changed for the drive update the json, rename the cache files and rename database tables

        # summary if the drive is unkown its detected and the toml is updated
        cache_s, _, suffix, driveTYPE = setup_drive_cache(
            basedir, appdata_local, dbopt, dbtarget, json_file, toml_file, cache_s_str, driveTYPE_frm, usr, email, compLVL, j_settings=j_settings
        )
        if not cache_s or not suffix:
            return 1
        if not j_settings:
            if basedir != "/":
                print("failed to load json in setup_drive_cache")
                return 1

    # make a named tuple or dict for args and to pass less args for clarity
    user_setting = {
        'usr': usr,
        'email': email,
        'basedir': basedir,
        'driveTYPE': driveTYPE,
        'feedback': feedback,
        'analytics': analytics,
        'checksum': checksum,
        'ps': ps,
        'cdiag': cdiag,
        'compLVL': compLVL
    }

    # end init

    # VARS
    log_file = home_dir / ".local" / "state" / "recentchanges" / "logs" / log_file

    tmpoutput = []  # holding
    # Searches
    recent = []  # main results
    tout = []  # ctime results
    sortcomplete = []  # combined
    tmpopt = []  # filtered from sortcomplete

    # NSF
    complete_1, complete_2 = [], []
    complete = []  # combined

    # Diff file
    difference = []
    absent = []  # actions
    rout = []  # actions from ha

    cfr = {}  # cache dict
    recentnul = b""  # filepaths `recentchanges`

    start = end = cstart = cend = ag = 0
    validrlt = tmn = filename = search_time = search_paths = None

    diffrlt = False
    nodiff = False
    syschg = False
    flsrh = False
    filtered = False
    valid_data = False
    dcr = False  # means to remove after encrypting.

    flnm = ""
    parseflnm = ""
    diff_file = ""

    filepath = ""
    dirSRC = ""

    tsv_doc = "doctrine.tsv"

    proval = 20  # progress
    endval = 30

    fmt = "%Y-%m-%d %H:%M:%S"

    usrDIR = os.path.join(home_dir, "Downloads")
    os.makedirs(usrDIR, mode=0o755, exist_ok=True)

    F = ["find", basedir, "-xdev"]  # what is on the device

    # this will make sure files and directories that are in base of / or /mnt or some other oscure place are listed.
    # but mountpoints are not

    search_list = []

    exclDIRS_fullpath = [os.path.join(basedir, d) for d in exclDIRS]

    if not python:

        try:

            baselen = len(exclDIRS_fullpath)
            skipped = [os.path.join(basedir, m) for m in MOUNT_FOLDERS]  # using xdev so can skip mount excludes
            prune = ["("]
            for i, d in enumerate(exclDIRS_fullpath):
                if d in skipped:
                    continue
                prune += ["-path", d]
                if i < baselen - 1:
                    prune.append("-o")
            prune += [")", "-prune",  "-o"]

            mounts = get_relavent_mounts(exclDIRS_fullpath)

            # build the folders that are searched to output to user
            # folders on the device in mount folders are added to base_folders so files in those obscure
            # areas show up. mount points in mount folders are added to exclDIRS_fullpath
            base_folders, _ = get_base_folders(basedir, exclDIRS_fullpath)
            for folder in base_folders:
                # if folder == "/":
                #     continue
                search_list.append(folder)

        except Exception as e:
            print("Problem with exclDIRS setting. using default search", toml_file)
            print("Error: ", e)
            if basedir != "/":
                sys.exit(1)
            F = [
                "find",
                "/bin", "/etc", "/home", "/lib", "/lib64", "/opt", "/root", "/sbin", "/tmp", "/usr",  "/var"
            ]
            prune = []
            search_list = []
    else:
        xRC = False

    TAIL = ["-not", "-type", "d", "-printf", "%T@ %A@ %C@ %i %M %n %s %u %g %m %p\\0"]

    mmin = []
    cmin = []

    tempd = tempfile.gettempdir()

    with tempfile.TemporaryDirectory(dir=tempd) as tempwork:

        scr = os.path.join(tempwork, "scr")  # feedback
        cerr = os.path.join(tempwork, "cerr")  # priority

        # Windows key gen
        # if not iqt:
        #     is_key, err = iskey(email)
        #     if is_key is False:
        #         if not genkey(appdata_local, usr, email, email_name, dbtarget, cache_f, cache_s, flth, tempwork):
        #             print("Failed to generate a gpg key. quitting")
        #             return 1
        #     elif is_key is None:
        #         print(err)
        #         return 1

        cfr = decr_ctime(cache_f, usr, iqt)

        start = time.time()

        # make a named tuple to pass less args
        logging_values = (log_file, ll_level, appdata_local, tempwork, scr, cerr, cache_f, cache_s, json_file, gnupg_home)  # append to so pass less args in pstsrg

        setup_logger(log_file, logging_values[1], "MAIN")
        change_perm(log_file, uid, gid)

        # initialize

        # load ctime or files created or copied with preserved metadata.
        # if xRC
        tout = init_recentchanges(script_dir, home_dir, xdg_runtime, inotify_creation_file, cfr, xRC, checksum, moduleNAME, log_file)

        if argone != "search":
            thetime = argone
        else:
            thetime = argtwo

        if argf == "filtered":
            filtered = True

        # search criteria

        if thetime != "noarguser":
            p = 60
            try:
                argone = int(thetime)
                tmn = time_convert(argone, p, 2)
                search_time = tmn
                search_string = f"files {argone} seconds old or newer"

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

                filtered = True if not filtered else False

                flsrh = True
                ct = int(time.time())
                frmt = int(os.stat(filename).st_mtime)
                ag = ct - frmt
                ag = time_convert(ag, p, 2)
                search_time = ag
                search_string = f"files newer than {filename}"

        else:
            tmn = search_time = argone = 5
            search_string = "files 5 minutes old or newer"

        cprint.cyan(f'Searching for{" filtered" if filtered else ""} {search_string}\n')

        if iqt:
            print(f"Progress: {proval}", flush=True)

        # sys.stdout.flush()

        # Main search

        current_time = datetime.now()
        search_start_dt = (current_time - timedelta(minutes=search_time))
        logger = logging.getLogger("FSEARCH")

        if python:
            init = True

            recent, complete_1, end, cstart = find_scan(
                recent, complete_1, init, cfr, search_start_dt, user_setting, logging_values,
                end, cstart, exclDIRS, exclDIRS_fullpath, iqt=iqt, logger=logger,
                strt=proval, endp=endval
            )

        else:
            secondary = []
            if tout:
                mmin = ["-mmin", f"-{search_time}"]

                find_command_mmin = F + prune + mmin + TAIL
                if search_list:
                    if mounts:
                        secondary = ["find", *mounts] + mmin + TAIL

                    search_paths = 'Running command:' + ' '.join(["find"] + search_list + mmin + TAIL)

                init = True
                endval += 30

                recent, complete_1, recentnul, end, cstart = find_files(
                    find_command_mmin, secondary, search_paths, "main", recent, complete_1, recentnul, init, cfr,
                    search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, logger=logger, strt=proval,
                    endp=endval
                )

            else:
                cmin = ["-cmin", f"-{search_time}"]
                current_time = datetime.now()

                find_command_cmin = F + prune + cmin + TAIL
                if search_list:
                    if mounts:
                        secondary = ["find", *mounts] + cmin + TAIL

                    search_paths = 'Running command:' + ' '.join(["find"] + search_list + cmin + TAIL)

                init = True

                tout, complete_2, recentnul, end, cstart = find_files(
                    find_command_cmin, secondary, search_paths, "ctime", tout, complete_2, recentnul, init, cfr,
                    search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, strt=proval,
                    endp=endval, logger=logger
                )

                cmin_end = time.time()
                cmin_start = current_time.timestamp()
                cmin_offset = time_convert(cmin_end - cmin_start, 60, 2)
                check_stop(stopf)

                mmin = ["-mmin", f"-{search_time + cmin_offset:.2f}"]

                find_command_mmin = F + prune + mmin + TAIL
                if search_list:
                    if mounts:
                        secondary = ["find", *mounts] + mmin + TAIL

                    search_paths = 'Running command:' + ' '.join(["find"] + search_list + mmin + TAIL)

                proval += 10
                endval += 30
                init = False

                recent, complete_1, recentnul, end, cstart = find_files(
                    find_command_mmin, secondary, search_paths, "main", recent, complete_1, recentnul, init, cfr,
                    search_start_dt, user_setting, logging_values, end, cstart, iqt=iqt, strt=proval,
                    endp=endval, logger=logger
                )

        cend = time.time()

        sys.stdout.flush()

        # end Main search

        if recent is None or tout is None:
            return 1

        # end Main search

        check_stop(stopf)
        if cfr and (recent or tout):
            encr_cache(cfr, cache_f, email, usr, compLVL)
            # change_perm(cache_f, uid, gid)

        if not recent:
            if not tout:
                cprint.cyan("No new files found")
                if iqt:
                    print("Progress: 100.00%")
                return 0
            # for entry in tout:
            #     tss = entry[0].strftime(fmt)
            #     fp = entry[1]
            #     print(f'{tss} {fp}')
            recent = tout[:]
            tout = []

        complete = complete_1 + complete_2  # nsf append to rout in pstsrg before stat insert
        proval = 60  # current progress
        endval = 90  # next

        sortcomplete = recent

        sortcomplete.sort(key=lambda x: x[0])  # get everything from the start time

        srttime = sortcomplete[0][0]  # store the start time
        merged = sortcomplete[:]

        for entry in tout:
            if not entry:
                continue
            tout_dt = entry[0]
            if tout_dt >= srttime:
                merged.append(entry)
        merged.sort(key=lambda x: x[0])

        seen = {}

        for entry in merged:
            if len(entry) < 12:
                continue

            filepath = entry[1]
            cam_flag = entry[11]

            key = filepath

            if key not in seen:
                seen[key] = entry
            else:
                existing_entry = seen[key]
                existing_cam = existing_entry[11]

                if existing_cam == "y" and cam_flag is None:
                    seen[key] = entry

        deduped = list(seen.values())

        # inclusions from this script /  sort -u
        exclude_patterns = get_runtime_exclude_list(usrDIR, moduleNAME, usr, str(file_out), flth, dbtarget, cache_f, cache_s, gnupg_home, str(log_file), str(toml_default))

        def filepath_included(filepath, exclude_patterns):
            filepath = filepath.lower()
            return not any(filepath.startswith(p) for p in exclude_patterns)

        sortcomplete = [
            entry for entry in deduped
            if filepath_included(entry[1], exclude_patterns)
        ]

        # get everything before the end time to exclude weird files created in the future. Doesnt happen on windows **
        if not flsrh:
            start_dt = srttime
            range_sec = 300 if thetime == 'noarguser' else int(thetime)
            end_dt = start_dt + timedelta(seconds=range_sec)
            lines = [entry for entry in sortcomplete if entry[0] <= end_dt]
        else:
            lines = sortcomplete

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

        sortcomplete = non_tmp_lines
        tmpoutput = tmp_lines

        filtered_lines = []
        for entry in sortcomplete:
            if len(entry) >= 17:
                ts_str = entry[0]
                filepath = entry[16]
                filtered_lines.append((ts_str, filepath))

        tmpopt = filtered_lines  # human readable
        recent = tmpopt[:]

        # Apply filter. recent is unfiltered all data to store in db
        tmpopt = filter_lines_from_list(tmpopt, escaped_user)

        logf = recent
        if filtered:
            logf = tmpopt

        # Merge/Move old searches
        if sortcomplete:

            # Copy files `recentchanges` and move old searches. if it is not porteus and some how enters bash script it just moves old files.
            if method == 'rnt':
                check_stop(stopf)

                if not iqt and argtwo == "SRC":
                    res = porteus_linux_check(any_version=True)
                    if res:
                        validrlt = copy_files(recent, recentnul, tmpopt, argone, thetime, argtwo, usr, tempwork, archivesrh, autooutput, xzmname, cmode, fmt, script_dir)
                    elif res is not None:
                        print("SRC skipped.")
                        # is_porteus = False
                        # else:
                        # validrlt = copy_files(recent, recentnul, tmpopt, argone, thetime, argtwo, usr, tempwork, archivesrh, autooutput, xzmname, cmode, fmt, appdata_local)

            oldsort = []
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
                dirSRC = "/tmp"  # recentchanges
            else:
                dirSRC = usrDIR  # recentchanges search

            # is old search?
            result_output = os.path.join(dirSRC, f'{moduleNAME}{flnm}')

            if os.path.isfile(result_output):
                with open(result_output, 'r') as f:
                    oldsort = f.readlines()

            if not flsrh and argf != "filtered":
                # try /tmp for previous search
                if method != "rnt" and not oldsort:
                    fallback_path = f'/tmp/{moduleNAME}{flnm}'
                    if os.path.isfile(fallback_path):
                        with open(fallback_path, 'r') as f:
                            oldsort = f.readlines()

                # try searches /tmp/moduleNAME_MDY*
                if not oldsort:
                    hsearch(oldsort, '/tmp', moduleNAME, flnm)

            # Reset. move old searches
            validrlt = clear_logs(dirSRC, method, '/tmp', moduleNAME, archivesrh)

            target_path = None
            # output /tmp file results
            if method != "rnt":
                # send Temp results to user
                if tmpoutput:
                    # b_argone = '' if parseflnm.endswith('.txt') else str(argone)
                    target_filename = f"{moduleNAME}xSystemTmpfiles{parseflnm}{argone}"

                    target_path = os.path.join(usrDIR, target_filename)
                    with open(target_path, 'w') as dst:
                        for entry in tmpoutput:
                            tss = entry[0].strftime(fmt)
                            fp = entry[1]
                            dst.write(f'{tss} {fp}\n')

            diff_file = os.path.join(dirSRC, moduleNAME + flnmdff)

            # Difference file
            if oldsort:
                nodiff = True

                clean_oldsort = [line.strip() for line in oldsort]
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
                    processha.isdiff(sortcomplete, absent, rout, diff_file, difference, flsrh, srttime, fmt)

            # Send search result sortcomplete to user
            removefile(result_output)
            with open(result_output, 'w') as f:
                for entry in logf:
                    tss = entry[0].strftime(fmt)
                    fp = entry[1]
                    f.write(f'{tss} {fp}\n')

            proval = 65  # - 90%   normal for finishing pstsrg

            # file doctrine
            if postop:
                endval = 85  # adjust 65% - 85%

            # if scanIDX:
            #     endval = 80  # adjust 65% - 80%

            # if postop and scanIDX:
            #     endval = 75

            check_stop(stopf)
            if iqt:
                dcr = True  # leave open as its called from the app
                print(f"Progress: {proval}", flush=True)
            # elif not scanIDX:
            #     dcr = False
            else:
                dcr = False

            # pass some analytics into pstsrg
            el = end - start
            el2 = cend - cstart
            total_time = el + el2
            total_files = len(sortcomplete)
            # Backend

            dbopt, data = pst_srg(
                dbopt, dbtarget, sortcomplete, complete, rout, cachermPATTERNS, user_setting, logging_values,
                total_time, total_files, dcr=dcr, iqt=iqt, strt=proval, endp=endval
            )
            # dbopt return from pst_srg is either path, encr_error, new_profile or None
            proval = endval
            endval = 100

            if not dbopt:
                print("There is a problem in pst_srg no return value. likely database wasnt created, path to database did not exist or permission issue")
                return 1
            # if dbopt and dbopt != "encr_error":
            #     if os.path.isfile(dbtarget):
            #         change_perm(dbtarget, uid, gid, 0o644)

            csum, unique_files, lifetime_throughput, ha_total_time, logger_total_time = data

            # for benchmarking pstsrg returned the time for multiprocessing ect. This can help verify if any changes or new designs improve performance and also
            # where the bulk of the work is. This data isnt stored so it is essentially free and adds no complexity.
            if analytics:
                if dbopt not in ("new_database", "encr_error", "db_error"):  # "new_profile" would be not to scan index as it was just made
                    valid_data = True
                    if ha_total_time:
                        print("Hanly total time:", format(ha_total_time, ".3f"), "seconds", "logger:", format(logger_total_time, ".4f"), "seconds")

            # Diff output to user
            processha.processha(rout, absent, diff_file, cerr, flsrh, argf, srttime, escaped_user, supbrwLIST, suppress_browser, suppress)

            # Filter hits
            update_filter_csv(recent, flth, escaped_user)
            sys.stdout.flush()

            # File doctrine
            if postop:
                outpath = os.path.join(usrDIR, tsv_doc)
                if not os.path.isfile(outpath):

                    # run_doctrine(appdata_local, usrDIR, sortcomplete, tmpopt, logf, rout, toml_file, escaped_user, method, fmt)
                    # cprint.green(f"File doctrine.tsv created {usrDIR}/{tsv_doc}")
                    # change_perm(outpath, uid, gid)

                    if build_tsv(sortcomplete, tmpopt, logf, rout, escaped_user, outpath, method, fmt):
                        change_perm(outpath, uid, gid)
                        cprint.green(f"File doctrine.tsv created {usrDIR}/{tsv_doc}")
                elif not iqt:
                    # update_toml_values({'diagnostics': {'postop': False}}, toml_file)  # if one was already made disable the setting
                    config['diagnostics']['postop'] = False
                    dump_toml(None, config, toml_file)

            # Terminal output process scr/cer
            if not csum and not suppress:
                if os.path.exists(scr):
                    filter_output(scr, escaped_user, 'Checksum', 'no', 'blue', 'yellow', 'scr', supbrwLIST, suppress_browser, suppress)

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

            logic(syschg, nodiff, diffrlt, validrlt, thetime, argone, argf, result_output, filename, flsrh, method)  # feedback
            # display(dspEDITOR, result_output, dspPATH, syschg)  # open text editor? handled in wrapper

        except Exception as e:
            print(f"Error in logic or display {type(e).__name__} : {e}")

        if analytics:

            print(f'Search took {el:.3f} seconds')
            if checksum:
                print(f'Checksum took {el2:.3f} seconds')
            print()

            print("Files scanned:", total_files)
            throughput = total_files / total_time
            if total_files != 0:

                output = "Perceived throughput: {:.3f} files per second".format(throughput)
                if valid_data:
                    output += f" Lifetime throughput: {lifetime_throughput:.3f}" if lifetime_throughput else ""
                print(output)
                if unique_files:
                    print()
                    print("Total unique files in logs:", unique_files)
        print()

        # removed below to handle scan idx after this script in qt as scanning a profile index from commandline is unecessary hence
        # why its removed from the script. Makes it less complex and its a feature that wouldnt be used because there is a gui
        #

        # Scan system index. If it is from the command line and a new profile was just made dont scan it.
        # Encryption failure dont scan as there is a problem.
        # if dbopt not in ("new_profile", "encr_error", "db_error") and scanIDX:  # Scan system index. If it is from the command line and a new profile was just made dont scan it. Encryption failure dont scan as there is a problem.

        #     cprint.green('Running postop system index scan.')

        #     # append to old or use new default
        #     diff_file = diff_file if diffrlt else get_diff_file(usrDIR, moduleNAME)

        #     check_stop(stopf)
        #     rlt = scan_system(appdata_local, dbopt, dbtarget, basedir, usr, diff_file, cache_s, email, analytics, show_diff, compLVL, dcr=dcr, iqt=iqt, strt=proval, endp=endval)
        #     if not iqt and not autoIDX:  # if commandline, turn off so doesnt scan every time
        #         # update_toml_values({'diagnostics': {'scanIDX': False}}, toml_file)
        #         config['diagnostics']['scanIDX'] = False
        #         dump_toml(None, config, toml_file)
        #         #
        #         #
        #         #
        #     if rlt != 0:
        #         if rlt == 1:
        #             print("Post op index scan failed scan_system dirwalker.py")
        #             return 1
        #         if rlt == 7:
        #             if not iqt:
        #                 print("No profile created. set proteusSHIELD to create profile")
        #             else:
        #                 print("No profile created. run build IDX on pg2")
        #         else:
        #             print(f"Unexpected error scan_system : error code {rlt}")
        #             return rlt

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
        args.usr,
        args.pwd,
        args.argf,
        args.method,
        args.iqt,
        args.drive,
        args.dtype,
        args.db_output,
        args.cache_file,
        args.post_OP,
        args.gnupghome
    ]

    result = main(*calling_args)
    sys.exit(result)
