import csv
import logging
import os
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict
from .config import get_json_settings
from .config import load_toml
from .configfunctions import get_config
from .fileops import calculate_checksum
from .fileops import find_dir_link_target
from .fileops import find_link_target
from .fileops import get_stat
from .fileops import set_stat
from .fsearchfunctions import file_owner
from .gpgcrypto import decrm
from .logs import emit_log
from .pyfunctions import epoch_to_date
from .pyfunctions import epoch_to_str
from .pyfunctions import fmt
from .pyfunctions import user_path
# 08/21/2026

# Globals
MOUNT_FOLDERS = ("mnt",  "media")  # list any other base mount folders here. these could have files or files in folders that are not mount points
# for mounts in /var /home ect find those because -xdev wont. and are relavent folders for a search
MOUNTS_INCLUDE = ("/var", "/home", "/usr")


MODE_FILENAME = 1
MODE_EXT = 2
MODE_FILENAME_EXT = 3


@dataclass
class ConfigData:
    home_dir: Path
    xdg_runtime: Path
    toml_file: Path
    json_file: Path
    log_file: Path
    log_dir: Path
    uid: int
    gid: int
    config: Dict
    exclDIRS: list
    nogo: list
    filterout_list: list
    driveTYPE: str
    ll_level: str


def get_config_data(appdata_local, usr):
    '''
        read the config for dirwalker to avoid passing too many arguments
        return configs files toml, json and log file
        if the user is root return a root log file to avoid permission errors if user switches back to user '''
    toml_file, json_file, home_dir, _, xdg_runtime, xdg_state, usr, uid, gid = get_config(appdata_local, usr, platform="Linux")  # xdg_config, xdg_state

    config = load_toml(toml_file)
    if not config:
        sys.exit(1)
    exclDIRS = user_path(config['search']['exclDIRS'], usr)
    nogo = user_path(config['shield']['nogo'], usr)
    filterout_list = user_path(config['shield']['filterout'], usr)
    driveTYPE = config['search']['driveTYPE']
    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if usr != "root" else root_log_file

    log_dir = home_dir / ".local" / "state" / "recentchanges" / "logs"

    if xdg_state:
        log_dir = Path(xdg_state) / "recentchanges" / "logs"
    log_file = log_dir / log_file

    return ConfigData(home_dir, xdg_runtime, toml_file, json_file, log_file, log_dir, uid, gid, config, exclDIRS, nogo, filterout_list, driveTYPE, ll_level)


# Cache read
def decr_cache(cache_s, user=None):
    if not cache_s or not os.path.isfile(cache_s):
        return None

    csv_path = decrm(cache_s, user=user)
    if not csv_path:
        return None

    cfr_src = {}
    reader = csv.DictReader(StringIO(csv_path), delimiter='|')

    for row in reader:
        root = row.get('root')
        if not root:
            continue

        modified_ep_s = row.get('modified_ep') or ''
        try:
            modified_ep = float(modified_ep_s) if modified_ep_s else None
        except ValueError:
            modified_ep = None
        if modified_ep is None:
            continue

        modified_ep_s = row.get('modified_ep') or ''
        cfr_src[root] = {
            'modified_time': str(row.get('modified_time', '')),
            'modified_ep': modified_ep,
            'file_count': str(row.get('file_count', '0')),
            'idx_count': str(row.get('idx_count', '0')),
            'idx_bytes': str(row.get('idx_bytes', '0')),
            'max_depth': str(row.get('max_depth', '0')),
            'type': str(row.get('type', '')),
            'target': str(row.get('target', ''))
        }

    return cfr_src


def chunk_split(recent_sys, list_length, batch_size=25):  # , max_workers=8

    return [recent_sys[i:i+batch_size] for i in range(0, list_length, batch_size)]

    # round robin batching
    # worker_count = min(max_workers, multiprocessing.cpu_count() or 1)

    # chunks = [[] for _ in range(worker_count)]
    # worker_index = 0
    # for i in range(0, len(recent_sys), batch_size):
    #     batch = recent_sys[i:i + batch_size]
    #     chunks[worker_index].extend(batch)

    #     worker_index = (worker_index + 1) % worker_count

    # chunks = [c for c in chunks if c]
    # return chunks

    #
    # above uses numpy because pandas uses it. if not numpy
    # num_chunks = min(8, multiprocessing.cpu_count() or 1)
    # total_items = len(recent_sys)
    # chunk_size = math.ceil(total_items / num_chunks)
    # chunks = [
    #     recent_sys[i:i + chunk_size]
    #     for i in range(0, total_items, chunk_size)
    # ]


def flatten_dict(dir_data):
    # dict of dicts to flat tuples
    parsedidx = []
    for fldr, key_meta in dir_data.items():
        parsedidx.append((
            none_if_empty(key_meta.get('modified_time')),
            fldr,
            key_meta.get('file_count'),
            key_meta.get('idx_count'),
            key_meta.get('idx_bytes'),
            key_meta.get('max_depth'),
            none_if_empty(key_meta.get('type')),
            none_if_empty(key_meta.get('target'))
        ))
    return parsedidx


def none_if_empty(value):
    return value or None


# see MOUNTS_INCLUDE for relavent mount folders like /var /usr /home


