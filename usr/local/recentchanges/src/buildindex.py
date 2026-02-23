
# Build index - Scan a drive for specified files and hash/get meta data.
# formerly scan_f # 02/07/2026
import os
from .dirwalkerfunctions import scandir_meta


def build_index(chunk, i, show_progress=False, strt=0, endp=100):

    # rec_count = 0
    c = 0

    dbit = False
    # if i == special_k:
    if show_progress:
        dbit = True
        rec_count = len(chunk)
        #     # scale = (endp - strt) / rec_count
        steps = sorted(set(int((r / 10) * rec_count) for r in range(1, 11)))
        step_len = len(steps)

    sys_data = []
    logs = []

    incr = 10
    current_step = 0
    delta_v = endp - strt

    # last_printed = -1

    for record in chunk:
        c += 1
        if len(record) < 6:
            continue

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

        filename = record[0]
        hash_path = record[1]
        if os.path.isfile(filename):
            st = record[2]
            sym = record[3]
            target = record[4]
            found = record[5]

            rlt, status = scandir_meta(filename, hash_path, st, sym, target, found, sys_data, logs)

            if not rlt:
                if rlt is False and status == "Nosuchfile":
                    logs.append(("DEBUG", f"scandir_meta File not found: {filename}: "))
                elif rlt is None:
                    logs.append(("DEBUG", f"status: {status}, Hash skipped {filename} . record: {record}"))
        else:
            logs.append(("DEBUG", f"file not found during indexing, skipping: {filename}"))
    return sys_data, logs, c
