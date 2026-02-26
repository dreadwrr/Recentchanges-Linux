import logging
import os
import sqlite3
import subprocess
import traceback
from collections import defaultdict
from .dirwalkerfunctions import flatten_dict
from .gpgcrypto import encr
from .gpgcrypto import encr_sys_cache
from .pysql import clear_conn
from .pysql import clear_table
from .pysql import create_sys_table
from .pysql import create_table_cache
from .pysql import get_sys_changes
from .pysql import increment_f
from .pysql import insert_cache
from .pysql import table_exists
from .pysql import table_has_data
from .pysql import update_cache
from .qtdrivefunctions import get_idx_tables
from .qtdrivefunctions import parse_systimeche
from .rntchangesfunctions import cnc
# 02/04/2026


def hardlinks(basedir, database, target, conn, cur, email, user, compLVL):
    try:

        cur.execute("SELECT filename, inode FROM logs WHERE hardlinks is NOT NULL and hardlinks != ''")
        file_rows = cur.fetchall()

        cmd = [
            "find",
            basedir,
            "-xdev",
            "-type", "f",
            "-links", "+1",
            "-printf", "%i %n %p\n"
        ]
        strn = "running command:" + ' '.join(cmd)
        print(strn)

        result = subprocess.run(cmd, capture_output=True, text=True)
        ret_code = result.returncode
        is_error = False
        if ret_code != 0:

            if ret_code not in (0, 1):
                is_error = True
            for line in result.stderr.splitlines():
                print(line)
            if is_error:
                print(f"find exited with {ret_code}. An error occurred while retrieving hardlinks:")
                return 1

        # Build filesystem
        fs_inode_map = defaultdict(list)
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3:
                continue
            inode_str, count_str, path = parts
            inode = int(inode_str)
            count_val = int(count_str)
            fs_inode_map[inode].append((count_val, path))

        if not fs_inode_map or not file_rows:
            print("No results nothing to set")
            return True

        db_inode_map = defaultdict(set)
        for filename, inode in file_rows:
            if not filename:
                continue
            if os.path.isfile(filename):
                db_inode_map[int(inode)].add(filename)

        matches = []
        for inode, db_paths in db_inode_map.items():
            if inode in fs_inode_map:
                for path in db_paths:
                    for count_val, fs_path in fs_inode_map[inode]:
                        if path == fs_path:
                            matches.append((count_val, inode, path))
            else:
                for path in db_paths:
                    matches.append((1, inode, path))

        if matches:
            cur.execute("UPDATE logs SET hardlinks = NULL WHERE hardlinks IS NOT NULL AND hardlinks != ''")
            cur.executemany(
                "UPDATE logs SET hardlinks = ? WHERE inode = ? AND filename = ?",
                matches
            )
            conn.commit()
            nc = cnc(database, compLVL)
            rlt = encr(database, target, email, user=user, no_compression=nc, dcr=True)
            if rlt:
                print("Hard links updated.")
                return True
            else:
                print("Reencryption failed, hardlinks not set.")
                return False
    except sqlite3.Error as e:
        print(f"hardlinks Error executing database query/update. err: {type(e).__name__}: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error setting hardlinks: {e} {type(e).__name__} \n{traceback.format_exc()}")
    return None