def get_relavant_mounts(excluded_paths):
    """ used by find -xdev to cover common mounts like /home or /var/lib/containers that it would miss """

    # first attempt but mounts in aufs doesnt parse correctly
    # import subprocess
    # result = subprocess.run(
    #     ["findmnt", "-rn", "-o", "TARGET"],
    #     capture_output=True,
    #     text=True,
    #     check=True,
    # )
    # sort so any base comes firsts
    # targets = sorted(result.stdout.splitlines(), key=len)

    # alternative to final method used with subprocess
    # result = subprocess.run(
    #     ['awk', '{print $4}', '/proc/self/mountinfo'],
    #     capture_output=True, text=True
    # )
    # targets = [
    #     line for line in result.stdout.splitlines()
    #     if line.startswith(prefixes)
    # ]
    # sort so any base comes firsts
    # targets.sort(key=len)

    # final method

    # find any mounts we are interested in
    targets = []
    with open('/proc/self/mountinfo') as f:

        # sort so any base comes firsts
        targets = sorted(
            (line.split()[3] for line in f
                if line.split()[3].startswith(MOUNTS_INCLUDE)),
            key=len
        )

    # list any tmpfs mounted on /
    # for d in /*; do
    #     printf '%-15s ' "$d"
    #     df -T "$d" | awk 'NR==2 {print $2, $7}'
    # done
    # and include any other in mounts

    mounts = []
    # find any mounts such as /home /var /usr from MOUNTS_INCLUDE
    for t in targets:
        if not any(t == p or t.startswith(p + "/") for p in MOUNTS_INCLUDE):
            continue
        if t in excluded_paths:
            continue
        # skip if already an existing parent
        if any(t.startswith(m + "/") or t == m for m in mounts):
            continue

        mounts.append(t)
    return mounts


# see MOUNT_FOLDERS to look for mounts to exclude


def check_mount_folders(folder_path, excluded_paths):
    """ instead of excluding mount areas such as mnt and media by default only exclude if specifically in config exclDIRS
        exclude only those that dont belong to the device. this way if there are any files or files in folders they are
        included in files_search python,  find_created and index_system.

        add to excluded_paths the mount points to exclude

        """
    x = 0
    mnt_dev = os.stat(folder_path).st_dev

    for entry in os.scandir(folder_path):
        if entry.is_dir():
            if entry.path in excluded_paths:
                continue
            dev = os.stat(entry.path).st_dev

            if dev != mnt_dev:
                x += 1
                excluded_paths.append(entry.path)
    return x


def get_mount_excludes(basedir, excluded_paths, as_set=False) -> list | set:
    """ get the mount points to exclude from MOUNT_FOLDERS
         for use by index_system in dirwalker """

    mount_folders = (os.path.join(basedir, fld) for fld in MOUNT_FOLDERS)
    for fld in mount_folders:
        if os.path.exists(fld):
            check_mount_folders(fld, excluded_paths)
    if not as_set:
        return excluded_paths
    return set(excluded_paths)


def get_base_folders(basedir, excluded_paths):
    """ used to get the search areas for find_created and also to display the searched folders for recentchanges search """

    c = 0
    base_folders = []
    if os.path.isdir(basedir):
        c += 1
        base_folders.append(basedir)

    # original
    # for folder_name in os.listdir(basedir):
    #     folder_path = os.path.join(basedir, folder_name)
    #     if folder_path in excluded_paths
    #         continue
    #     if os.path.isdir(folder_path):
    #         c += 1
    #         base_folders.append(folder_path)

    for entry in os.scandir(basedir):
        if entry.is_dir():

            path = entry.path
            # name = entry.name

            if path in excluded_paths:
                continue
            c += 1
            base_folders.append(path)

    return base_folders, c


def get_drive_type(basedir, driveTYPE, cache_s, json_file):
    from .qtdrivefunctions import parse_systimeche
    _, suffix = parse_systimeche(basedir, cache_s)
    di = get_json_settings(None, suffix, json_file) or {}
    dtype = di.get("drive_type")
    if dtype in ("HDD", "SSD"):
        return dtype
    else:
        print("Warning entry for", basedir, "is malformed in json file:", json_file, "using default", driveTYPE)
    return driveTYPE

# def get_dir_mtime(dirpath, locale):
#     """ currently not used """
#     try:
#         modified_ep = None
#         modified_time_str = None
#         st = os.lstat(dirpath)  # os.stat(file_path, follow_symlinks=False)
#         if st:
#             modified_ep = st.st_mtime
#             modified_time_str = epoch_to_str(modified_ep)
#         return modified_time_str, modified_ep, st
#     except Exception as e:
#         logging.debug(f"get_dir_mtime from {locale} access denied indexing directory on {dirpath}: {e}")
#         return None, None, None

# class ErrorHandler:
#     """ currently not used. for os.walk """
#     def __init__(self, logger=None):
#         self.logger = logger if logger else logging

#     def __call__(self, list_error):
#         if isinstance(list_error, PermissionError):
#             self.logger.debug(
#                 "os.walk Permission denied: %s, skipping...",
#                 getattr(list_error, "filename", None)
#             )
#         elif isinstance(list_error, OSError):
#             self.logger.debug("os.walk Error accessing in a root folder: %s", list_error)
#         else:
#             self.logger.debug("os.walk Unexpected error: %s", list_error)
#             raise list_error


