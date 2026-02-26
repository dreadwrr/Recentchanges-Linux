import os
import psutil
import pyudev
import sqlite3
import subprocess
from pathlib import Path
from .configfunctions import get_json_settings
from .configfunctions import dump_j_settings
from .configfunctions import set_json_settings
from .configfunctions import update_dict
from .configfunctions import update_toml_values
from .gpgcrypto import decr
from .gpgcrypto import encr
from .pysql import table_exists
from .rntchangesfunctions import cnc
from .rntchangesfunctions import name_of


def parse_drive(basedir):
    return os.path.basename(basedir)  # get sdx from /mnt/sdx


def parse_suffix(input_text: str):
    if input_text == "cache_s":
        return input_text, None
    parts = input_text.split('_', 1)
    key = parts[1] if len(parts) > 1 else ""
    return parts[0], key


def parse_systimeche(basedir, CACHE_S):
    """ systimeche table from CACHE_S """
    # get the key from actual cache file
    systimeche = name_of(CACHE_S)
    key = basedir
    if basedir != "/":
        systimeche, key = systimeche.split("_", 1)
        systimeche = systimeche + f"_{key}"
    return systimeche, key


def get_cache_s(basedir, cache_file, idx_suffix=None):
    """ initial setup """
    # / has systimeche.gpg for CACHE_S and systimeche for cache table
    # other systimeche_sdx.gpg for CACHE_S and systimeche_sdx table for cache table

    prefix = name_of(cache_file)
    CACHE_S = cache_file
    systimeche = prefix
    key = basedir
    if basedir != "/":
        if not idx_suffix:
            raise TypeError("idx_suffix requires for drive", basedir)
        key = idx_suffix
        CACHE_S = prefix + f"_{key}.gpg"
        app_path = os.path.dirname(cache_file)
        CACHE_S = os.path.join(app_path, CACHE_S)
        systimeche = prefix + f"_{key}"
    return CACHE_S, systimeche, key


def get_idx_tables(basedir, cache_file, idx_suffix=None):
    """ pass actual cache_file or key """
    # profile sys_ a changes sys _b. profile cache table
    # get the key from actual cache file

    sys_a = ""
    cache_table = "cache_s"
    key = basedir
    if basedir != "/":
        if idx_suffix:
            key = idx_suffix
        else:
            part = name_of(cache_file)
            key = part.split("_", 1)[-1]
        sys_a = f"_{key}"
        cache_table = "cache" + sys_a
    sys_b = "sys2" + sys_a
    sys_a = "sys" + sys_a
    return (sys_a, sys_b), cache_table, key


def get_new_idx_suffix(basedir, j_settings):
    if basedir == "/":
        return ""
    key = parse_drive(basedir)
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
    with open("/proc/self/mounts") as f:
        for line in f:
            parts = line.split()
            if parts[1] == mount_point:
                return os.path.basename(parts[0])
    return None


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
    drive_type = "HDD"
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
                        except FileNotFoundError/ValueError/OSError:
                            rotational = -1

            else:
                print(f"No device found for {base_dir}")
                return None

            if usb_drive:
                model_type = "USB"
                drive_type = "SSD"
            else:
                if drive_type != "SSD":
                    if rotational == 0:
                        drive_type = "SSD"

    except psutil.DeviceNotFoundByFileError:
        # / with unknown fs backing default to HDD and unknown
        pass
    except Exception as e:
        print("An error occurred in drive model check:", type(e).__name__, e)
        return None

    return (device_name, parent_device, drive_id_model, model_type, drive_type)


# check by model type, pnp description or rotation. if not run read test fall back to write test. if all fails set to HDD.
# user can set in config file config.toml for basedir. user can set in usrprofile.toml for index drive.
# Newer HDD drives have RotationRate in wmi. Older or legacy drives do not.
def setup_drive_settings(basedir, key, driveTYPE, toml_file, user_json=None, j_settings=None, idx_drive=False, lclapp_data=None):

    if driveTYPE:
        return driveTYPE

    # mmode = None
    # speedMB = None

    print("Determining drive type by model")  # or speed test
    drive_info = current_drive_type_model_check(basedir)
    if not drive_info:
        return None

    device_name, parent_device, drive_id_model, mtype, drive_type = drive_info
    # if we dont know
    if drive_type is None:
        print("Couldnt determine speed defaulting to HDD. change in config.toml to SSD", toml_file)
        drive_type = "HDD"

    model_type = mtype

    if toml_file and not idx_drive:
        update_toml_values({'search': {'driveTYPE': drive_type}}, toml_file)  # update config.toml the basedir

    # config.toml is where basedir ie / info is stored. the 'driveTYPE' HDD or SSD

    # if its an idx_drive usrprofile.json is where its info is stored. 'drive_type' and 'drive_model'
    #
    #
    # if we were to put the wrong info in usrprofile and config.toml the user would have to update two config files which is unlikely.

    if user_json:
        if idx_drive or model_type:
            if model_type is None:
                model_type = "Unknown"
            if key and j_settings is not None:

                update_dict({"idx_suffix": device_name, "parent_device": parent_device, "mount_of_index": basedir, "drive_id_model": drive_id_model, "model_type": model_type, "drive_type": drive_type}, j_settings, key)
                dump_j_settings(j_settings, user_json)
            elif key:
                set_json_settings({"idx_suffix": device_name, "parent_device": parent_device, "mount_of_index": basedir, "drive_id_model": drive_id_model, "model_type": model_type, "drive_type": drive_type}, drive=key, filepath=user_json)
    # print("idx_suffix ", device_name)
    # print("parent_device ", parent_device)
    # print("mount_of_index", basedir)
    print(f"model {drive_id_model}")
    print(f"model_type {model_type}")
    print(f"drive_type {drive_type}")
    return drive_type


