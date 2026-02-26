import logging
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from .fileops import calculate_checksum
from .fileops import find_link_target
from .fileops import set_stat
from .fsearchfunctions import get_cached
from .fsearchfunctions import normalize_timestamp
from .fsearchfunctions import upt_cache
from .logs import write_logs_to_logger
from .pyfunctions import epoch_to_date
from .pyfunctions import escf_py
# Get metadata hash of files and return array 02/16/2026

fmt = "%Y-%m-%d %H:%M:%S"

# Parallel SORTCOMPLETE search and ctime hashing


def process_line(line, checksum, file_type, search_start_dt, CACHE_F):

    label = "Sortcomplete"
    CSZE = 1048576

    logs = []

    cached = status = None

    lastmodified = checks = cam = target = hardlink = None

    if len(line) < 11:
        logs.append(("DEBUG", f"process_line record length less than required 11. skipping: {line}"))
        return None, logs

    mod_time, access_time, change_time, inode, symlink, hardlink, size, user, group, mode, file_path = line

    escf_path = escf_py(file_path)
    if not os.path.exists(file_path):
        return None, logs
    mtime = epoch_to_date(mod_time)
    if not os.path.isfile(file_path):
        if not mtime:
            mt = datetime.now().strftime(fmt)
        else:
            mt = mtime.replace(microsecond=0)
        return ("Nosuchfile", mt, mt, escf_path), None
    ctime = epoch_to_date(change_time)
    if mtime is None:
        return None, logs
    if not ctime and file_type == "ctime":
        return None, logs
    if not (file_type == "ctime" and ctime is not None and ctime > mtime) and file_type != "main":
        return None, logs

    try:
        inode = int(inode)
    except (TypeError, ValueError) as e:
        logs.append(("ERROR", f"process_ine from find  {e} {type(e).__name__} inode: {size} line:{line}"))
        return None, logs
    try:
        size = int(size)
    except (TypeError, ValueError) as e:
        logs.append(("ERROR", f"process_line from find  {e} {type(e).__name__} size: {size} line:{line}"))
        return None, logs

    sym = "y" if isinstance(symlink, str) and symlink.startswith("l") else None

    # mtime_epoch = mtime.timestamp()
    mtime_us = normalize_timestamp(mod_time)
    if sym != "y" and checksum:
        if size > CSZE:
            cached = get_cached(CACHE_F, size, mtime_us, escf_path)
            if cached is None:
                checks, file_dt, file_us, st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, logs, retry=1, max_retry=1, cacheable=True)
                if checks is not None:
                    if status == "Retried":
                        mtime, mtime_us, ctime, inode, size, user, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, user, group, mode, sym, hardlink, logs)
                    label = "Cwrite"
            else:
                checks = cached.get("checksum")
        else:
            checks, file_dt, file_us, st, status = calculate_checksum(file_path, mtime, mtime_us, inode, size, logs, retry=1, max_retry=1, cacheable=False)
            if checks is not None:
                if status == "Retried":
                    mtime, mtime_us, ctime, inode, size, user, group, mode, sym, hardlink = set_stat(line, file_dt, st, file_us, inode, user, group, mode, sym, hardlink, logs)

    elif sym == "y":
        target = find_link_target(file_path, logs)

    atime = epoch_to_date(access_time)

    if mtime is None or (file_type == "main" and mtime < search_start_dt):
        logs.append(("DEBUG", f"Warning system cache conflict: {escf_path} mtime={mtime} < cutoff={search_start_dt}"))
        return None, logs
    if mtime < search_start_dt and label == "Cwrite":
        label = ""
    if file_type == "ctime":
        if ctime and ctime <= mtime:
            return None, logs
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
    ), logs