def files_search(base_dir, search_start_dt, feedback, exclDIRS: list, excluded_paths=None, filename=None, extension=None, mode=None, iqt=False, logger=None, strt=0, endp=100):
    ''' os.scandir find

        if mode is None use process scan find created files by time for recentchangessearch
        modes
        process search find filename, extension or filename and extension and or by time for findfile '''

    if excluded_paths is not None and not isinstance(excluded_paths, list):
        raise TypeError("excluded_paths is not a list")
    logger = logger if logger else logging
    if search_start_dt and not isinstance(search_start_dt, datetime):
        print("search_start_dt is not a valid date time object exitting")
        return None, 0

    def match_name(file_lower, filename, extension):
        return file_lower == filename

    def match_extn(file_lower, filename, extension):
        return (file_lower.endswith(extension))

    def match_name_extn(file_lower, filename, extension):
        base, ext = os.path.splitext(file_lower)
        return base.startswith(filename) and ext == extension

    all_entries = []
    buffer = []

    cckSEEN = set()

    max_depth = 0
    BATCH_SIZE = 5

    filename = filename.lower() if filename else None
    extension = extension.lower() if extension else None

    cutoff = None
    if search_start_dt:
        cutoff = search_start_dt.timestamp()

    # set any modes

    matcher = None
    if mode:
        if mode == MODE_FILENAME:
            matcher = match_name
        elif mode == MODE_EXT:
            matcher = match_extn
        elif mode == MODE_FILENAME_EXT:
            matcher = match_name_extn

    if not excluded_paths:
        excluded_paths = [os.path.join(base_dir, d.lstrip("/")) for d in exclDIRS]

    base_folders, root_count = get_base_folders(base_dir, excluded_paths)
    excluded_paths = get_mount_excludes(base_dir, excluded_paths, as_set=True)  # adds to excluded_paths mount points to exclude from MOUNT_FOLDERS. return as a set.

    if root_count < 2:
        if os.path.isdir(base_dir):
            print(f"Unable to read base folders of drive {base_dir} the drive could be empty or check permissions")
            return None, 0

    f = 0
    dir_path = ""

    try:

        def process_search(root, matcher, current_depth=0, max_depth=0):

            rtype = None
            try:

                if root in cckSEEN:
                    return max_depth
                cckSEEN.add(root)

                max_depth = max(max_depth, current_depth)

                with os.scandir(root) as entries:
                    for entry in entries:

                        rtype = None
                        symlink = False

                        full_path = entry.path

                        try:

                            if entry.is_symlink():
                                symlink = True

                            if entry.is_dir():

                                if full_path in excluded_paths:
                                    continue

                                if symlink:
                                    rtype = "symlink"

                                if not rtype:
                                    if root != base_dir:
                                        max_depth = process_search(full_path, matcher, current_depth + 1, max_depth)

                            elif entry.is_file():

                                # filename = entry.name
                                file_lower = entry.name.lower()

                                if matcher(file_lower, filename, extension):
                                    if cutoff:
                                        stat_info = get_stat(entry, logger=logger)
                                        if not stat_info:
                                            continue
                                        mtime = stat_info.st_mtime
                                        c_time = stat_info.st_birthtime
                                        if (mtime < cutoff and c_time < cutoff):
                                            continue

                                    if len(buffer) >= BATCH_SIZE:
                                        print("\n".join(buffer), flush=True)
                                        buffer.clear()
                                    if feedback:
                                        buffer.append(full_path)

                                    all_entries.append(full_path)

                        except OSError as e:
                            logger.error(f"files search process_search Exception scanning {'symlink' if symlink else ''} {full_path}: {type(e).__name__} {e}", exc_info=True)

            except PermissionError:
                logger.debug(f"files search process_search Permission denied scanning: {root}")
            except OSError as e:
                logger.error(f"files search process_search Exception scanning {root}: {type(e).__name__} {e}", exc_info=True)

            return max_depth

        def process_scan(root, current_depth=0, max_depth=0):

            rtype = None
            try:

                if root in cckSEEN:
                    return max_depth
                cckSEEN.add(root)

                max_depth = max(max_depth, current_depth)

                with os.scandir(root) as entries:
                    for entry in entries:

                        rtype = None
                        symlink = False

                        full_path = entry.path

                        try:
                            if entry.is_symlink():
                                symlink = True

                            if entry.is_dir():

                                if full_path in excluded_paths:
                                    continue

                                if symlink:
                                    rtype = "symlink"

                                if not rtype:
                                    if root != base_dir:
                                        max_depth = process_scan(full_path, current_depth + 1, max_depth)

                            elif entry.is_file():

                                # filename = entry.name
                                stat_info = get_stat(entry, logger=logger)
                                if not stat_info:
                                    continue

                                mtime = stat_info.st_mtime
                                c_time = stat_info.st_ctime

                                if (mtime >= cutoff or c_time >= cutoff):
                                    if len(buffer) >= BATCH_SIZE:
                                        print("\n".join(buffer), flush=True)
                                        buffer.clear()
                                    if feedback:
                                        buffer.append(full_path)

                                    mtime_us = stat_info.st_mtime_ns // 1_000
                                    ino = stat_info.st_ino

                                    atime = stat_info.st_atime

                                    hardlink = stat_info.st_nlink
                                    size = stat_info.st_size

                                    mode = oct(stat.S_IMODE(stat_info.st_mode))[2:]
                                    owner, domain = file_owner(full_path, stat_info, logger=logger)

                                    all_entries.append((mtime, mtime_us, atime, c_time, ino, symlink, hardlink, size, owner, domain, mode, full_path))

                        except OSError as e:
                            logger.error(f"files search process_scan Exception scanning {'symlink' if symlink else ''} {full_path}: {type(e).__name__} {e}", exc_info=True)

            except PermissionError:
                logger.debug(f"files search process_scan Permission denied scanning: {root}")
            except OSError as e:
                logger.error(f"files search process_scan Exception scanning {root}: {type(e).__name__} {e}", exc_info=True)

            return max_depth

        prog_v = 0
        scale = current_step = 0

        steps = []
        step_len = 0

        if iqt:
            scale = (endp - strt) / root_count
            n = min(10, root_count)
            steps = sorted(set(int(i * root_count / n) for i in range(n + 1)))
            step_len = len(steps)

        max_depth = 0
        for dir_path in base_folders:

            f += 1
            try:

                if not mode:
                    d = process_scan(dir_path)

                else:
                    d = process_search(dir_path, matcher)

                if d > max_depth:
                    max_depth = d

                if iqt:
                    if current_step < step_len and f >= steps[current_step]:
                        prog_v = strt + (f * scale)
                        print(f"Progress: {prog_v:.2f}%", flush=True)

                        current_step += 1
            except OSError as e:
                emsg = f"Couldnt stat path {dir_path}: {type(e).__name__} err: {e}"
                print(emsg)
                logger.debug(emsg)
                continue
        if buffer:
            print("\n".join(buffer))
        if iqt and current_step <= len(steps) - 1:
            print(f"Progress: {endp:.2f}%", flush=True)

        return all_entries, max_depth

    except Exception as e:
        print(f"files_search Exception: {type(e).__name__} {e}")
        emit_log("ERROR", f"files_search file loop error {f}\\{root_count}, detected files_search line {f} of {root_count} : dir: {dir_path} {type(e).__name__} {e}", logger=logger)
        raise


