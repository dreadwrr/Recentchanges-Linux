import csv
import grp
import hashlib
import logging
import os
import pwd
import stat
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Dict
from .configfunctions import find_install
from .configfunctions import get_config
from .configfunctions import load_toml
from .fileops import calculate_checksum
from .fileops import find_link_target
from .fileops import set_stat
from .gpgcrypto import decrm
from .pyfunctions import epoch_to_date
from .pyfunctions import epoch_to_str
from .pyfunctions import user_path


# Globals
fmt = "%Y-%m-%d %H:%M:%S"


@dataclass
class ConfigData:
    appdata_local: Path
    home_dir: Path
    xdg_runtime: Path
    toml_file: Path
    json_file: Path
    log_file: Path
    uid: int
    gid: int
    config: Dict
    EXCLDIRS: list
    nogo: list
    suppress_list: list
    driveTYPE: str
    ll_level: str


# read the config for dirwalker to avoid passing too many arguments
# return configs files toml, json and log file
# if the user is root return a root log file to avoid permission errors if user switches back to user
def get_config_data(USR):
    appdata_local = find_install()  # Path(__file__).resolve().parent.parent
    toml_file, json_file, home_dir, _, xdg_runtime, USR, uid, gid = get_config(appdata_local, USR)  # xdg_config
    config = load_toml(toml_file)
    if not config:
        sys.exit(1)
    EXCLDIRS = user_path(config['search']['EXCLDIRS'], USR)
    nogo = user_path(config['shield']['nogo'], USR)
    suppress_list = user_path(config['shield']['filterout'], USR)
    driveTYPE = config['search']['driveTYPE']

    ll_level = config['logs']['logLEVEL']
    root_log_file = config['logs']['rootLOG']
    log_file = config['logs']['userLOG'] if USR != "root" else root_log_file

    log_file = home_dir / ".local" / "state" / "recentchanges" / "logs" / log_file

    return ConfigData(appdata_local, home_dir, xdg_runtime, toml_file, json_file, log_file, uid, gid, config, EXCLDIRS, nogo, suppress_list, driveTYPE, ll_level)


# Cache read
def decr_cache(CACHE_S, user=None):
    if not CACHE_S or not os.path.isfile(CACHE_S):
        return None

    csv_path = decrm(CACHE_S, user=user)
    if not csv_path:
        return None

    cfr_src = {}
    reader = csv.DictReader(StringIO(csv_path), delimiter='|')

    for row in reader:
        root = row.get('root')
        if not root:
            continue

        modified_ep_s = row.get('modified_ep') or ''
        cfr_src[root] = {
            'modified_time': str(row.get('modified_time', '')),
            'modified_ep': float(modified_ep_s) if modified_ep_s else 0.0,
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
    if value == "":
        return None
    else:
        return value


def get_dir_mtime(dirpath, locale):
    try:
        modified_ep = None
        modified_time_str = None
        st = os.lstat(dirpath)  # os.stat(file_path, follow_symlinks=False)
        if st:
            modified_ep = st.st_mtime
            modified_time_str = epoch_to_str(modified_ep)
        return modified_time_str, modified_ep, st
    except Exception as e:
        logging.debug(f"get_dir_mtime from {locale} access denied indexing directory on {dirpath}: {e}")
        return None, None, None


def get_base_folders(base_dir, EXCLDIRS_FULLPATH):
    c = 0
    base_folders = []
    if os.path.isdir(base_dir):
        c += 1
        base_folders.append(base_dir)

    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)
        if folder_path in EXCLDIRS_FULLPATH:
            continue
        if os.path.isdir(folder_path):
            c += 1
            base_folders.append(folder_path)
    return base_folders, c


def return_info(file_path, st, symlink, link_target, logs):
    target = sym = hardlink = None

    if symlink:
        sym = "y"
        target = link_target

    mode = oct(stat.S_IMODE(st.st_mode))[2:]  # '644' # stat.filemode(st.st_mode)  '-rw-r--r--'
    inode = st.st_ino

    if stat.S_ISREG(st.st_mode):
        hardlink = st.st_nlink
    try:
        owner = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        logs.append(("DEBUG", f"set_stat failed to convert uid to user name for file: {file_path}"))
        owner = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        logs.append(("DEBUG", f"set_stat failed to convert gid to group name for file: {file_path}"))
        group = str(st.st_gid)

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