# insert changes into sys2 or sys2_sda table. sys or sys_sda table have originals.
# ie for / sys2, sys
# for /mnt/nvme0n1p1 sys2_nvme0n1p1, sys_nvme0n1p1
def sync_db(dbopt, basedir, CACHE_S, parsedsys, parsedidx, sys_records, keys=None, from_idx=False):

    systimeche, suffix = parse_systimeche(basedir, CACHE_S)

    sys_tables, cache_table, _ = get_idx_tables(basedir, None, suffix)

    res = False
    conn = cur = None

    try:
        conn = sqlite3.connect(dbopt)
        cur = conn.cursor()

        # scan IDX
        if sys_records:
            res = increment_f(conn, cur, sys_tables, sys_records, logger=logging)

        # build IDX
        elif parsedsys:

            drive_sys_table = sys_tables[0]

            if table_exists(conn, drive_sys_table):
                clear_table(drive_sys_table, conn, cur, True)

            create_sys_table(conn, sys_tables)
            create_table_cache(conn, cache_table, ('filename',))
            create_table_cache(conn, systimeche, ('filename',))

            if table_has_data(conn, systimeche):
                clear_table(systimeche, conn, cur, True)
            if table_has_data(conn, cache_table):
                clear_table(cache_table, conn, cur, True)

            with conn:

                cur.executemany(f"""
                    INSERT OR IGNORE INTO {drive_sys_table} (
                        timestamp, filename, changetime, inode, accesstime,
                        checksum, filesize, symlink, owner, `group`, permissions,
                        casmod, target, lastmodified, hardlinks, count, mtime_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, parsedsys)

                if parsedidx:
                    cur.executemany(f"""
                        INSERT OR IGNORE INTO {cache_table} (
                            modified_time, filename, file_count, idx_count,
                            idx_bytes, max_depth, type, target
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, parsedidx)

                    cur.execute(f"""
                        INSERT INTO {systimeche} (
                            modified_time, filename, file_count, idx_count,
                            idx_bytes, max_depth, type, target
                        )
                        SELECT modified_time, filename, file_count, idx_count,
                            idx_bytes, max_depth, type, target
                        FROM {cache_table}
                    """)
                res = True

        # Find downloads add index
        elif from_idx and parsedidx:

            if table_has_data(conn, systimeche):
                clear_table(systimeche, conn, cur, True)
            create_table_cache(conn, systimeche, ('filename',))

            res = insert_cache(parsedidx, systimeche, conn)
            if not res:
                print(f"Failed to insert parsedidx for table {systimeche} drive {basedir} re sync_db")

        # Find download update index
        elif from_idx and keys:

            res = update_cache(keys, conn, systimeche)
            if not res:
                print(f"failed to update {systimeche} table for drive index for drive {basedir} in sync_db. dirwalkersrg.py")

            # if maintaining a full index can add remove but chance of desync
            # cur.executemany("DELETE FROM sys WHERE filepath = ?", del_keys)
            # conn.commit()
        else:
            print("Incorrect parameters for sync_db function dirwalkersrg.py. returning False")

        return res

    except sqlite3.Error as e:
        emsg = f"Database error sync_db in dirwalkersrg: {type(e).__name__} {e}"
        print(emsg)
        logging.error(emsg, exc_info=True)
    except Exception as e:
        emsg = f"Unexpected error in sync_db: {type(e).__name__} {e}"
        print(f"{emsg}  \n{traceback.format_exc()}")
        logging.error(emsg, exc_info=True)
    finally:
        clear_conn(conn, cur)
    return False


def create_new_index(dbopt, dbtarget, basedir, CACHE_S, email, user, parsedsys, dir_data, idx_drive=False, compLVL=200, dcr=True, error_message=None):

    if dir_data:
        parsedidx = flatten_dict(dir_data)

        # encrypt the cache and then save in database
        return index_drive(dbopt, dbtarget, basedir, CACHE_S, email, user, parsedsys, parsedidx, dir_data, idx_drive, compLVL, dcr, error_message)
    else:
        print("No directories to cache. the cache file was empty")

    return 1


def save_db(dbopt, dbtarget, basedir, CACHE_S, email, user, parsedsys, parsedidx, sys_records, keys=None, idx_drive=False, compLVL=200, dcr=True):
    if sync_db(dbopt, basedir, CACHE_S, parsedsys, parsedidx, sys_records, keys, idx_drive):

        nc = cnc(dbopt, compLVL)
        if encr(dbopt, dbtarget, email, user=user, no_compression=nc, dcr=dcr):
            return True
        else:
            print("Reencryption of database failed.")
    return False


def index_drive(dbopt, dbtarget, basedir, CACHE_S, email, user, parsedsys, parsedidx, dir_data, idx_drive, compLVL, dcr, error_message):

    if save_db(dbopt, dbtarget, basedir, CACHE_S, email, user, parsedsys, parsedidx, None, None, idx_drive, compLVL, dcr):
        if dir_data:

            if encr_sys_cache(dir_data, CACHE_S, email, user=user):
                return 0
            else:
                print(error_message)
                return 1
        else:
            return 0
    else:
        print("Failed to sync db. index_system from dirwalkersrg")
    return 4


def db_sys_changes(dbopt, sys_tables):
    conn = None
    cur = None
    try:
        conn = sqlite3.connect(dbopt)
        cur = conn.cursor()
        sys_a, sys_b = sys_tables

        if not table_has_data(conn, sys_a):
            return False

        recent_sys = get_sys_changes(cur, sys_a, sys_b)
        return recent_sys

    except (sqlite3.Error, Exception) as e:
        print(f"Problem retrieving profile data for system index in db_sys_changes dirwalkersrg. database {dbopt} {type(e).__name__} error: {e}")
    finally:
        clear_conn(conn, cur)
    return None