def scan_files(basedir, layer, xzm_obj, is_exec, is_sym, logger):
    ''' XzmProfile shield os.scandir '''
    non_matches = {}
    matches = {}
    cckSEEN, idx_bytes = set(), set()
    try:

        def scan_dir(root, current_depth=0, r=0, j=0):

            ix = 0
            if root in cckSEEN:
                return r, j

            cckSEEN.add(root)

            with os.scandir(root) as entries:
                relative = os.path.relpath(root, layer)
                base = os.path.join(basedir, relative)
                for entry in entries:

                    path = entry.path
                    found = False
                    in_binary = False
                    target = None

                    try:

                        if entry.is_dir(follow_symlinks=False):
                            if path != basedir:
                                r, j = scan_dir(path, current_depth + 1, r, j)

                        elif entry.is_file():
                            filename = entry.name
                            symlink = entry.is_symlink()

                            if not is_sym and symlink:
                                continue
                            stat_info = get_stat(entry, logger=logger)
                            if not stat_info:
                                continue
                            j += 1

                            full_path = os.path.join(base, filename)

                            if full_path.startswith(xzm_obj.path_tup):
                                found = True
                                if is_exec:
                                    if is_shared_object(file_name=filename.lower()):
                                        if not shared_executable(path, logger):
                                            found = False
                                    elif not is_regular_executable(stat_info):
                                        found = False
                            else:
                                in_library = full_path.startswith(xzm_obj.library_tup) and is_shared_object(file_name=filename.lower())
                                in_binary = not in_library and full_path.startswith(xzm_obj.binary_tup)
                                if in_library:
                                    found = True
                                    if is_exec and not shared_executable(path, logger):
                                        found = False
                                        logger.debug(f"scan_dir skipping on is_exec flag for .so file: {path}")
                                elif in_binary:
                                    if is_regular_executable(stat_info):
                                        found = True
                            if symlink:
                                target = resolve_profile_link(path, base, logger)

                            sze = stat_info.st_size
                            dev = stat_info.st_dev
                            ino = stat_info.st_ino
                            if found:
                                r += 1
                                if ino != 0:
                                    key = (dev, ino)
                                    if key not in idx_bytes:
                                        ix += sze
                                        idx_bytes.add((dev, ino))
                                else:
                                    ix += sze
                                matches[full_path] = (full_path, path, stat_info, symlink, target, True, ino)
                            else:
                                non_matches[full_path] = (full_path, path, stat_info, symlink, target, False, ino)

                    except OSError as e:
                        logger.error(f"scan_dir Exception scanning file {path}: {type(e).__name__} {e}", exc_info=True)

            return r, j

        r, j = scan_dir(layer)

    except Exception as e:
        emsg = f"scan_files: {type(e).__name__} {e}"
        print(emsg)
        logger.error(emsg, exc_info=True)
        return None, None, 0, 0

    return non_matches, matches, r, j


def collect_files(basedir, excluded_paths, filter_tup, is_xzm_profile, matches, extn_tup, paths_tup, is_noextension, is_shared_library, is_exec, is_sym, logger):
    ''' proteusEXTN shield os.scandir '''
    all_entries = []
    log_entries = []
    dir_data = {}
    cckSEEN, idx_bytes = set(), set()
    try:

        def collect_scan(root, root_modified_dt=None, root_modified_ep=None, current_depth=0, max_depth=0, r=0, j=0):

            x = 0
            ix = 0
            idx_files = 0
            rtype = None
            try:

                if root in cckSEEN:
                    return max_depth, r, j
                cckSEEN.add(root)

                max_depth = max(max_depth, current_depth)

                with os.scandir(root) as entries:
                    for entry in entries:

                        rtype = None
                        symlink = False
                        target = None
                        shared_object = False
                        found = False
                        is_path_match = False
                        path = entry.path

                        modified_dt = None
                        modified_ep = None

                        try:

                            if entry.is_symlink():
                                symlink = True

                            if entry.is_dir():

                                if path in excluded_paths:
                                    continue
                                stat_info = get_stat(entry, logger=logger)
                                if not stat_info:
                                    continue

                                if symlink:
                                    rtype = "symlink"

                                modified_ep = stat_info.st_mtime
                                modified_dt = epoch_to_str(modified_ep)

                                if not rtype:
                                    if path != basedir:
                                        max_depth, r, j = collect_scan(path, modified_dt, modified_ep, current_depth + 1, max_depth, r, j)
                                else:
                                    target = find_link_target(path, logger=logger)

                            elif entry.is_file():

                                if not (symlink and not is_sym):
                                    filename = entry.name
                                    x += 1
                                    j += 1

                                    if is_xzm_profile:
                                        if path in matches:
                                            found = True
                                            idx_files += 1
                                            r += 1
                                            entry = matches.get(path)
                                            stat_info = entry[2] if entry else None
                                            if stat_info:
                                                sze = stat_info.st_size
                                                ix += sze
                                    else:

                                        if path.lower().startswith(filter_tup):
                                            continue

                                        elif path.startswith(paths_tup):
                                            is_path_match = True
                                            found = True
                                        else:
                                            if is_noextension:
                                                if "." not in filename or (filename.startswith(".") and filename.count(".") == 1):
                                                    found = True
                                            if not found:
                                                filename_lower = filename.lower()
                                                if filename_lower.endswith(extn_tup):
                                                    found = True
                                                elif is_shared_library:
                                                    if is_shared_object(filename_lower):
                                                        shared_object = True
                                                        found = True

                                        if found:
                                            stat_info = get_stat(entry, logger=logger)
                                            if not stat_info:
                                                continue
                                            if not is_path_match and not to_spec(path, stat_info, shared_object, is_shared_library, is_exec, logger):
                                                continue

                                            if symlink:
                                                target = find_link_target(path, logger=logger)

                                            idx_files += 1
                                            r += 1
                                            sze = stat_info.st_size
                                            dev = stat_info.st_dev
                                            ino = stat_info.st_ino
                                            if stat_info.st_nlink > 1:
                                                if ino != 0:
                                                    key = (dev, ino)
                                                    if key not in idx_bytes:
                                                        idx_bytes.add(key)
                                                        ix += sze
                                                else:
                                                    ix += sze
                                            else:
                                                ix += sze

                                            all_entries.append((path, path, stat_info, symlink, target, found, ino))
                            else:
                                if symlink:
                                    target = find_dir_link_target(path, logger=logger)
                                    if target:
                                        rtype = "symlink"
                                        stat_info = get_stat(entry, logger=logger)
                                        if not stat_info:
                                            logger.debug(f"could not stat broken dir symlink {path}")
                                            continue
                                        modified_ep = stat_info.st_mtime
                                        modified_dt = epoch_to_str(modified_ep)
                            if rtype:

                                entry_data = {
                                    'modified_time': modified_dt if modified_dt else '',
                                    'modified_ep': modified_ep,
                                    'file_count': 0,
                                    'idx_count': 0,
                                    'idx_bytes': 0,
                                    'max_depth': path.count(os.sep),
                                    'type': rtype,
                                    'target': target
                                }
                                dir_data[path] = entry_data

                        except OSError as e:
                            logger.error(f"collect_scan Exception scanning {'symlink' if symlink else ''} {path}: {type(e).__name__} {e}", exc_info=True)

                    entry_data = {
                        'modified_time': root_modified_dt if root_modified_dt else '',
                        'modified_ep': root_modified_ep,
                        'file_count': x,
                        'idx_count': idx_files,
                        'idx_bytes': ix,
                        'max_depth': root.count(os.sep),
                        'type': '',
                        'target': ''
                    }
                    dir_data[root] = entry_data

            except PermissionError:
                logger.debug(f"collect_scan Permission denied scanning: {root}")
            except OSError as e:
                logger.error(f"collect_scan Exception scanning {root}: {type(e).__name__} {e}", exc_info=True)

            return max_depth, r, j

        root_stat = os.stat(basedir)
        modified_ep = root_stat.st_mtime
        modified_dt = epoch_to_str(modified_ep)

        max_depth, r, j = collect_scan(basedir, modified_dt, modified_ep)

    except OSError as e:
        print(f"Couldnt stat unable to access drive {basedir}: {e}")
        return None, None, None, 0, 0, 0
    except Exception as e:
        emsg = f"collect_files Exception: {type(e).__name__} {e}"
        print(emsg)
        logger.error(f"{emsg}", exc_info=True)
        return None, None, None, 0, 0, 0

    return all_entries, dir_data, log_entries, max_depth, r, j


