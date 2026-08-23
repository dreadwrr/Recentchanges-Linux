import os
import psutil
import pyudev
import random
import subprocess
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from .dirwalkerfunctions import get_config_data
from .config import dump_j_settings
from .config import get_json_settings
from .config import set_json_settings
from .config import update_dict
from .config import update_toml_values
from .dirwalkerfunctions import MOUNT_FOLDERS
from .pysql import clear_conn
from .pysql import create_conn
from .pysql import table_exists
from .qtfunctions import window_prompt
from .rntchangesfunctions import name_of
from .rntchangesfunctions import set_xdg


# DATA_DIR = "/mnt/nvme0n1p3"  # "/mnt/sda3" # "/mnt/live/memory/changes/"
MIN_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB try to gather upto
READ_SIZE = 1024 * 1024  # 1MB read instead of 4kbper random read
TOTAL_TEST_BYTES = 100 * 1024**2  # 100 MB
# THREAD_COUNTS = [1, 2, 4]


def parse_drive(basedir):
    return os.path.basename(basedir)  # get sdx from /mnt/sdx


def parse_suffix(input_text: str):
    if input_text == "cache_s":
        return input_text, None
    parts = input_text.split('_', 1)
    key = parts[1] if len(parts) > 1 else "/"
    return parts[0], key


def parse_key(basedir, cache_file=None, idx_suffix=None):
    if idx_suffix:
        return idx_suffix
    elif cache_file:
        if "_" in cache_file:
            part = name_of(cache_file)
            return part.split("_", 1)[-1]
    return device_name_of_mount(basedir)


def parse_systimeche(basedir, cache_s):
    """ systimeche table from cache_s """
    # get the key from actual cache file
    systimeche = name_of(cache_s)
    key = basedir
    if basedir != "/":
        if "_" not in systimeche:
            raise TypeError("idx_suffix requires for drive", basedir)
        _, key = systimeche.split("_", 1)
    return systimeche, key


def get_cache_s(basedir, cache_file, idx_suffix=None):
    """ initial setup """
    # / has systimeche.gpg for cache_s and systimeche for cache table
    # other systimeche_sdx.gpg for cache_s and systimeche_sdx table for cache table

    prefix = name_of(cache_file)
    cache_s = cache_file
    systimeche = prefix
    key = basedir
    if basedir != "/":
        key = parse_key(basedir, cache_file, idx_suffix)
        cache_s = prefix + f"_{key}.gpg"
        app_path = os.path.dirname(cache_file)
        cache_s = os.path.join(app_path, cache_s)
        systimeche = prefix + f"_{key}"
    return cache_s, systimeche, key


def get_idx_tables(basedir, cache_file, idx_suffix=None):
    """ pass actual cache_file or key """
    # profile sys_ a changes sys _b. profile cache table
    # get the key from actual cache file

    sys_a = ""
    cache_table = "cache_s"
    key = basedir
    if basedir != "/":
        key = parse_key(basedir, cache_file, idx_suffix)
        sys_a = f"_{key}"
        cache_table = "cache" + sys_a
    sys_b = "sys2" + sys_a
    sys_a = "sys" + sys_a
    return (sys_a, sys_b), cache_table, key


def get_new_idx_suffix(device, j_settings):
    if device == "/":
        return device
    key = device
    while j_settings.get(key) is not None:
        key = "x" + key
    return key


def get_mount_partuuid(mount_point: str) -> str | None:
    partitions = psutil.disk_partitions()
    device = None
    for p in partitions:
        if p.mountpoint == mount_point:
            device = p.device
            break
    if device is None:
        return None

    by_part_path = "/dev/disk/by-partuuid/"
    if os.path.exists(by_part_path):
        for entry in os.listdir(by_part_path):
            full_path = os.path.realpath(os.path.join(by_part_path, entry))
            if full_path == device:
                return entry
    return None


def get_mount_from_partuuid(partuuid: str) -> str | None:
    if not partuuid:
        return None
    partuuid_path = f"/dev/disk/by-partuuid/{partuuid}"
    if os.path.islink(partuuid_path):
        absolute = os.path.realpath(partuuid_path)
        # target = resolve_target(partuuid_path)  # from .fsearchfunctions import resolve_target
        return get_mountpoint(absolute)
    return None