# os.scandir meta DirEntry object formerly walk_meta
# for Build IDX meta - either to specifications or XzmProfile template
# take initial stat. run the checksum then stat again to confirm hash.
def scandir_meta(file_name, hash_path, st, symlink, link_target, found, sys_data, logs):

    count = 1  # init version #
    status = None
    checks = size = cam = lastmodified = None

    try:

        file_info = return_info(file_name, st, symlink, link_target, logs)

        sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size = file_info

        mtime_us = m_epoch_ns // 1_000

        if found and sym != "y":

            checks, file_dt, file_us, st, status = calculate_checksum(hash_path, m_dt, mtime_us, inode, size, logs, retry=2, max_retry=2, cacheable=False)

            if checks is not None:  # if status in ("Returned", "Retried"):
                if status == "Retried":
                    line = ', '.join(map(str, file_info))

                    mtime, mtime_us, ctime, inode, size, owner, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, owner, group, mode, sym, hardlink, logs)
                    if mtime is None:
                        logs.append(("ERROR", f"scandir_meta Retried mtime was None skipping file {file_name}"))
                        return None, status
                    m_time = mtime.strftime(fmt)
                    c_time = ctime.strftime(fmt) if ctime else None
            else:
                if status == "Nosuchfile":
                    return False, status
        # status in ("Returned", "Retried", "Changed"):

        sys_data.append((m_time, file_name, c_time, inode, a_time, checks, size, sym, owner, group, mode, cam, target, lastmodified, hardlink, count, mtime_us))
        return True, status

    except PermissionError as e:
        logs.append(("ERROR", f"scandir_meta Permission error on: {file_name} {e}"))
        return None, status
    except FileNotFoundError:
        return False, "Nosuchfile"
    except Exception as e:
        logs.append(("ERROR", f"scandir_meta Problem getting metadata skipped: {file_name} err:{type(e).__name__}: {e}"))
        return None, status


# For Scan IDX meta
# same as above but have previous checksum of file. stat and hash each profile item and check to original to find any
# changes including modifications without a new modified time or faked modified time.
def meta_sys(file_path, file_name, previous_md5, previous_sym, previous_target, previous_count, is_sym, sys_data, link_data, logs):

    status = None
    checks = size = hardlink = None
    target = None
    cas = None  # record[9]
    lastmodified = None  # record[11]
    count = previous_count + 1

    try:

        st = file_path.lstat()
        symlink = False
        if stat.S_ISLNK(st.st_mode):
            symlink = True
            target = find_link_target(file_path, logs)

        file_info = return_info(file_path, st, symlink, target, logs)

        sym, target, mode, inode, hardlink, owner, group, m_dt, m_epoch_ns, m_time, c_time, a_time, size = file_info

        mtime_us = m_epoch_ns // 1_000

        if sym != "y":

            checks, file_dt, file_us, st, status = calculate_checksum(file_path, m_dt, mtime_us, inode, size, logs, retry=2, max_retry=2, cacheable=False)
            if checks is not None:  # if status in ("Returned", "Retried"):
                if status == "Retried":
                    line = ', '.join(map(str, file_info))
                    mtime, mtime_us, ctime, inode, size, owner, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, owner, group, mode, sym, hardlink, logs)
                    if mtime is None:
                        logs.append(("ERROR", f"meta_sys Retried mtime was None skipping file {file_name}"))
                        return None, status
                    m_time = mtime.strftime(fmt)
                    c_time = ctime.strftime(fmt) if ctime else None
                # status in ("Returned", "Retried"):
                if checks != previous_md5:
                    sys_data.append((m_time, file_name, c_time, inode, a_time, checks, size, sym, owner, group, mode, cas, target, lastmodified, hardlink, count, mtime_us))

            else:  # status == "Nosuchfile" or status == "Changed"
                if status == "Changed":
                    print(f"File changed during scan skipping. file: {file_path}")
                return False, status
        else:
            if is_sym and previous_sym == "y":
                if target != previous_target:
                    link_data.append((m_time, file_name, c_time, inode, a_time, checks, size, sym, owner, group, mode, cas, target, lastmodified, hardlink, count, mtime_us))
                    link_data.append((previous_target, target))

        return True, status

    except PermissionError as e:
        logs.append(("ERROR", f"meta_sys Permission error on: {file_name} err: {e}"))
        return None, status
    except FileNotFoundError:
        return False, "Nosuchfile"
    except Exception as e:
        logs.append(("ERROR", f"meta_sys Problem getting metadata skipped: {file_name} err:{type(e).__name__}: {e}"))
        return None, status


def get_md5(file_path):
    try:
        hash_func = hashlib.md5()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception:
        return None


def resolve_profile_link(file_path, base):
    try:
        target = os.readlink(file_path)
        absolute = os.path.abspath(os.path.join(base, target))
        return absolute
    except OSError as e:
        logging.debug(f"Error checking xzm symlink target file: {file_path}: {e}")
        return None


def get_stat(path, entry, symlink, logger):
    try:
        if symlink:
            stat_info = os.lstat(path)
        else:
            stat_info = entry.stat()
        return stat_info
    except OSError as e:
        logger.debug(f"OSError cannot stat  {type(e).__name__} {e} : {path}")
        return None

# def get_md5(file_path):
#     try:
#         with open(file_path, "rb") as f:
#             return hashlib.md5(f.read()).hexdigest()
#     except FileNotFoundError:
#         return None
#     except Exception:
#         # print(f"Error reading {file_path}: {e}")
#         return None


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
            if e == ".so":
                # pull out and set flag to check for .so
                is_shared = True
                continue
            extn_set.add(e.lower())
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