def return_info(file_path, st, symlink, link_target, log_q):

    target = sym = hardlink = None

    if symlink:
        sym = "y"
        target = link_target

    mode = oct(stat.S_IMODE(st.st_mode))[2:]  # '644' # stat.filemode(st.st_mode)  '-rw-r--r--'
    inode = st.st_ino

    # if stat.S_ISREG(st.st_mode):
    hardlink = st.st_nlink
    owner, group = file_owner(file_path, st, log_q)

    m_epoch = st.st_mtime
    m_epoch_ns = st.st_mtime_ns
    c_epoch = st.st_ctime
    a_epoch = st.st_atime
    m_dt = epoch_to_date(m_epoch)
    m_time = m_dt.strftime(fmt)
    c_time = epoch_to_str(c_epoch)
    a_time = epoch_to_str(a_epoch)
    size = st.st_size

    return sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size


def scandir_meta(file_path, hash_path, st, symlink, link_target, found, sys_data, algo="md5", log_q=None):
    '''
        os.scandir meta DirEntry object formerly walk_meta
        for Build IDX meta - either to specifications or XzmProfile template
        take initial stat. run the checksum then stat again to confirm hash. '''

    count = 1  # init version #
    status = None
    checks = entropy = mime = size = cam = lastmodified = None

    try:

        file_info = return_info(file_path, st, symlink, link_target, log_q)

        sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size = file_info

        mtime_us = m_epoch_ns // 1_000

        if found and sym != "y":

            checks, entropy, mime, file_dt, file_us, file_st, status = calculate_checksum(hash_path, m_dt, mtime_us, inode, size, algo=algo, retry=2, max_retry=2, cacheable=False, log_q=log_q)

            if checks is not None:  # if status in ("Returned", "Retried"):
                if status == "Retried":
                    checks, mtime, st, mtime_us, c_time, inode, size = set_stat(file_info, checks, file_dt, file_st, file_us, inode, log_q)
                    if mtime is None:
                        emit_log("ERROR", f"scandir_meta Retried mtime was None skipping file {file_path}", log_q)
                        return None, status

                    m_time = mtime.strftime(fmt)
                    c_time = c_time.strftime(fmt) if c_time else None

            else:
                if status == "Nosuchfile":
                    return False, status

        # status in ("Returned", "Retried", "Changed"):
        sys_data.append((m_time, file_path, c_time, inode, a_time, checks, entropy, mime, size, sym, owner, group, mode, cam, target, lastmodified, hardlink, count, mtime_us))
        return True, status

    except PermissionError as e:
        emit_log("ERROR", f"scandir_meta Permission error on: {file_path} {e}", log_q)
        return None, status
    except FileNotFoundError:
        return False, "Nosuchfile"
    except Exception as e:
        emit_log("ERROR", f"scandir_meta Problem getting metadata skipped: {file_path} err:{type(e).__name__}: {e}", log_q)
        raise