def get_mountpoint(dev_path: str) -> str | None:
    for part in psutil.disk_partitions(all=True):
        if part.device == dev_path:
            return part.mountpoint
    return None


def device_name_of_mount(mount_point: str) -> str | None:
    if not mount_point:
        return None

    target = os.path.realpath(mount_point)

    for part in psutil.disk_partitions(all=True):
        if os.path.realpath(part.mountpoint) == target:
            return os.path.basename(part.device)

    return None

# using above have psutil so use that
# def device_name_of_mount(mount_point: str) -> str | None:
#     if not mount_point:
#         return None
#     with open("/proc/self/mounts") as f:
#         for line in f:
#             parts = line.split()
#             if parts[1] == mount_point:
#                 return os.path.basename(parts[0])
#     return None


def parent_of_device(device: str) -> str:
    dev = "/sys/class/block/" + device
    real_path = Path(dev).resolve()
    parent_name = real_path.parent.name
    return parent_name


def is_model_ssd(model: str) -> bool:
    SSD_KEYWORDS = [
        "SSD", "NVME", "NVM", "M.2", "EVO",
        "SOLID", "FLASH", "V-NAND", "3D NAND"
    ]
    if not model:
        return False
    m = model.upper()
    return any(keyword in m for keyword in SSD_KEYWORDS)


# udevadm info --name=/dev/nvme0n1p6 --attribute-walk
def current_drive_type_model_check(base_dir="/"):

    device_name = parent_device = None
    rotational = -1
    usb_drive = 0
    drive_id_model = "Unknown"
    model_type = "Unknown"
    drive_type = None
    file_sys = None
    try:
        try:
            # tmpfs, aufs - squashfs - ext4, xfs
            file_sys = subprocess.check_output(
                ["findmnt", "-n", "-o", "FSTYPE", "--target", base_dir],
                text=True
            ).strip()

            # print(f"FS for {base_dir} is: {file_sys}")
        except subprocess.CalledProcessError:
            print("Could not determine backing device for", base_dir)

        if file_sys and file_sys in ("tmpfs", "aufs", "overlay", "overlayfs", "squashfs", "zram"):
            drive_id_model = "RAM-based"
            if file_sys == "aufs":
                drive_id_model = "Union filesystem (aufs)"
            elif file_sys in ("overlay", "overlayfs"):
                drive_id_model = "Union filesystem (overlay/overlayfs)"
            return device_name, parent_device, drive_id_model, file_sys, "SSD"
        # its a drive
        else:

            device_name = None

            device = None
            for part in psutil.disk_partitions(all=True):
                if part.mountpoint == base_dir:
                    device = part.device
                    break

            if device:

                context = pyudev.Context()
                udev_dev = pyudev.Device.from_device_file(context, device)

                d = udev_dev
                while d and d.device_type != "disk":
                    d = d.parent

                if d:
                    device_name = os.path.basename(udev_dev.device_node)
                    parent_device = os.path.basename(d.device_node)

                    drive_id_model = d.properties.get("ID_MODEL", "Unknown")

                    usb_drive = any(
                        p.subsystem == "usb" and p.device_type == "usb_device"
                        for p in d.ancestors
                    )
                    # print([p.device_type for p in d.ancestors])

                    if not usb_drive:
                        if d.properties.get("ID_BUS") == "nvme" or parent_device.startswith("nvme") or is_model_ssd(drive_id_model):
                            drive_type = "SSD"

                        id_ssd = d.properties.get("ID_SSD")
                        if id_ssd == "1":
                            drive_type = "SSD"

                        try:
                            rotational = int(Path(d.sys_path, "queue/rotational").read_text().strip())
                        except (FileNotFoundError, ValueError, OSError):
                            rotational = -1

            else:
                print(f"No device found for {base_dir}")
                return None

            if usb_drive:
                model_type = "USB"
                drive_type = "SSD"
            elif not drive_type:
                if rotational == 0:
                    drive_type = "SSD"
                if rotational:
                    drive_type = "HDD"
                else:

                    # failing all else prompt the user
                    drive_type = "HDD"
                    parent = None
                    app_inst = QApplication.instance()
                    if app_inst:
                        parent = QApplication.activeWindow()
                        uinpt = window_prompt(parent, "Drive type", f"Is {base_dir} ssd", "Yes", "No")
                        if uinpt:
                            drive_type = "SSD"
                    else:
                        while True:
                            uinp = input(f"Is {base_dir} ssd (Y/N): ").strip().lower()
                            if uinp == 'y':
                                drive_type = "SSD"
                                break
                            elif uinp == 'n':
                                break
                            else:
                                print("Invalid input, please enter 'Y' or 'N'.")

        return (device_name, parent_device, drive_id_model, model_type, drive_type)

    except pyudev.DeviceNotFoundByFileError:
        # / with unknown fs backing default to HDD and unknown
        pass
    except Exception as e:
        print("An error occurred in drive model check:", type(e).__name__, e)
        return None


