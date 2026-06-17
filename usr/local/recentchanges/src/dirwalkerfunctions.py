import csv
import logging
import os
import stat
from datetime import datetime
from io import StringIO
from .dirwalkerlinux import return_info
from .fileops import calculate_checksum
from .fileops import find_dir_link_target
from .fileops import find_link_target
from .fileops import set_stat
from .fsearchfunctions import file_owner
from .gpgcrypto import decrm
from .logs import emit_log
from .pyfunctions import epoch_to_str
# 06/15/2026

# Globals
MOUNT_FOLDERS = ("mnt",  "media")  # list any other base mount folders here. these could have files or files in folders that belong to basedir and are not mount points
# for mounts in /var /home ect find those because -xdev wont. and are relavent folders
MOUNTS_INCLUDE = ("/var", "/home", "/usr")

fmt = "%Y-%m-%d %H:%M:%S"

MODE_FILENAME = 1
MODE_EXT = 2
MODE_FILENAME_EXT = 3


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


# def get_dir_mtime(dirpath, locale):
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


# see MOUNTS_INCLUDE for relavent mount folders to include in search but exclude their mount points

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
def get_relavent_mounts(exclDIRS_fullpath):
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
        if t in exclDIRS_fullpath:
            continue
        # skip if already an existing parent
        if any(t.startswith(m + "/") or t == m for m in mounts):
            continue

        mounts.append(t)
    return mounts


def check_mount_folders(folder_path, base_folders, exclDIRS_fullpath):
    """ instead of excluding mount areas such as mnt and media by default only exclude if in config exclDIRS
        this way if there are any files or files in folders that belong to device in those mount areas they are included
        in the scan profiles

        add to exclDIRS_fullpath the mount points to exclude while iterating in files_search python, find_created and
        index_system.

        """
    x = 0
    mnt_dev = os.stat(folder_path).st_dev

    for entry in os.scandir(folder_path):
        if entry.is_dir():
            if entry.path in exclDIRS_fullpath:
                continue
            dev = os.stat(entry.path).st_dev

            if dev != mnt_dev:
                x += 1
                exclDIRS_fullpath.append(entry.path)
    return x


def get_base_folders(basedir, exclDIRS_fullpath):
    """ used to get the search areas for find_created and also to display the searched folders for recentchanges search

        adds any mount points in MOUNT_FOLDERS to exclDIRS_fullpath this way any obscure files in MOUNT_FOLDERS or
        files in folders are searched but mount points are not """

    c = 0
    base_folders = []
    if os.path.isdir(basedir):
        c += 1
        base_folders.append(basedir)

    # original
    # for folder_name in os.listdir(basedir):
    #     folder_path = os.path.join(basedir, folder_name)
    #     if folder_path in exclDIRS_fullpath
    #         continue
    #     if os.path.isdir(folder_path):
    #         c += 1
    #         base_folders.append(folder_path)

    # 06/15/2026 changed to make sure all possible search locations are returned
    # example if /mnt/myfolder is part of basedir or / device that it is
    # searched and any other mount points in /mnt are excluded in
    # exclDIRS_fullpath. the same for /media or any other folder in
    # MOUNT_FOLDERS

    for entry in os.scandir(basedir):
        if entry.is_dir():

            path = entry.path
            name = entry.name

            if path in exclDIRS_fullpath:
                continue
            c += 1
            base_folders.append(path)
            if name in MOUNT_FOLDERS:
                count = check_mount_folders(path, base_folders, exclDIRS_fullpath)
                c += count

    return base_folders, c


# os.scandir find
def files_search(base_dir, search_start_dt, feedback, exclDIRS: list, exclDIRS_fullpath=None, filename=None, extension=None, mode=None, iqt=False, logger=None, strt=0, endp=100):
    if exclDIRS_fullpath is not None and not isinstance(exclDIRS_fullpath, list):
        raise TypeError("exclDIRS_fullpath is not a list")
    logger = logger if logger else logging
    if search_start_dt and not isinstance(search_start_dt, datetime):
        print("search_start_dt is not a valid date time object exitting")
        return None, 0

    # if mode is None use process scan find created files by time for recentchangessearch
    # modes
    # process search find filename, extension or filename and extension and or by time for findfile

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

    if not exclDIRS_fullpath:
        exclDIRS_fullpath = [os.path.join(base_dir, d.lstrip("/")) for d in exclDIRS]

    base_folders, root_count = get_base_folders(base_dir, exclDIRS_fullpath)
    if root_count <= 1:
        print(f"Unable to read base folders of drive {base_dir} the drive could be empty or check permissions")
        return None, 0
    exclDIRS_fullpath = set(exclDIRS_fullpath)

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

                                if full_path in exclDIRS_fullpath:
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

                                if full_path in exclDIRS_fullpath:
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

        f = 0
        prog_v = 0
        scale = current_step = 0
        steps = step_len = 0

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