def get_cache_files(basedir, dbopt, dbtarget, CACHE_S, json_file, user, email, compLVL, j_settings=None, partuuid=None, iqt=False):

    suffix = basedir
    cache_file = None
    systimeche = None

    if isinstance(j_settings, dict) and not j_settings:  # iqt
        jdata = get_json_settings(None, None, json_file)
        j_settings.update(jdata)

    if basedir != "/":

        if j_settings is None:  # command line
            j_settings = get_json_settings(None, None, json_file)

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

            drive_suffix = parse_drive(basedir)  # basedir.split('/')[-1]

            x = 0
            drive_info = None
            suffix = None

            found = False
            for key in j_settings.keys():
                drive_info = j_settings.get(key, {})
                if isinstance(drive_info, dict):
                    drive_partuuid = drive_info.get("drive_partuuid")
                    if not found and drive_partuuid and drive_partuuid == uuid:
                        suffix = key
                        found = True
                    elif isinstance(key, str) and key.endswith(drive_suffix):
                        x += 1

            if suffix:

                cache_file, systimeche, _ = get_cache_s(basedir, CACHE_S, suffix)

                # if the mountpoint changed for the uuid update json, move cache file and db tables
                if drive_suffix not in suffix:

                    # old
                    old_cache_s = cache_file

                    # new
                    drive_suffix = ('x' * x) + drive_suffix
                    new_cache_s, new_systimeche, _ = get_cache_s(basedir, CACHE_S, drive_suffix)

                    # rename any cache file
                    if os.path.isfile(old_cache_s):
                        os.rename(old_cache_s, new_cache_s)

                    # if from cmd line get db
                    if not os.path.isfile(dbopt):
                        if os.path.isfile(dbtarget):
                            res = decr(dbtarget, dbopt, user)
                            if not res:
                                if res is None:
                                    print(f"There is no key for {dbtarget}.")
                                else:
                                    print("Decryption failed. exiting.")
                                return None, None, None

                    # rename any database tables
                    if os.path.isfile(dbopt):
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
                        try:
                            psEXTN = drive_info.get("proteusEXTN")
                            moi = drive_info.get("mount_of_index")
                            with sqlite3.connect(dbopt) as conn:
                                cur = conn.cursor()
                                if psEXTN and moi:
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
                        except sqlite3.Error as e:
                            emsg = f"Database error get_cache_files while moving tables db {dbopt} err: {e}"
                            print(emsg)
                            # logging.error(emsg, exc_info=True)
                        nc = cnc(dbopt, compLVL)
                        if not encr(dbopt, dbtarget, email, user=user, no_compression=nc, dcr=iqt):  # leave open for gui
                            print(f"Reencryption failed on updating uuid for drive {basedir}.\n")
                            print("If unable to resolve reset json file and clear gpgs")
                            return None, None, None
                    update_dict(None, j_settings, suffix)  # remove the old
                    drive_info["mount_of_index"] = basedir
                    j_settings[drive_suffix] = drive_info  # add the new now that nothing went wrong
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
        cache_file, systimeche, _ = get_cache_s(basedir, CACHE_S, suffix)

    return cache_file, systimeche, suffix


def setup_drive_cache(basedir, appdata_local, dbopt, dbtarget, json_file, toml_file, CACHE_S, driveTYPE, USR, email, compLVL, j_settings=None, partuuid=None, iqt=False):

    CACHE_S, systimeche, suffix = get_cache_files(basedir, dbopt, dbtarget, CACHE_S, json_file, USR, email, compLVL, j_settings, partuuid, iqt)  # confirm the uuid and build the CACHE_S and suffix
    if not suffix:
        return None, None, None, None

    if j_settings and basedir != "/":
        driveTYPE = j_settings.get(suffix, {}).get("drive_type")
    if iqt:
        if not j_settings:
            driveTYPE = None

    driveTYPE = setup_drive_settings(basedir, suffix, driveTYPE, toml_file, json_file, j_settings, False, appdata_local)
    if driveTYPE is None:
        print(f"An error occured set SSD or HDD in {toml_file} for {basedir}")
        return None, None, None, None
    elif driveTYPE.lower() not in ('hdd', 'ssd'):
        print(f"Incorrect setting driveTYPE: {driveTYPE} in config: {toml_file}")
        return None, None, None, None

    return CACHE_S, systimeche, suffix, driveTYPE