def setup_drive_settings(basedir, key, driveTYPE, toml_file, user_json=None, j_settings=None, idx_drive=False, lclapp_data=None):
    '''
        check by model type, pnp description or rotation. if not run read test fall back to write test. if all fails set to HDD.
        user can set in config file config.toml for basedir. user can set in usrprofile.toml for index drive.
        Newer HDD drives have RotationRate in wmi. Older or legacy drives do not. '''
    if driveTYPE:
        return driveTYPE

    # mmode = None
    # speedMB = None

    print("Determining drive type by model")  # or speed test
    drive_info = current_drive_type_model_check(basedir)
    if not drive_info:
        return None

    device_name, parent_device, drive_id_model, model_type, drive_type = drive_info
    if drive_type is None:
        print("Couldnt determine speed defaulting to HDD. change in config.toml to SSD", toml_file)
        drive_type = "HDD"

    if basedir == "/" and toml_file and not idx_drive:
        update_toml_values({'search': {'driveTYPE': drive_type}}, toml_file)  # update config.toml the basedir

    # config.toml is where basedir ie C:\\ info is stored. the 'modelTYPE' HDD or SSD
    # if its a basedir we only want to put the info in the usrprofile.toml if we have it. This is used for diagnostics to return more info about settings in ui.
    # if we were to put the wrong info in usrprofile.toml and config.toml the user would have to update two config files which is unlikely.
    #
    # if its an idx_drive we need this info regardless as usrprofile.toml is where its info is stored. 'drive_type' and 'drive_model'
    if user_json:
        # if idx_drive or model_type != "Unknown":

        if key and j_settings is not None:

            update_dict({"idx_suffix": device_name, "parent_device": parent_device, "mount_of_index": basedir, "drive_id_model": drive_id_model, "model_type": model_type, "drive_type": drive_type}, j_settings, key)
            dump_j_settings(j_settings, user_json)
        elif key:
            set_json_settings({"idx_suffix": device_name, "parent_device": parent_device, "mount_of_index": basedir, "drive_id_model": drive_id_model, "model_type": model_type, "drive_type": drive_type}, drive=key, filepath=user_json)

    print(f"model {drive_id_model}")
    print(f"model_type {model_type}")
    print(f"drive_type {drive_type}")
    return drive_type