def meta_sys(file_path, previous_md5, previous_entropy, previous_mime_id, previous_symlink, previous_target, previous_count, is_sym, sys_data, link_data, ent_data, mime_data, id_to_mime, algo="md5", log_q=None):
    '''
        For Scan IDX meta
        same as above but have previous checksum of file. stat and hash each profile item and check to original to find any
        changes including modifications without a new modified time or faked modified time.

        a file could change to a symlink and vice versa. which wouldnt effect anything but is info that can be output for symmetric
        differences
        previous_symlink before
        and symlink\\sym after '''

    status = None
    checks = entropy = mime = size = hardlink = None

    target = None

    cam = None  # record[11]
    lastmodified = None  # record[11]
    count = previous_count + 1

    try:

        st = os.lstat(file_path)

        symlink = False
        if stat.S_ISLNK(st.st_mode):
            symlink = True
            target = find_link_target(file_path, log_q)

        file_info = return_info(file_path, st, symlink, target, log_q)

        sym, target, mode, inode, hardlink, owner, domain, m_dt, m_epoch_ns, m_time, c_time, a_time, size = file_info

        if previous_symlink == "y" and sym != "y":
            emit_log("ERROR", f"meta_sys Warning symlink changed to file: {file_path}", log_q)
        mtime_us = m_epoch_ns // 1_000

        if sym != "y" and size:

            checks, entropy, mime, file_dt, file_us, file_st, status = calculate_checksum(file_path, m_dt, mtime_us, inode, size, algo=algo, retry=2, cacheable=False, log_q=log_q)
            if checks is not None:  # if status in ("Returned", "Retried"):
                if status == "Retried":
                    checks, mtime, st, mtime_us, c_time, inode, size = set_stat(file_info, checks, file_dt, file_st, file_us, inode, log_q)
                    if mtime is None:
                        emit_log("ERROR", f"meta_sys Retried mtime was None skipping file {file_path}", log_q)
                        return None, status, 0

                    m_time = mtime.strftime(fmt)
                    c_time = c_time.strftime(fmt) if c_time else None

                # status in ("Returned", "Retried"):
                if checks != previous_md5:

                    all_sys = (m_time, file_path, c_time, inode, a_time, checks, entropy, mime, size, sym, owner, domain, mode, cam, target, lastmodified, hardlink, count, mtime_us)

                    if mime and previous_mime_id:
                        previous_mime = id_to_mime.get(previous_mime_id, {}).get("mime")
                        if previous_mime and mime != previous_mime:

                            mime_data.append((*all_sys, previous_mime_id))

                    if entropy is not None and previous_entropy is not None:
                        entropy_delta = abs(entropy - previous_entropy)
                        if entropy_delta >= 0.50:

                            ent_data.append((*all_sys, previous_entropy, entropy_delta))

                    if previous_symlink == "y":
                        symlink_to_file = True

                        link_data.append((*all_sys, False, symlink_to_file))  # emit_log("ERROR", f"meta_sys Warning symlink changed to file: {file_path}", log_q)
                        link_data.append((previous_target, target))

                    sys_data.append(all_sys)

            else:  # status == "Nosuchfile" or status == "Changed"
                return False, status, 0

        elif sym == "y" and is_sym:
            if previous_symlink == "y":

                # ensure valid targets
                if target and previous_target and target != previous_target:
                    all_sys = (m_time, file_path, c_time, inode, a_time, checks, entropy, mime, size, sym, owner, domain, mode, cam, target, lastmodified, hardlink, count, mtime_us)

                    link_data.append((*all_sys, False, False))
                    link_data.append((previous_target, target))
            else:
                file_to_symlink = True
                all_sys = (m_time, file_path, c_time, inode, a_time, checks, entropy, mime, size, sym, owner, domain, mode, cam, target, lastmodified, hardlink, count, mtime_us)

                link_data.append((*all_sys, file_to_symlink, False))  # emit_log("ERROR", f"meta_sys Warning file changed to symlink: {file_path}", log_q)
                link_data.append((previous_target, target))

        return True, status, size

    except PermissionError as e:
        emit_log("ERROR", f"meta_sys Permission error on: {file_path} err: {e}", log_q)
        return None, status, 0
    except FileNotFoundError:
        return False, "Nosuchfile", 0
    except Exception as e:
        emit_log("ERROR", f"meta_sys Problem getting metadata skipped: {file_path} err:{type(e).__name__}: {e}", log_q)
        raise


def check_specified_paths(basedir, configured_paths, list_name, suppress=False):
    paths = set()
    exists = []  # valid system paths
    missing = []  # inform

    for p in configured_paths:
        full = os.path.join(basedir, p)
        if os.path.isdir(full):
            paths.add(full)
            exists.append(p)
        else:
            missing.append(full)

    if not suppress and missing:
        # missing = [p[len(basedir):].lstrip(os.sep) for p in missing]  # absolute
        print(
            f"\nWarning: The following {list_name} do not exist, removed and continuing: "
            f'{", ".join(missing)}'
        )
    return tuple(paths), exists


def fill_filterout_list(action, appdata_local, basedir, driveTYPE, dbopt, dbtarget, cache_s, gnupghome, exclDIRS, nogo, filterout_list, extension, config, config_data, is_noextension, is_xzm_profile):
    """ handle inclusions. build exclusions for index_system and find_created. if drive != C:\\ get drivetype from usrprofile.json
        return filterout_list and drivetype """

    exclDIRS += nogo

    from .qtdrivefunctions import parse_systimeche
    """ filter out """
    # handle exclusions
    filterout_list = [os.path.join(basedir, d) for d in filterout_list]
    if action == 'downloads':
        if basedir == "/":

            # sensitivity adjust
            # left out for speed so dont have to glob. these are intermettitent runtime files so doesnt effect anything
            # search_archive = os.path.join(appdata_local, f"{moduleNAME}_MDY_*")  # windows
            # search_archive = os.path.join("/tmp", f"{moduleNAME}_MDY_*")  # linux
            # excluded = glob.glob(search_archive)
            # search_exclude = [
            #     str(Path(f).relative_to(Path(f).anchor))
            #     for f in excluded
            # ]
            # exclDIRS += search_exclude

            # biggest exclude is .gnupg/random_seed and any runtime files
            #
            # Note:
            #
            #

            moduleNAME = config['paths']['moduleNAME']
            home_dir = config_data.home_dir
            download_results = os.path.join(home_dir, "Downloads", moduleNAME + 'x')
            pst_data = home_dir / ".local" / "share" / "recentchanges"
            flth_frm = pst_data / "flth.csv"  # filter hits
            cache_f_frm = os.path.join(pst_data, "ctimecache.gpg")
            cache_s_frm, _ = parse_systimeche(basedir, cache_s)
            cache_s_frm = os.path.join(pst_data, cache_s_frm)
            filterout_list.append(str(flth_frm))
            filterout_list.append(download_results)
            filterout_list.append(cache_f_frm)
            filterout_list.append(cache_s_frm)

        if driveTYPE not in ("HDD", "SSD"):
            driveTYPE = config_data.driveTYPE
            json_file = config_data.json_file
            print("driveTYPE for drive", basedir, " was null check json file", json_file)

    elif action == 'build':
        if basedir == "/":

            # Linux temp folder so tmp is not included in any profile
            exclude_temp = "tmp"
            if exclude_temp not in exclDIRS:
                exclDIRS.append('tmp')

            xdg_runtime = config_data.xdg_runtime
            home_dir = config_data.home_dir
            file_out = xdg_runtime / "file_output"
            pst_data = home_dir / ".local" / "share" / "recentchanges"
            moduleNAME = config['paths']['moduleNAME']

            filterout_list.append(str(file_out))
            if not is_xzm_profile:
                download_results = os.path.join(home_dir, "Downloads", moduleNAME + "x")
                filterout_list.append(download_results)
                if '.gpg' in extension:

                    cache_f_frm = os.path.join(pst_data, "ctimecache.gpg")
                    cache_s_frm, _ = parse_systimeche(basedir, cache_s)
                    cache_s_frm = os.path.join(pst_data, cache_s_frm)

                    filterout_list.append(cache_f_frm)
                    filterout_list.append(cache_s_frm)
                    filterout_list.append(dbtarget)

                if ".csv" in extension:

                    flth_frm = pst_data / "flth.csv"
                    filterout_list.append(str(flth_frm))

                if ".db" in extension:
                    filterout_list.append(dbopt)

            if is_noextension and gnupghome:

                file_exclude = os.path.join(gnupghome, "random_seed")
                if file_exclude not in filterout_list:
                    filterout_list.append(file_exclude)
        else:
            # use drive type stored for basedir != "/"
            json_file = config_data.json_file
            driveTYPE = get_drive_type(basedir, driveTYPE, cache_s, json_file)
    else:
        RuntimeError("invalid action", action)

    return filterout_list, driveTYPE


