import math
import os
import traceback
from datetime import datetime
from .logs import emit_log
from . import logs
from .fileops import calculate_checksum
from .fileops import find_link_target
from .fileops import set_stat
from .fsearchfunctions import get_cached
from .fsearchfunctions import normalize_timestamp
from .pyfunctions import epoch_to_date
from .pyfunctions import escf_py


fmt = "%Y-%m-%d %H:%M:%S"


# Parallel SORTCOMPLETE search and  ctime hashing
#
# Get metadata hash of files and return array 03/02/2026
def process_line(line, checksum, file_type, search_start_dt, CACHE_F):

    label = "Sortcomplete"
    CSZE = 1048576

    log_entries = []

    cached = status = None

    lastmodified = checks = cam = target = hardlink = None

    if len(line) < 11:
        emit_log("DEBUG", f"process_line record length less than required 11. skipping: {line}", logs.WORKER_LOG_Q, log_entries)
        return None, log_entries

    mod_time, access_time, change_time, inode, symlink, hardlink, size, user, group, mode, file_path = line

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
    if not ctime and file_type == "ctime":
        return None, log_entries
    if not (file_type == "ctime" and ctime is not None and ctime > mtime) and file_type != "main":
        return None, log_entries

    try:
        inode = int(inode)
    except (TypeError, ValueError) as e:
        emit_log("ERROR", f"process_ine from find  {e} {type(e).__name__} inode: {size} line:{line}", logs.WORKER_LOG_Q, log_entries)
        return None, log_entries
    try:
        size = int(size)
    except (TypeError, ValueError) as e:
        emit_log("ERROR", f"process_line from find  {e} {type(e).__name__} size: {size} line:{line}", logs.WORKER_LOG_Q, log_entries)
        return None, log_entries

    sym = "y" if isinstance(symlink, str) and symlink.startswith("l") else None

    mtime_us = normalize_timestamp(mod_time)
    if sym != "y" and checksum:
        if size > CSZE:
            cached = get_cached(CACHE_F, size, mtime_us, escf_path)
            if cached is None:
                checks, file_dt, file_us, st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, retry=1, max_retry=1, cacheable=True, logger=logs.WORKER_LOG_Q)
                if checks is not None:
                    if status == "Retried":
                        mtime, mtime_us, ctime, inode, size, user, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, user, group, mode, sym, hardlink, logs.WORKER_LOG_Q)
                    label = "Cwrite"
                else:
                    if status == "Nosuchfile":
                        mt = mtime.replace(microsecond=0)
                        return ("Deleted", mt, mt, escf_path), log_entries
            else:
                checks = cached.get("checksum")
        else:
            checks, file_dt, file_us, st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, retry=1, max_retry=1, cacheable=False, logger=logs.WORKER_LOG_Q)
            if checks is not None:
                if status == "Retried":
                    mtime, mtime_us, ctime, inode, size, user, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, user, group, mode, sym, hardlink, logs.WORKER_LOG_Q)
            else:
                if status == "Nosuchfile":
                    mt = mtime.replace(microsecond=0)
                    return ("Deleted", mt, mt, escf_path), log_entries
    elif sym == "y":
        target = find_link_target(file_path, logs.WORKER_LOG_Q)

    atime = epoch_to_date(access_time)

    if mtime is None or (file_type == "main" and mtime < search_start_dt):
        emit_log("DEBUG", f"Warning system cache conflict: {escf_path} mtime={mtime} < cutoff={search_start_dt}", logs.WORKER_LOG_Q, log_entries)
        return None, log_entries
    if mtime < search_start_dt and label == "Cwrite":
        label = ""
    if file_type == "ctime":
        if ctime and ctime <= mtime:
            return None, log_entries
        lastmodified = mtime
        mtime = ctime
        cam = "y"

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


def process_line_worker(chunk, checksum, file_type, search_start_dt, CACHE_F, show_progress, strt, endp):

    results = []
    log_entries = []
    # delta_p = endp - strt if show_progress else 0
    dbit = False

    r = x = 0

    t_chunk = 0
    current_step = 0
    if show_progress:
        dbit = True
        t_chunk = len(chunk)

        steps = sorted({math.ceil(i * t_chunk / 10) for i in range(1, 11)})
        step_len = len(steps)

    for i, line in enumerate(chunk):
        try:

            result, log_ = process_line(line, checksum, file_type, search_start_dt, CACHE_F)

            if result is not None:
                results.append(result)
            if log_:
                log_entries.extend(log_)

        except Exception as e:
            emit_log("ERROR", f"process_line_worker - Error line {i}: {e}\n{traceback.format_exc()}", logs.WORKER_LOG_Q, log_entries)
        r = i + 1
        x += 1
        if dbit:

            if current_step < step_len and r >= steps[current_step]:

                emit_log("prog", x, logs.WORKER_LOG_Q)
                x = 0
                current_step += 1
                # prog_v = strt + round(delta_p * (steps[current_step] / t_chunk))
                # print(f"Progress: {prog_v}%", flush=True)

            # prog_i = strt + ((i + 1) / t_chunk) * delta_p
            # print(f"Progress: {prog_i:.2f}", flush=True)

    if dbit and current_step <= len(steps) - 1:
        emit_log("prog", x, logs.WORKER_LOG_Q)

    return results, log_entries, r

#
# End parallel #
#