def get_cache_files(basedir, dbopt, dbtarget, cache_s, json_file, user, email, j_settings=None, partuuid=None, iqt=False):

    suffix = basedir
    cache_file = None
    systimeche = None

    # qt gui initial load json
    # this avoids loading json unnecessarily for commandline if basedir is "/"
    # which is what it would be set to m ost of the time

    if isinstance(j_settings, dict) and not j_settings:  # iqt
        jdata = get_json_settings(None, None, json_file)
        j_settings.update(jdata)

    if basedir != "/":

        # command line
        if not iqt:
            if j_settings is None:
                j_settings = get_json_settings(None, None, json_file)  # original left for legacy
            elif not j_settings:
                jdata = get_json_settings(None, None, json_file)
                j_settings.update(jdata)

        basedir = basedir.rstrip('/')
        if not os.path.exists(basedir):
            print(f"get_cache_files setting drive: {basedir} unable to find drive")
            return None, None, None

        try:
            uuid = partuuid
            if not partuuid:
                uuid = get_mount_partuuid(basedir)
                if not uuid:
                    print(f"couldnt find uuid for {basedir} mount point")
                    return None, None, None

            drive_suffix = device_name_of_mount(basedir)  # basedir.split('/')[-1]

            x = 0
            suffix = drive_info = None

            found = False
            for key, di in j_settings.items():
                if not isinstance(di, dict):
                    continue
                drive_partuuid = di.get("drive_partuuid")
                if not found and drive_partuuid and drive_partuuid == uuid:
                    suffix = key
                    drive_info = di.copy()
                    moi = di.get("mount_of_index")
                    found = True
                elif isinstance(key, str) and key.endswith(drive_suffix):
                    x += 1

            if suffix:

                cache_file, systimeche, _ = get_cache_s(basedir, cache_s, suffix)

                # if the mountpoint changed for the uuid update json, move cache file and db tables
                #
                if moi and moi != basedir:

                    # old
                    old_cache_s = cache_file

                    # new
                    drive_suffix = ('x' * x) + drive_suffix
                    new_cache_s, new_systimeche, _ = get_cache_s(basedir, cache_s, drive_suffix)

                    # rename any cache file. after database query

                    # rename any database tables
                    if os.path.isfile(dbtarget):
                        sys_tables, cache_table, _ = get_idx_tables(basedir, None, suffix)
                        sys_a, sys_b = sys_tables
                        sys_tables, cache_table2, _ = get_idx_tables(basedir, None, drive_suffix)
                        sys_a2, sys_b2 = sys_tables
                        table_list = [
                            (sys_a, sys_a2),
                            (sys_b, sys_b2),
                            (cache_table, cache_table2),
                            (systimeche, new_systimeche)
                        ]
                        conn = cur = None
                        try:
                            if iqt:
                                user = None
                            conn = create_conn(dbopt, dbtarget, email, user=user)
                            cur = conn.cursor()

                            for table in table_list:
                                table_name = table[0]
                                if table_exists(conn, table_name):
                                    cur.execute(f"""
                                        UPDATE {table_name}
                                        SET filename = REPLACE(filename, ?, ?)
                                        WHERE filename LIKE ?;
                                    """, (moi, basedir, moi + "%"))
                                    cur.execute(f"""
                                        UPDATE {table_name}
                                        SET target = REPLACE(target, ?, ?)
                                        WHERE target LIKE ?;
                                    """, (moi, basedir, moi + "%"))

                            for old_table, new_table in table_list:
                                if table_exists(conn, old_table):
                                    cur.execute(f"ALTER TABLE {old_table} RENAME TO {new_table};")
                            conn.commit()
                            cur.close()
                            conn.close()
                            cur = conn = None

                            if os.path.isfile(old_cache_s):
                                os.rename(old_cache_s, new_cache_s)
                            update_dict(None, j_settings, suffix)  # remove the old

                        except Exception as e:
                            if conn:
                                conn.rollback()
                            print(f"Database error get_cache_files while moving tables db {dbopt} err {type(e).__name__}: {e}\ncontinuing")
                        finally:
                            clear_conn(conn, cur)

                    drive_info["mount_of_index"] = basedir
                    drive_info["idx_suffix"] = drive_suffix
                    j_settings[basedir] = drive_info  # add the new now that nothing went wrong
                    dump_j_settings(j_settings, json_file)

                    suffix = drive_suffix
                    cache_file = new_cache_s
                    systimeche = new_systimeche

            # add x per duplicate
            else:
                suffix = ('x' * x) + drive_suffix
                update_dict({"drive_partuuid": uuid}, j_settings, suffix)
                dump_j_settings(j_settings, json_file)

        except Exception as e:
            print(f"Error getting cache files for drive {basedir} err: {type(e).__name__} {e}")
            return None, None, None

    if not cache_file:
        cache_file, systimeche, _ = get_cache_s(basedir, cache_s, suffix)

    return cache_file, systimeche, suffix