def collect_files(basedir, exclDIRS_fullpath, filter_tup, is_xzm_profile, matches, extn_tup, paths_tup, is_noextension, is_shared_library, is_exec, is_sym, logger):
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

                                if path in exclDIRS_fullpath:
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


# os.scandir meta DirEntry object formerly walk_meta
# for Build IDX meta - either to specifications or XzmProfile template
# take initial stat. run the checksum then stat again to confirm hash.
def scandir_meta(file_path, hash_path, st, symlink, link_target, found, sys_data, log_q=None):

    count = 1  # init version #
    status = None
    checks = size = cam = lastmodified = None

    try:

        file_info = return_info(file_path, st, symlink, link_target, log_q)

        sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size = file_info

        mtime_us = m_epoch_ns // 1_000

        if found and sym != "y":

            checks, file_dt, file_us, file_st, status = calculate_checksum(hash_path, m_dt, mtime_us, inode, size, retry=2, max_retry=2, cacheable=False, log_q=log_q)

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
        sys_data.append((m_time, file_path, c_time, inode, a_time, checks, size, sym, owner, group, mode, cam, target, lastmodified, hardlink, count, mtime_us))
        return True, status

    except PermissionError as e:
        emit_log("ERROR", f"scandir_meta Permission error on: {file_path} {e}", log_q)
        return None, status
    except FileNotFoundError:
        return False, "Nosuchfile"
    except Exception as e:
        emit_log("ERROR", f"scandir_meta Problem getting metadata skipped: {file_path} err:{type(e).__name__}: {e}", log_q)
        raise


# For Scan IDX meta
# same as above but have previous checksum of file. stat and hash each profile item and check to original to find any
# changes including modifications without a new modified time or faked modified time.
#
# a file could change to a symlink and vice versa. which wouldnt effect anything but is info that can be output for symmetric
# differences
# previous_symlink before
# and symlink\\sym after
#
def meta_sys(file_path, previous_md5, previous_symlink, previous_target, previous_count, is_sym, sys_data, link_data, log_q=None):

    status = None
    checks = size = hardlink = None

    target = None

    cam = None  # record[9]
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

        if sym != "y":

            checks, file_dt, file_us, file_st, status = calculate_checksum(file_path, m_dt, mtime_us, inode, size, retry=2, cacheable=False, log_q=log_q)
            if checks is not None:  # if status in ("Returned", "Retried"):
                if status == "Retried":
                    checks, mtime, st, mtime_us, c_time, inode, size = set_stat(file_info, checks, file_dt, file_st, file_us, inode, log_q)
                    if mtime is None:
                        emit_log("ERROR", f"meta_sys Retried mtime was None skipping file {file_path}", log_q)
                        return None, status

                    m_time = mtime.strftime(fmt)
                    c_time = c_time.strftime(fmt) if c_time else None

                # status in ("Returned", "Retried"):
                if checks != previous_md5:
                    sys_data.append((m_time, file_path, c_time, inode, a_time, checks, size, sym, owner, domain, mode, cam, target, lastmodified, hardlink, count, mtime_us))

            else:  # status == "Nosuchfile" or status == "Changed"
                return False, status

        else:
            if is_sym and previous_symlink == "y":
                if target != previous_target:
                    link_data.append((m_time, file_path, c_time, inode, a_time, checks, size, sym, owner, domain, mode, cam, target, lastmodified, hardlink, count, mtime_us))
                    link_data.append((previous_target, target))
            elif not previous_symlink:
                emit_log("ERROR", f"meta_sys Warning file changed to symlink: {file_path}", log_q)

        return True, status

    except PermissionError as e:
        emit_log("ERROR", f"meta_sys Permission error on: {file_path} err: {e}", log_q)
        return None, status
    except FileNotFoundError:
        return False, "Nosuchfile"
    except Exception as e:
        emit_log("ERROR", f"meta_sys Problem getting metadata skipped: {file_path} err:{type(e).__name__}: {e}", log_q)
        raise


def resolve_profile_link(file_path, base, logger=None):
    log = logger if logger else logging
    try:
        target = os.readlink(file_path)
        absolute = os.path.abspath(os.path.join(base, target))
        return absolute
    except OSError as e:
        log.debug(f"Error checking xzm symlink target file: {file_path}: {e}")
        return None


