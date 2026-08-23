import logging
import os
import sqlcipher3
import subprocess
import traceback
from collections import defaultdict
from pathlib import Path
from .dirwalkerfunctions import flatten_dict
from .dirwalkerfunctions import get_config_data
from .gpgcrypto import encr_sys_cache
from .logs import setup_logger
from .pyfunctions import convert_mime_to_int
from .pysql import clear_conn
from .pysql import clear_table
from .pysql import create_conn
from .pysql import create_sys_tables
from .pysql import create_table_cache
from .pysql import get_mime_map
from .pysql import get_sys_changes
from .pysql import increment_f
from .pysql import insert_mimes
from .pysql import insert_cache
from .pysql import table_has_data
from .pysql import update_cache
from .qtdrivefunctions import get_idx_tables
from .qtdrivefunctions import parse_systimeche
from .rntchangesfunctions import set_xdg
# 08/21/2026


# functions for find_created index_system and scan_system


def sync_db(dbopt, dbtarget, user, email, basedir, cache_s, parsedsys, parsedidx, sys_records, new_mime_rows, keys=None, from_idx=False):
    '''
        insert changes into sys2 or sys2_sda table. sys or sys_sda table have originals.
        ie for / sys2, sys
        for /mnt/nvme0n1p1 sys2_nvme0n1p1, sys_nvme0n1p1 '''

    systimeche, suffix = parse_systimeche(basedir, cache_s)

    sys_tables, cache_table, _ = get_idx_tables(basedir, None, suffix)

    res = False
    conn = cur = None

    try:

        conn = create_conn(dbopt, dbtarget, email, user=user)
        cur = conn.cursor()
        # scan IDX
        if sys_records:

            insert_mimes(cur, new_mime_rows)

            res = increment_f(conn, cur, sys_tables, sys_records, logger=logging)
            if res:
                conn.commit()

        # build IDX
        elif parsedsys:

            drive_sys_table = sys_tables[0]
            drive_sys_changes_table = sys_tables[1]

            with conn:
                # if table_exists(conn, drive_sys_table):
                #     clear_table(drive_sys_table, conn, cur, True)

                # 06/15/2026 remove scan history for the profile
                cur.execute(f"DROP TABLE IF EXISTS {drive_sys_table}")
                cur.execute(f"DROP TABLE IF EXISTS {drive_sys_changes_table}")
                # conn.commit()
                create_sys_tables(conn, sys_tables)
                create_table_cache(conn, cache_table, ('filename',))
                create_table_cache(conn, systimeche, ('filename',))

                if table_has_data(conn, systimeche):
                    clear_table(systimeche, conn, cur, True)
                if table_has_data(conn, cache_table):
                    clear_table(cache_table, conn, cur, True)

                # 07/20/2026
                mime_hashmap, id_to_mime = get_mime_map(cur)
                # map mime str to an int for database
                parsed_revised, new_mime_rows, next_mime_id = convert_mime_to_int(parsedsys, mime_hashmap, id_to_mime)

                cur.execute("DELETE FROM scan_entries WHERE basedir = ?", (basedir,))
                cur.execute("DELETE FROM scans WHERE id NOT IN (SELECT DISTINCT scan_id FROM scan_entries)")
                cur.executemany(f"""
                    INSERT OR IGNORE INTO {drive_sys_table} (
                        timestamp, filename, changetime, inode, accesstime,
                        checksum, entropy, mime_id, filesize, symlink, owner,
                        `group`, permissions, casmod, target, lastmodified,
                        hardlinks, count, mtime_us
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, parsed_revised)

                insert_mimes(cur, new_mime_rows)

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
            with conn:
                if table_has_data(conn, systimeche):
                    clear_table(systimeche, conn, cur, True)
                create_table_cache(conn, systimeche, ('filename',))

                if insert_cache(parsedidx, systimeche, conn):
                    res = True

                else:
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

    except sqlcipher3.Error as e:
        if conn:
            conn.rollback()
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


def save_db(dbopt, dbtarget, basedir, cache_s, email, user, parsedsys, parsedidx, sys_records, new_mime_rows, keys=None, idx_drive=False):
    if sync_db(dbopt, dbtarget, user, email, basedir, cache_s, parsedsys, parsedidx, sys_records, new_mime_rows, keys, idx_drive):
        return True
    return False


def index_drive(dbopt, dbtarget, basedir, cache_s, email, user, parsedsys, parsedidx, dir_data, idx_drive, error_message):
    ''' encrypt the cache and then save in database '''
    if save_db(dbopt, dbtarget, basedir, cache_s, email, user, parsedsys, parsedidx, None, None, None, idx_drive):
        if dir_data:

            if encr_sys_cache(dir_data, cache_s, email, user=user):
                return 0
            else:
                print(error_message)
                return 1

    else:
        print("Failed to sync db. index_system from dirwalkersrg")
    return 4


def create_new_index(dbopt, dbtarget, basedir, cache_s, email, user, parsedsys, dir_data, idx_drive=False, error_message=None):
    ''' flatten dict of dicts and store. save cache file and store in db '''
    if dir_data:
        parsedidx = flatten_dict(dir_data)

        return index_drive(dbopt, dbtarget, basedir, cache_s, email, user, parsedsys, parsedidx, dir_data, idx_drive, error_message)
    else:
        print("No directories to cache. the cache file was empty")

    return 1


def db_sys_changes(dbopt, dbtarget, user, email, sys_tables):
    conn = None
    cur = None
    try:
        conn = create_conn(dbopt, dbtarget, email, user=user)
        cur = conn.cursor()
        sys_a, sys_b = sys_tables

        if not table_has_data(conn, sys_a):
            return False

        recent_sys = get_sys_changes(cur, sys_a, sys_b)

        mime_hashmap, id_to_mime = get_mime_map(cur)

        return recent_sys, mime_hashmap, id_to_mime

    except (sqlcipher3.Error, Exception) as e:
        print(f"Problem retrieving profile data for system index in db_sys_changes dirwalkersrg. database {dbopt} {type(e).__name__} error: {e}")
    finally:
        clear_conn(conn, cur)
    return None, None, None
# end functions for find_created index_system and scan_system

# scan idx functions


def insert_differences(cur, basedir, all_sys, scan_start):

    # table format
    #     'timestamp TEXT',
    #     'filename TEXT',
    #     'changetime TEXT',
    #     'inode INTEGER',
    #     'accesstime TEXT',
    #     "checksum TEXT",  # NOT NULL DEFAULT ''
    #     'entropy REAL',
    #     'mime_id INTEGER',
    #     'filesize INTEGER',
    #     'symlink TEXT',
    #     'owner TEXT',
    #     '`group` TEXT',
    #     'mode TEXT',
    #     'casmod TEXT',
    #     'target TEXT',
    #     'lastmodified TEXT',
    #     'hardlinks INTEGER'
    #     'count INTEGER',
    #     'mtime_us INTEGER'

    # cursor.execute("SELECT MAX(id) FROM scans")
    # last_id = cursor.fetchone()[0] or 0
    # sql = f"INSERT INTO scans (scantime) VALUES (?)", (scan_start),

    if not all_sys:
        return

    try:
        cur.execute("INSERT INTO scans (scantime) VALUES (?)", (scan_start,))
        scan_id = cur.lastrowid
    except sqlcipher3.Error:
        print("insert_differences was unable to insert into table: scans")
        raise

    rows = [(scan_id, basedir) + row for row in all_sys]

    try:
        cur.executemany("""
            INSERT INTO scan_entries (
                scan_id, basedir, timestamp, filename, changetime, inode,
                accesstime, checksum, entropy, mime_id, filesize, symlink,
                owner, `group`, permissions, casmod, target, lastmodified,
                hardlinks, count, mtime_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
    except sqlcipher3.Error:
        print("table: scan_entries")
        raise


def db_scans(cur, basedir):

    cur.execute("""
        SELECT e.*, s.scantime FROM scan_entries e
        JOIN scans s ON e.scan_id = s.id
        WHERE e.basedir = ?
        ORDER BY s.scantime
    """, (basedir,))
    rows = cur.fetchall()

    groups = defaultdict(list)
    for row in rows:
        d = dict(row)
        scantime = d.pop("scantime")
        groups[scantime].append(d)

    return groups


def differences_db(dbopt, dbtarget, user, email, basedir, all_sys, sys_tables, cache_table, systimeche, showDiff, scan_start):
    """ get the old scans insert the new scan and pull differences from when the profile
        was first made """

    link_diff, ent_diff, mime_diff, dir_diff, new_diff = [], [], [], [], []
    conn = cur = None
    table = ""
    try:
        conn = create_conn(dbopt, dbtarget, email, user=user)
        conn.row_factory = sqlcipher3.Row
        cur = conn.cursor()

        table = "scans"
        prev_scans = db_scans(cur, basedir)

        table = ""
        insert_differences(cur, basedir, all_sys, scan_start)
        conn.commit()

        if showDiff:

            sys_a, sys_b = sys_tables
            table = sys_a + " " + sys_b

            query = f"""
                SELECT b.* FROM {sys_b} b
                JOIN {sys_a} a ON a.filename = b.filename
                WHERE b.target <> a.target
                AND b.timestamp = (
                    SELECT MAX(timestamp) FROM {sys_b} b2
                    WHERE b2.filename = b.filename
                )
                ORDER BY b.timestamp
            """
            cur.execute(query)
            link_diff = cur.fetchall()
            query = f"""
                SELECT b.* FROM {sys_b} b
                JOIN {sys_a} a ON a.filename = b.filename
                WHERE ABS(b.entropy - a.entropy) >= 0.5
                AND b.timestamp = (
                    SELECT MAX(timestamp) FROM {sys_b} b2
                    WHERE b2.filename = b.filename
                )
                ORDER BY b.timestamp
            """
            cur.execute(query)
            ent_diff = cur.fetchall()
            query = f"""
                SELECT b.* FROM {sys_b} b
                JOIN {sys_a} a ON a.filename = b.filename
                WHERE b.mime_id <> a.mime_id
                AND b.timestamp = (
                    SELECT MAX(timestamp) FROM {sys_b} b2
                    WHERE b2.filename = b.filename
                )
                ORDER BY b.timestamp
            """
            cur.execute(query)
            mime_diff = cur.fetchall()

            # dirs that had no files and now do

            if table_has_data(conn, systimeche):
                table = systimeche
                query = f"""
                    SELECT s.modified_time,
                        s.filename,
                        s.file_count
                    FROM {systimeche} AS s
                    WHERE s.file_count > 0
                    AND s.type IS NULL
                    AND EXISTS (
                            SELECT 1
                            FROM {cache_table} AS c
                            WHERE c.filename = s.filename
                            AND c.file_count = 0
                            AND c.type IS NULL
                    )
                """
                cur.execute(query)
                dir_diff = cur.fetchall()
            else:
                table = cache_table
                query = f'''
                    SELECT modified_time,
                        filename,
                        file_count
                    FROM {cache_table}
                    WHERE file_count = 0
                    AND type IS NULL
                '''
                cur.execute(query)
                records = cur.fetchall()
                if records:
                    for record in records:
                        dirname = record[1]
                        if os.path.isdir(dirname):
                            try:
                                with os.scandir(dirname) as it:
                                    if any(entry.is_file() for entry in it):
                                        dir_diff.append(record)
                            except (FileNotFoundError, PermissionError):
                                pass

            table = systimeche + " " + cache_table

            # new directories

            sql = f"""
            SELECT DISTINCT s.filename
            FROM {systimeche} s
            LEFT JOIN {cache_table} c ON s.filename = c.filename
            WHERE c.filename IS NULL
            """
            cur.execute(sql)
            new_diff = [row[0] for row in cur.fetchall()]

        return prev_scans, link_diff, ent_diff, mime_diff, dir_diff, new_diff
    except sqlcipher3.Error as e:
        print(f"dirwalkersrg.py problem retrieving data in differences_db. database {dbopt} {'tables ' + table if table else ''} {type(e).__name__} error: {e}")
        return None, None, None, None, None, None
    except Exception as e:
        print(f"General error occurred in differences_db {type(e).__name__} error: {e} \n{traceback.format_exc()}")
        logging.error(f"differences_db profile {'tables ' + table if table else ''} {type(e).__name__} error: {e}\n", exc_info=True)
        return None, None, None, None, None, None
    finally:
        clear_conn(conn, cur)
# end scan idx functions


def hardlinks(basedir, database, target, conn, cur, email, user, logger=None):
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
            print("Hard links updated.")
            return True

    except sqlcipher3.Error as e:
        print(f"hardlinks Error executing database query/update. err: {type(e).__name__}: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        em = f"Error setting hardlinks: {e} {type(e).__name__}"  # \n{traceback.format_exc()}
        print(em)
        logger.error(em, exc_info=True)
    return None


def set_hardlinks(appdata_local, dbopt, dbtarget, basedir, user, uid, gid, tempdir, email, xdg_settings):
    '''
        update the hardlink state for all files in the logs table. Any files that no longer exist are NULL and
        is useful to see that those file dont exist in the database viewer '''

    # set environment
    set_xdg(xdg_settings)
    appdata_local = Path(appdata_local)
    # tempdir = Path(tempdir)
    config_data = get_config_data(appdata_local, user)
    log_file = config_data.log_file
    ll_level = config_data.ll_level
    logging_values = (appdata_local, ll_level, tempdir)
    logger = setup_logger(log_file, logging_values[1], "HARDLINKS")
    # change_perm(log_file, uid, gid)

    rlt = 1

    if os.path.isfile(dbopt):
        try:
            conn = create_conn(dbopt, dbtarget, email, user=user)
            cur = conn.cursor()

            sts = hardlinks(basedir, dbopt, dbtarget, conn, cur, email, user, logger)
            if sts:
                cur.close()
                conn.close()
                cur = conn = None

                print("Progress: 100.00%", flush=True)
                rlt = 0
            # change_perm(dbtarget, uid, gid, 0o644)

        finally:
            clear_conn(conn, cur)

    else:
        print("dirwalker.py could not find dbopt: ", dbopt)

    return rlt

# alternative to above used by windows
# cur.execute("SELECT filename, inode, symlink FROM logs WHERE hardlinks is NOT NULL and hardlinks != ''")
# file_rows = cur.fetchall()
# matches = []
# for record in file_rows:
#     file_path = record[0]
#     inode = record[1]
#     symlink = record[2]
#     if symlink != "y":
#         if os.path.isfile(file_path):
#             count_val = hlink_count(file_path=file_path, logger=logger)
#             if count_val:
#                 matches.append((count_val, inode, file_path))
# if matches:
