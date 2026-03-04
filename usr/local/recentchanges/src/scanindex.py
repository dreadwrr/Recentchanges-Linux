import os
import traceback
from pathlib import Path
from . import logs
from .logs import emit_log
from .dirwalkerfunctions import meta_sys


def scan_index(chunk, is_sym, i, show_progress=False, strt=0, endp=100):
    # the checksum could change on live system checksum is verified with retries
    c = r = 0
    # t_fold = 0
    dbit = False

    if show_progress:
        dbit = True
        t_fold = len(chunk)
        # scale = (endp - strt) / t_fold
        steps = sorted(set(int((i / 10) * t_fold) for i in range(1, 11)))
        step_len = len(steps)

    sys_data, link_data, nsf_records, log_entries = [], [], [], []

    x, y = 0, 0

    current_step = 0
    # incr = 10
    # delta_v = endp - strt
    # last_printed = -1

    filename = None
    for record in chunk:
        c += 1
        r += 1
        if len(record) < 16:
            emit_log("DEBUG", f"scan_index  record length less than required 16. skipping {record}", logs.WORKER_LOG_Q)
            continue
        try:
            if dbit:

                if current_step < step_len and c >= steps[current_step]:
                    emit_log("prog", r, logs.WORKER_LOG_Q)
                    r = 0
                    current_step += 1
                    # prog_i = (current_step + 1) * incr  # single core orig
                    # prog_v = round((delta_v * (prog_i / 100))) + strt
                    # print(f"Progress: {prog_v}%", flush=True)

                # p_g = strt + (c * scale)  # original
                # if p_g > last_printed:
                #     print(f"Progress: {p_g:.2f}%", flush=True)
                #     last_printed = p_g
                #     if p_g >= endp:
                #         dbit = False

            filename = str(record[1])
            if os.path.isfile(filename):
                x += 1
                checksum = record[5]
                symlink = record[7]
                target = record[12]
                count = record[15]
                if checksum:
                    file_path = Path(filename)

                    rlt, status = meta_sys(file_path, filename, checksum, symlink, target, count, is_sym, sys_data, link_data, logs.WORKER_LOG_Q)  # append meta data to sys_data
                    if not rlt:
                        if rlt is False and status == "Nosuchfile":
                            x -= 1
                            y += 1
                            nsf_records.append(record)
                            # emit_log("DEBUG", f"meta_sys File not found: {file_path}", WORKER_LOG_Q)
                        # elif rlt is None:
                        #     emit_log("DEBUG", f"status: {status}, Hash skipped {filename} . record: {record}", WORKER_LOG_Q)

            else:
                y += 1
                nsf_records.append(record)
        except (ValueError, IndexError) as e:
            emsg = f"Encountered an error chunk {i} processing record {c} of {len(chunk)}, file {filename}: {e} \n{traceback.format_exc()}"
            print(emsg)
            emit_log("ERROR", emsg, logs.WORKER_LOG_Q)

    if dbit and current_step <= len(steps) - 1:
        emit_log("prog", r, logs.WORKER_LOG_Q)
    return sys_data, link_data, nsf_records, log_entries, x, y, c