def resolve_profile_link(file_path, base, logger=None):
    log = logger if logger else logging
    try:
        target = os.readlink(file_path)
        absolute = os.path.abspath(os.path.join(base, target))
        return absolute
    except OSError as e:
        log.debug(f"Error checking xzm symlink target file: {file_path}: {e}")
        return None


# if stat.S_IXUSR & stat_info.st_mode:
# return (st.st_mode & 0o111) != 0
# return os.access(file_path, os.X_OK)
def is_regular_executable(stat_info):
    if not stat.S_ISREG(stat_info.st_mode):
        return True
    return stat.S_IXUSR & stat_info.st_mode


def shared_executable(file_path, logger):
    try:
        with open(file_path, "rb") as f:
            if f.read(4) != b'\x7fELF':
                return False
        return True
    except OSError:
        logger.error(f"shared_executable skipping OSError file: {file_path}")
    except Exception as e:
        logger.error(f"shared_executable {file_path} {type(e).__name__} error: {e}")
    return False


def is_shared_object(file_name: str) -> bool:
    if file_name.endswith(".so"):
        return True
    if ".so." in file_name:
        remainder = file_name.split(".so.", 1)[1]
        return bool(remainder) and remainder[0].isdigit()
    return False


def to_spec(file_path, stat_info, shared_object, is_shared_library, is_exec, logger):
    if not is_exec:
        return True
    if is_shared_library:
        if shared_object:
            return shared_executable(file_path, logger)
    return is_regular_executable(stat_info)


def get_extension_tup(extension):
    extn_set = set()
    is_shared = False
    is_noextension = False
    for e in extension:
        if e:
            e_lower = e.lower()
            if e_lower == ".so":
                # pull out and set flag to check for .so
                is_shared = True
                continue
            extn_set.add(e_lower)
        else:
            is_noextension = True
    return tuple(extn_set), is_noextension, is_shared


def get_filter_tup(suppress_list):
    sup_set = set()
    for s in suppress_list:
        if s:
            sup_set.add(s.lower())
    return tuple(sup_set)


# dup = any(path for path in input_one in input_two)
def check_precedence(lib_tup, bin_tup, suppress=False):
    if not suppress:
        for path in lib_tup:
            if path in bin_tup:
                print(f"Duplicate entry {path} from LIBRARY in BINARY set. LIBRARY has precedence over BINARY.")
                print("for both use PATH set with exec for proper precedence")