def get_stat(entry, log_q=None, log_entries=None, logger=None):
    try:
        return entry.stat(follow_symlinks=False)
    except OSError as e:
        emit_log("DEBUG", f"OSError cannot stat  {type(e).__name__} {e} : {entry}", log_q, log_entries, logger)
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


# dup = any(path for path in input_one in input_two)
def check_precedence(lib_tup, bin_tup, suppress=False):
    if not suppress:
        for path in lib_tup:
            if path in bin_tup:
                print(f"Duplicate entry {path} from LIBRARY in BINARY set. LIBRARY has precedence over BINARY.")
                print("for both use PATH set with exec for proper precedence")


def get_exclDIRS_set(basedir, exclDIRS_fullpath, not_set=False):
    """ use of function of get_base_folders to get the mount points to exclude from the mount folder
         for use by index_system in dirwalker """
    discard = []
    mount_folders = (os.path.join(basedir, fld) for fld in MOUNT_FOLDERS)
    for fld in mount_folders:
        if os.path.exists(fld):
            check_mount_folders(fld, discard, exclDIRS_fullpath)
    if not_set:
        return exclDIRS_fullpath
    return set(exclDIRS_fullpath)


def output_diff(diff_file, prev_scans, all_sys, link_diff, nfs_records, dir_diff, new_diff, cmsg, are_symmetrics, showDiff, scan_start):
    """ handle output of differences to terminal and to diff file. as this is a dynamic append it tries to handle situations where the scan
         failed but still pulls previous scans and dir_diff and new_diff. If the scan succeeded you also have link_diff and nfs_records.

         this function makes it so all changes since the profile was made are inserted at the bottom of a diff file entirely. This is secure
         as the data is stored in scans and scan_entries tables. that data is pulled then the current scan is appended to the dict of lists
         prev_scans which first has the values converted into tuples.

         the end result is a history of scans along with symmetric differences at the end

         symmetric differences
         for all_sys
         link_diff symlinks whois target has changed
         nfs_records files that no longer exist from the profile
         for the profile
         dir_diff directories that had no files when the profile was created but now do
         new_diff new directories made since the profile was created

         cmsg is the hit rate and if its over 30% print to terminal and write to file """

    hdr1 = 'System index scan'
    mode = 'a' if os.path.isfile(diff_file) else 'w'
    write_type = "appended" if mode == 'a' else "written"
    hdr2 = "The following files from sys index have changes by checksum\n"
    fstr = "timestamp,filename,creationtime,inode,accesstime,checksum,filesize,symlink,user,group,mode,casmod,target,lastmodified,hardlinks,count,mtimeus"

    # current_time = datetime.now().strftime("MDY_%m-%d-%y-TIME_%H_%M_%S")  # FLBRAND

    # check if there are previous scan results so they can be removed from the bottom

    found = False

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

    # write out the scan results for the profile

    with open(diff_file, mode) as f:
        if not found and mode == 'a':
            f.write('\n')
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
            if cmsg:
                print(cmsg, file=f)

        # symmetric differences content
        # if the scan was successful:
        # symlink target change
        # show the files that no longer exist from the miss rate
        # always listed:
        # show directories that had 0 files at indexing but now have files
        # show new directories since profile was created

        if showDiff and are_symmetrics:

            # write out the symmetric differences

            # write the header in case if the prev_scans was empty
            if not prev_scans:
                print(hdr1, file=f)

            if link_diff:
                link_header = "symlink(s) with changed target"
                print(link_header, file=f)
                for i in range(0, len(link_diff), 2):
                    tup = link_diff[i]  # file record
                    if i+1 < len(link_diff):
                        second_tup = link_diff[i+1]  # old target new target
                        tup_str = " ".join(map(str, tup)) + " " + ">".join(map(str, second_tup))
                    else:
                        tup_str = " ".join(map(str, tup))
                    f.write(tup_str + "\n")
                f.write('\n')
            if nfs_records:
                header = "following profile files no longer exist"
                print(header, file=f)
                for tup in nfs_records:
                    tup_str = " ".join(map(str, tup))
                    f.write(tup_str + "\n")
                f.write('\n')
            if dir_diff:
                diff_header = "Directory had 0 files when profile created but now has files"
                print(diff_header, file=f)
                for tup in dir_diff:
                    f.write(" ".join(map(str, tup)) + "\n")
                f.write('\n')
            if new_diff:
                p = len(new_diff)
                print(f'{p} new directories since profile was created', file=f)
                for d in new_diff:
                    f.write(d + "\n")
                f.write('\n')
            # end write out the symmetric differences

    # terminal feedback
    if prev_scans:
        print()
        if cmsg:
            print(cmsg)

    if all_sys:
        print(hdr2)
        for record in all_sys:
            print(record[0], record[1])
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