def setup_drive_cache(basedir, appdata_local, dbopt, dbtarget, json_file, toml_file, cache_s, driveTYPE, usr, email, j_settings=None, partuuid=None, iqt=False):

    if driveTYPE:
        if driveTYPE.lower() not in ('hdd', 'ssd'):
            print(f"Incorrect setting driveTYPE: {driveTYPE} in config: {toml_file}")
            return None, None, None, None

    cache_s, systimeche, suffix = get_cache_files(basedir, dbopt, dbtarget, cache_s, json_file, usr, email, j_settings, partuuid, iqt)  # confirm the uuid and build the cache_s and suffix
    if not suffix:
        return None, None, None, None

    saved_dt = None
    if j_settings:
        dtype = j_settings.get(suffix, {}).get("drive_type")
        if dtype in ("HDD", "SSD"):
            saved_dt = dtype

        # case where user changed the drive in toml but has no entry in json. set it to None so type can be detected
        if not dtype:
            driveTYPE = None

    if driveTYPE in ("HDD", "SSD"):
        if saved_dt and saved_dt != driveTYPE:
            print("saved drive type doesnt match config.toml. using", driveTYPE, "update config.toml if this doesnt match the drive")
        return cache_s, systimeche, suffix, driveTYPE

    driveTYPE = setup_drive_settings(basedir, suffix, driveTYPE, toml_file, json_file, j_settings, False, appdata_local)
    if driveTYPE is None:
        print(f"An error occured set SSD or HDD in {toml_file} for {basedir}")
        return None, None, None, None
    elif driveTYPE.lower() not in ('hdd', 'ssd'):
        print(f"Incorrect setting driveTYPE: {driveTYPE} in config: {toml_file}")
        return None, None, None, None

    return cache_s, systimeche, suffix, driveTYPE


def collect_files(root, excluded_paths, min_size, max_total):
    files = []
    total = 0
    stack = [root]

    while stack:
        path = stack.pop()
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_dir():
                        if entry.path in excluded_paths:
                            continue
                        stack.append(entry.path)
                        continue

                    size = entry.stat().st_size

                    if size < min_size:
                        continue

                    files.append((entry.path, size))
                    total += size

                    if total >= max_total:
                        return files, total
                except (FileNotFoundError, PermissionError):
                    continue
        except (FileNotFoundError, PermissionError):
            continue
    return files, total


def perform_read_test(appdata_local, basedir, user, xdg_settings="", exclDIRS=None, log_fn=print):

    # save current pwd
    # old_dir = os.getcwd()
    # try:
    #     os.chdir(DATA_DIR)
    # finally:
    #     os.chdir(old_dir)

    # windows version
    # drive = parse_drive(basedir)
    # result = subprocess.run(
    #     ["winsat", "disk", "-drive", drive, "-seq", "-read"],
    #     capture_output=True,
    #     text=True,
    #     check=True,
    # )
    # print(result.stdout)
    # return result.returncode
    if not exclDIRS:
        # set environment
        set_xdg(xdg_settings)

        appdata_local = Path(appdata_local)
        # tempdir = Path(tempdir)
        config_data = get_config_data(appdata_local, user)
        exclDIRS = config_data.exclDIRS

    try:

        DATA_DIR = basedir

        exclusions = []
        for excluded in exclDIRS + list(MOUNT_FOLDERS):
            entry = os.path.join(DATA_DIR, excluded)
            exclusions.append(entry)

        files, total = collect_files(
            DATA_DIR,
            set(exclusions),
            MIN_FILE_SIZE,
            MAX_TOTAL_BYTES
        )

        if not files:
            log_fn("nothing to test")
            return 1
        out_str = (
            f"collected {len(files)} files, "
            f"{total / (1024 * 1024):.1f} MB"
        )
        log_fn(out_str)

        # drop cache
        subprocess.run(['sync'])
        with open('/proc/sys/vm/drop_caches', 'w') as f:
            f.write('3')

        random.shuffle(files)

        selected = []
        total_read = 0
        for path, size in files:
            selected.append((path, size))
            total_read += size
            if total_read >= TOTAL_TEST_BYTES:
                break

        start = time.perf_counter()

        total = 0
        for path, size in selected:  # files:
            # log_fn(path)
            try:
                with open(path, 'rb') as f:
                    while chunk := f.read(READ_SIZE):
                        total += len(chunk)
            except OSError:
                pass

        elapsed = time.perf_counter() - start
        log_fn("")
        log_fn(f"{total / elapsed / (1024**2):.2f} MB/s")
        return 0

    except subprocess.CalledProcessError as e:
        log_fn(f"perform_read_test failed with exit code {e.returncode}")
        log_fn(e.stdout or "")
        log_fn(e.stderr or "")
        return e.returncode
    except Exception as e:
        log_fn(f"Unexpected error while performing read test {type(e).__name__}, {e}")
        return 1