def output_diff(diff_file, prev_scans, all_sys, mime_hashmap, id_to_mime, link_change, ent_change, mime_change, link_diff, ent_diff, mime_diff, nfs_records, dir_diff, new_diff, cmsg, are_symmetrics, showDiff, scan_start):
    """ handle output of differences to terminal and to diff file. as this is a dynamic append it tries to handle situations where the scan
        failed but still pulls previous scans and dir_diff and new_diff. If the scan succeeded you also have link_change ent_change
        mime_change and nfs_records.

        this function makes it so all changes since the profile was made are inserted at the bottom of a diff file entirely. This is secure
        as the data is stored in scans and scan_entries tables. that data is pulled then the current scan is appended to the dict of lists
        prev_scans which first has the values converted into tuples.

        the end result is a history of scans along with symmetric differences at the end

        for all_sys
        all_sys change by checksum
        link_change symlinks whois target has changed
        ent_change change in entropy >= 0.5
        mime_change change in file type
        nfs_records files that no longer exist from the profile

        symmetric differences for the profile
        queries of difference from when the profile was first made:
        link_diff
        ent_diff
        mime_diff
        dir_diff directories that had no files when the profile was created but now do
        new_diff new directories made since the profile was created

        cmsg is the hit rate and if its over 30% print to terminal and write to file """

    hdr1 = 'System index scan'
    mode = 'a' if os.path.isfile(diff_file) else 'w'
    write_type = "appended" if mode == 'a' else "written"
    hdr2 = "The following files from sys index have changed by checksum\n"
    hdr3 = "Symmetric differences of profile"
    fstr = "timestamp,filename,creationtime,inode,accesstime,checksum,entropy,mimeid,filesize,symlink,user,group,mode,casmod,target,lastmodified,hardlinks,count,mtimeus"

    # current_time = datetime.now().strftime("MDY_%m-%d-%y-TIME_%H_%M_%S")  # FLBRAND

    # check if there are previous scan results so they can be removed from the bottom

    found = False

    lines = []

    if mode == "a":

        with open(diff_file, 'r') as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if line.startswith("System index scan"):
                lines = lines[:i]
                found = True
                break

    if found:
        with open(diff_file, 'w') as f:
            f.writelines(lines)

    # prepapare changes
    # all_sys are changes by checksum. to have changes by entropy type target those have to be made and appended. Changed by checksum and these are changes since last or
    # instanteous changes.

    recent_changes = []

    if ent_change:
        warn = []
        reg = []
        recent_changes.append("change in entropy")
        for ent in ent_change:
            timestamp = ent[0]
            file_name = ent[1]
            entropy = ent[6]
            previous_entropy = ent[-2]
            delta = ent[-1]

            tup_str = timestamp + " " + file_name
            str_end = f"change from {previous_entropy:.2f} to {entropy:.2f}"
            if delta >= 1.00:
                warn.append(tup_str + " Warning file high entropy" + str_end)
            else:
                reg.append(tup_str + " had a delta of .5 or more " + str_end)

        for warning in warn:
            recent_changes.append(warning)
        for regular in reg:
            recent_changes.append(regular)

    if mime_change:
        recent_changes.append("changed by file type")
        for m in mime_change:
            timestamp = m[0]
            file_name = m[1]
            mime = m[7]  # mime type

            # mime_id = mime_hashmap.get(mime, {}).get("id")  # to match hanly output the mime str instead of id

            previous_mime_id = m[-1]
            previous_mime = id_to_mime.get(previous_mime_id, {}).get("mime")

            if previous_mime:
                recent_changes.append(timestamp + " " + file_name + " " + previous_mime + " → " + mime)

    if link_change:
        warn = []
        reg = []
        recent_changes.append("symlink change by target or type")

        link_change_len = len(link_change)
        for i in range(0, link_change_len, 2):
            tup = link_change[i]  # file record

            timestamp = tup[0]
            file_name = tup[1]

            file_to_symlink = tup[-2]
            symlink_to_file = tup[-1]

            tup_str = timestamp + " " + file_name + " "

            if i+1 < link_change_len:
                second_tup = link_change[i+1]  # old target new target

                if file_to_symlink:
                    tup_str = f"{timestamp} Warning file: {file_name} changed to symlink. target {second_tup[1]}"
                    warn.append((timestamp, tup_str))
                elif symlink_to_file:
                    tup_str = f"{timestamp} Warning symlink: {file_name} changed to file. former target {second_tup[0]}"
                    warn.append((timestamp, tup_str))
                else:
                    tup_str = tup_str + " → ".join(map(str, second_tup))
                    reg.append((timestamp, tup_str))
        if warn:
            # warn.sort(key=lambda x: x[0])
            for warning in warn:
                recent_changes.append(warning[1])
        if reg:
            # reg.sort(key=lambda x: x[0])
            for regular in reg:
                recent_changes.append(regular[1])
    # end prepare changes

    # write out the scan results for the profile

    with open(diff_file, mode) as f:
        if not found and mode == 'a':
            f.write('\n')

        # write out changes since last or instanteous changes

        if prev_scans:

            for scan_date in prev_scans.keys():
                records = prev_scans[scan_date]
                if records:
                    print(hdr1, file=f)
                    print(hdr2, file=f)
                    print(fstr, file=f)
                for record in records:
                    record_str = ' '.join(map(str, record))
                    f.write(record_str + '\n')
                parts = scan_date.split()
                time_stamp = f'MDY_{parts[0]}-TIME_{parts[1]}'
                f.write(time_stamp + '\n\n')

            if recent_changes:
                for changes in recent_changes:
                    f.write(changes + '\n')

            if cmsg:
                print(cmsg, file=f)

        # write out any symmetric differences or changes since first

        if showDiff and are_symmetrics:

            if not prev_scans:
                print(hdr1, file=f)  # in case if the prev_scans was empty

            print(hdr3, file=f)

            if link_diff:
                f.write('\n')
                print("symlink(s) with changed target", file=f)
                for link in link_diff:
                    f.write(" ".join(map(str, link)) + "\n")
            if ent_diff:
                f.write('\n')
                print("change in entropy", file=f)
                for ent in ent_diff:
                    f.write(" ".join(map(str, ent)) + "\n")
            if mime_diff:
                f.write('\n')
                print("chang by file type", file=f)
                for mime in mime_diff:
                    f.write(" ".join(map(str, mime)) + "\n")
            if nfs_records:
                header = "following profile files no longer exist"
                f.write('\n')
                print(header, file=f)
                for tup in nfs_records:
                    tup_str = " ".join(map(str, tup))
                    f.write(tup_str + "\n")
            if dir_diff:
                diff_header = "Directory had 0 files when profile created but now has files"
                f.write('\n')
                print(diff_header, file=f)
                for tup in dir_diff:
                    f.write(" ".join(map(str, tup)) + "\n")
            if new_diff:
                f.write('\n')
                print(f'{len(new_diff)} new directories since profile was created', file=f)
                for d in new_diff:
                    f.write(d + "\n")

            # find legend of encountered MIME types for reference

            if mime_diff:
                f.write('\n')
                print("MIME types", file=f)
                for mime_id, content in id_to_mime.items():
                    print(mime_id, content["mime"], file=f)

    # terminal feedback
    if prev_scans:
        print()
        if cmsg:
            print(cmsg)

    if all_sys:
        print(hdr2)
        for record in all_sys:
            print(record[0], record[1])

        for changes in recent_changes:
            print(changes)

        print(f"\nChanges {write_type} to difference file {diff_file}")
        if showDiff and are_symmetrics:
            print("Differences included")

    else:
        if showDiff and are_symmetrics:
            if not prev_scans and (dir_diff or new_diff):
                print("Directory differences found")
                print()
            print(f"{write_type} to difference file {diff_file}")

    if showDiff and not are_symmetrics:
        print("no symmetric differences found.")