def process_line_worker(chunk, checksum, file_type, search_start_dt, CACHE_F, show_progress, strt, endp):

    results = []
    logs = []
    delta_p = endp - strt if show_progress else 0
    dbit = False

    r = 0

    t_chunk = 0
    if show_progress:
        dbit = True
        t_chunk = len(chunk)

    for i, line in enumerate(chunk):
        try:

            result, log_entries = process_line(line, checksum, file_type, search_start_dt, CACHE_F)

            if result is not None:
                results.append(result)
            if log_entries:
                logs.extend(log_entries)

        except Exception as e:
            logs.append(("ERROR", f"process_line_worker - Error line {i}: {e}\n{traceback.format_exc()}"))
        r = i + 1
        if dbit:
            prog_i = strt + ((i + 1) / t_chunk) * delta_p
            print(f"Progress: {prog_i:.2f}", flush=True)

    return results, logs, r


def process_lines(lines, file_type, search_start_dt, process_label, user_setting, logging_values, CACHE_F, iqt=False, strt=20, endp=60):

    drive_type = user_setting['driveTYPE']
    checksum = user_setting['checksum']

    ck_results = []

    logger = logging.getLogger(process_label)
    len_lines = len(lines)

    show_progress = False
    if iqt:
        show_progress = True

    if len_lines < 80 or drive_type.lower() == "hdd":
        ck_results, logs, _ = process_line_worker(lines, checksum, file_type, search_start_dt, CACHE_F, show_progress, strt, endp)
        if logs:
            write_logs_to_logger(logs, logger)
    else:

        # min_chunk_size = 10
        # max_workers = max(1, min(8, os.cpu_count() or 4, len(lines) // min_chunk_size))
        max_workers = min(8, os.cpu_count() or 1, len_lines)
        chunk_size = max(1, (len_lines + max_workers - 1) // max_workers)
        chunks = [lines[i:i + chunk_size] for i in range(0, len_lines, chunk_size)]

        done = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_line_worker, chunk, checksum, file_type, search_start_dt, CACHE_F, False, strt, endp

                )
                for idx, chunk in enumerate(chunks)
            ]
            for future in as_completed(futures):
                try:
                    results, logs, r = future.result()
                    if results:
                        ck_results.extend(results)
                    if logs:
                        write_logs_to_logger(logs, logger)
                    done += r
                    if show_progress:
                        print(f"Progress: {strt + round((endp - strt) * done / len_lines)}%", flush=True)
                except BrokenProcessPool as e:
                    print("search failed in mc")
                    logger.error(f"fsearch error {e} \n{traceback.format_exc()}")
                    for f in futures:
                        f.cancel()
                    break
                except Exception as e:
                    emsg = f"Worker error occurred: {type(e).__name__} : {e} \n{traceback.format_exc()}"
                    print(emsg)
                    logger.error(emsg)

    results = [item for item in ck_results if item is not None]  # results = [item for sublist in ck_results if sublist is not None for item in sublist]  # flatten the list

    sortcomplete = []
    complete = []
    cwrite = []

    for res in results:
        if res is None or not res:
            continue
        if isinstance(res, tuple) and len(res) > 3:
            if res[0] == "Nosuchfile":
                complete.append((res[0], res[1], res[2], res[3]))
            elif res[0] == "Cwrite":
                cwrite.append(res[1:])
                sortcomplete.append(res[1:])
            else:
                sortcomplete.append(res[1:])
    try:

        if cwrite:

            for res in cwrite:
                time_stamp = res[0].strftime("%Y-%m-%d %H:%M:%S")
                # file_path = res[1]
                checks = res[5]
                file_size = res[6]
                # user = res[8]
                # group = res[9]
                mtime_epoch = res[15]
                epath = res[16]
                upt_cache(CACHE_F, checks, file_size, time_stamp, mtime_epoch, epath)

    except Exception as e:
        msg = f'Error updating cache: {type(e).__name__}: {e}'
        print(msg)
        logger.error(msg, exc_info=True)

    return sortcomplete, complete

#
# End parallel #
#
