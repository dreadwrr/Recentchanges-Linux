# Find downloads                                                            01/26/2026
#
# Using the directory cache use the mtime of the dir to find new files. At the end
# the cache file is up to date with any new dir mtimes.
# Note: reparse points were first added during indexing. Any future reparse points we
# dont care about as if there is a problem can just reindex. Windows only has certain junctions ect.
#
# Adding to much info or trying to maintain a cache ie removing deleted files can result in desync.
import os
import traceback
from .dirwalkerfunctions import get_dir_mtime


def scan_created(chunk, basedir, EXCLDIRS_FULLPATH, filter_tup, CACHE_S, root_count, i, total_chunks, strt=0, endp=0):

    sys_data = []
    results = []
    logs = []

    cckSEEN = set()

    def process_directory(root, results, sys_data, logs):

        x = 0
        ix = 0
        entry = {"dirl": {}, "cfr_reparse": {}, "cfr_data": {}}

        if root in cckSEEN:
            return
        cckSEEN.add(root)
        prev_entry = CACHE_S.get(root)  # skip known reparse
        if prev_entry and prev_entry.get("type"):
            return

        filename = None
        previous_mtime = None
        dirl = False
        scanf = True
        # rtype = None

        modified_dt, modified_ep, st = get_dir_mtime(root, "scan_created")
        if not st:
            logs.append(("DEBUG", f"process_directory Skipped. chunk {i} of {total_chunks}. Unable to access directory: {root} no modified_ep mtime"))
            return

        if prev_entry:
            entry["dirl"][root] = "entry"
            previous_mtime = prev_entry.get('modified_ep')

            if not previous_mtime or modified_ep > previous_mtime:
                dirl = True
            elif modified_ep <= previous_mtime:
                scanf = False
        else:
            dirl = True
            # if stat.S_ISLNK(st.st_mode):  # *ignore new symlink
            # entry["cfr_reparse"][root] = {
            #     'modified_time': modified_dt if modified_dt else '',
            #     'modified_ep' : modified_ep,
            #     'file_count': 0,
            #     'idx_count': 0,
            #     'max_depth': root.count(os.sep),
            #     'type': rtype,
            #     'target': os.path.realpath(root)
            # }
            # results.append(entry)
            # logging.debug(f"folder was a reparse point: {root}")
            # return

        try:

            with os.scandir(root) as entries:
                for record in entries:

                    try:

                        if record.is_dir(follow_symlinks=False):
                            if record.path in EXCLDIRS_FULLPATH:
                                continue
                            if root != basedir:
                                process_directory(record.path, results, sys_data, logs)
                        if not scanf:
                            continue

                        if record.is_file():
                            filename = record.path

                            x += 1
                            stat_info = record.stat()
                            sze = stat_info.st_size
                            ix += sze
                            file_mtime = stat_info.st_mtime
                            if previous_mtime is None or file_mtime > previous_mtime:
                                if not filename.startswith(filter_tup):

                                    sys_data.append((filename, file_mtime))  # new file found

                    except OSError as e:
                        logs.append(("DEBUG", f"error could not stat file: {record.path} {type(e).__name__} {e}"))

                if dirl:
                    if prev_entry:
                        entry_data = prev_entry.copy()
                    else:
                        entry_data = {
                            'idx_count': 0,
                            'idx_bytes': 0,
                            'max_depth': root.count(os.sep),
                            'type': '',
                            'target': ''
                        }

                    entry_data.update({
                        'modified_time': modified_dt if modified_dt else '',
                        'modified_ep': modified_ep,
                        'idx_bytes': ix,
                        'file_count': x
                    })
                    entry["cfr_data"][root] = entry_data

                if entry["cfr_reparse"] or entry["dirl"] or entry["cfr_data"]:
                    results.append(entry)

        except (ValueError, TypeError) as e:
            logs.append(("ERROR", f"file loop error detected process_directory : dir: {root}, file: {filename} {type(e).__name__} {e} \n {traceback.format_exc()}"))
            return

        except OSError as e:
            logs.append(("ERROR",  f"chunk {i} of {total_chunks} file loop error detected process_directory : dir: {root}, file: {filename} {type(e).__name__} {e} \n{traceback.format_exc()}"))
            return

    f = 0
    scale = (endp - strt) / root_count
    for root in chunk:

        f += 1
        process_directory(root, results, sys_data, logs)

        if endp:
            prog_v = strt + (f * scale)
            print(f"Progress: {prog_v:.2f}%", flush=True)

    return sys_data, results, logs, f
