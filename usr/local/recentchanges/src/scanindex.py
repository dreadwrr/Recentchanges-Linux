import os
import traceback
from pathlib import Path
from .dirwalkerfunctions import meta_sys


def scan_index(chunk, is_sym, i, show_progress=False, strt=0, endp=100):
    # the checksum could change on live system checksum is verified with retries
    c = 0
    # t_fold = 0
    dbit = False
    # if i == special_k:
    if show_progress:
        dbit = True
        t_fold = len(chunk)
        # scale = (endp - strt) / t_fold
        steps = sorted(set(int((i / 10) * t_fold) for i in range(1, 11)))
        step_len = len(steps)

    sys_data = []
    link_data = []
    nsf_records = []
    logs = []

    x, y = 0, 0

    incr = 10
    current_step = 0
    delta_v = endp - strt

    # last_printed = -1

    filename = None
    for record in chunk:
        c += 1
        if len(record) < 16:
            logs.append(("DEBUG", f"scan_index  record length less than required 16. skipping {record}"))
            continue
        try:
            if dbit:

                if current_step < step_len and c >= steps[current_step]:
                    prog_i = (current_step + 1) * incr
                    prog_v = round((delta_v * (prog_i / 100))) + strt
                    print(f"Progress: {prog_v}%", flush=True)
                    current_step += 1
            # p_g = strt + (c * scale)
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

                    rlt, status = meta_sys(file_path, filename, checksum, symlink, target, count, is_sym, sys_data, link_data, logs)  # append meta data to sys_data
                    if not rlt:
                        if rlt is False and status == "Nosuchfile":
                            x -= 1
                            y += 1
                            nsf_records.append(record)
                            # logs.append(("DEBUG", f"meta_sys File not found: {file_path}"))
                        # elif rlt is None:
                        #     logs.append(("DEBUG", f"status: {status}, Hash skipped {filename} . record: {record}"))

            else:
                y += 1
                nsf_records.append(record)
        except (ValueError, IndexError) as e:
            emsg = f"Encountered an error processing record {c} of {len(chunk)}, file {filename}: {e} \n{traceback.format_exc()}"
            print(emsg)
            logs.append(("ERROR", emsg))

    return sys_data, link_data, nsf_records, logs, x, y, c
