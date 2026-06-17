# Get metadata hash of files and return array                       05/04/2026
import os
from datetime import datetime
from .logs import emit_log
from . import logs
from .fileops import calculate_checksum
from .fileops import find_link_target
from .fileops import set_stat
from .fsearchfunctions import get_cached
from .pyfunctions import epoch_to_date
from .pyfunctions import escf_py

# Find Parallel sortcomplete search and  ctime hashing


def process_scan(line, checksum, file_type, search_start_dt, cache_f, logger=None):

    label = "Sortcomplete"
    fmt = "%Y-%m-%d %H:%M:%S"
    CSZE = 1048576

    log_entries = []

    checks = cam = lastmodified = None
    target = None
    cached = status = None
    file_st = None

    if len(line) < 11:
        emit_log("DEBUG", f"process_line record length less than required 11. skipping: {line}", logs.WORKER_LOG_Q, logger=logger)
        return None, log_entries

    mod_time, mtime_us, access_time, change_time, inode, symlink, hardlink, size, user, group, mode, file_path = line

    escf_path = escf_py(file_path)
    if not os.path.exists(file_path):
        return None, log_entries
    mtime = epoch_to_date(mod_time)
    if not os.path.isfile(file_path):
        if not mtime:
            mt = datetime.now().strftime(fmt)
        else:
            mt = mtime.replace(microsecond=0)
        return ("Nosuchfile", mt, mt, escf_path), log_entries
    ctime = epoch_to_date(change_time)
    if mtime is None:
        return None, log_entries

    sym = "y" if symlink else None

    if sym != "y" and size and checksum:

        if size > CSZE:
            cached = get_cached(cache_f, size, mtime_us, file_path)
            if cached is None:
                checks, file_dt, file_us, file_st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, retry=1, cacheable=True, log_q=logs.WORKER_LOG_Q, logger=logger)
                if checks is not None:
                    if status == "Retried":
                        checks, mtime, st, mtime_us, ctime, inode, size = set_stat(line, checks, file_dt, file_st, file_us, inode, logs.WORKER_LOG_Q, logger=logger)

                    if checks:
                        label = "Cwrite"

                else:
                    if status == "Nosuchfile":
                        mt = mtime.replace(microsecond=0)
                        return ("Deleted", mt, mt, escf_path), log_entries
            else:
                checks = cached.get("checksum")

        else:
            checks, file_dt, file_us, file_st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, retry=1, cacheable=False, log_q=logs.WORKER_LOG_Q, logger=logger)
            if checks is not None:
                if status == "Retried":
                    checks, mtime, st, mtime_us, ctime, inode, size = set_stat(line, checks, file_dt, file_st, file_us, inode, logs.WORKER_LOG_Q, logger=logger)

            else:
                if status == "Nosuchfile":
                    mt = mtime.replace(microsecond=0)
                    return ("Deleted", mt, mt, escf_path), log_entries

    elif sym == "y":
        target = find_link_target(file_path, logs.WORKER_LOG_Q,  logger=logger)

    if mtime is None:
        emit_log("DEBUG", f"process line no mtime from calculate checksum: {file_path} mtime={mtime}", logs.WORKER_LOG_Q, logger=logger)
        return None, log_entries

    if ctime and ctime > mtime:
        lastmodified = mtime
        mtime = ctime
        cam = "y"
    elif not ctime:
        emit_log("DEBUG", f"creation time was None at casmod check: {file_path} : {line}", logs.WORKER_LOG_Q, logger=logger)
    if mtime < search_start_dt:
        emit_log("DEBUG", f"Warning system cache conflict: {file_path} mtime={mtime} < cutoff={search_start_dt}", logs.WORKER_LOG_Q, logger=logger)
        return None, log_entries

    atime = epoch_to_date(access_time)

    return (
        label,
        mtime.replace(microsecond=0),
        file_path,
        ctime.strftime(fmt) if ctime is not None else None,
        inode,
        atime.strftime(fmt) if atime is not None else None,
        checks,
        size,
        sym,
        user,
        group,
        mode,
        cam,
        target,
        lastmodified.strftime(fmt) if lastmodified is not None else None,
        hardlink,
        mtime_us,
        escf_path
    ), log_entries