# initial test writing a 500MB file hdd is usually below 100 MB/s ect its a rough test which cant be conclusive

# OUTPUT_FILE = r"D:\write_test.bin"
# SIZE = 500 * 1024 * 1024  # 500 MiB
# CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB
# print(f"Writing {SIZE / 1024 / 1024:.0f} MiB to {OUTPUT_FILE}...")
# start = time.perf_counter()
# with open(OUTPUT_FILE, "wb", buffering=0) as f:
#     remaining = SIZE
#     while remaining:
#         chunk = min(CHUNK_SIZE, remaining)
#         f.write(os.urandom(chunk))
#         remaining -= chunk
#     os.fsync(f.fileno())
# elapsed = time.perf_counter() - start
# speed = SIZE / elapsed / (1024 * 1024)
# print(f"Time:  {elapsed:.2f} seconds")
# print(f"Speed: {speed:.2f} MiB/s")
# print(f"File:  {OUTPUT_FILE}")

# find out how much winsat or a benchmark process writes for their test
# print(psutil.disk_io_counters(perdisk=True))
# from src.wmipy import get_disk_and_volume_for_drive
# d, v = get_disk_and_volume_for_drive("C:")
# print(d, v)
# before = psutil.disk_io_counters(perdisk=True)["PhysicalDrive2"]
# subprocess.run(["winsat", "disk", "-drive", "d", "-seq", "-read"])
# after = psutil.disk_io_counters(perdisk=True)["PhysicalDrive2"]
# print("Bytes written:", (after.write_bytes - before.write_bytes) / 1024 / 1024, "MiB")

# below uses of threads for higher queue depth to identify if a drive is a hdd by iops not scaling with concurrency which can be conclusive
# to identify if a drive is a hdd or ssd. Will expand on this later as its easier on linux as you can dump the caches. On windows you would
# have to read from the database if this is the first time the app is start since system reboot for that drive to ensure nothing is cached.
# this is why using winsat for the windows version of qt.
# from concurrent.futures import ThreadPoolExecutor
# files, total = collect_files(
#     DATA_DIR,
#     set({"C:\\Windows"}),
#     MIN_FILE_SIZE,
#     MAX_TOTAL_BYTES
# )
# print(
#     f"collected {len(files)} files, "
#     f"{total / (1024 * 1024):.1f} MB"
# )
# print(f"{'threads':>8} {'MB/s':>12} {'IOPS':>12} {'seconds':>10}")
# for tc in THREAD_COUNTS:
#     speed, iops, elapsed = run_test(tc, files)
#     print(
#         f"{tc:>8} "
#         f"{speed:>12.2f} "
#         f"{iops:>12.2f} "
#         f"{elapsed:>10.2f}"
#     )
# def random_read(path, size):
#     try:
#         with open(path, "rb", buffering=0) as f:
#             for _ in range(READS_PER_FILE):
#                 max_offset = size - READ_SIZE
#                 if max_offset <= 0:
#                     offset = 0
#                 else:
#                     offset = random.randint(0, max_offset)
#                 f.seek(offset)
#                 f.read(READ_SIZE)
#     except OSError:
#         pass
# def run_test(thread_count, files):
#     files = files.copy()
#     random.shuffle(files)
#     selected = []
#     total_read = 0
#     total_ops = 0
#     for path, size in files:
#         selected.append((path, size))
#         total_read += READ_SIZE * READS_PER_FILE
#         total_ops += READS_PER_FILE
#         if total_read >= TOTAL_TEST_BYTES:
#             break
#     start = time.perf_counter()
#     with ThreadPoolExecutor(max_workers=thread_count) as ex:
#         list(ex.map(lambda x: random_read(*x), selected))
#     elapsed = time.perf_counter() - start
#     read_speed = total_read / elapsed / (1024 * 1024)
#     iops = total_ops / elapsed
#     return read_speed, iops, elapsed
