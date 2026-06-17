#!/usr/bin/env python3
# pstsrg.py - Process and store logs in a SQLite database, encrypting the database       06/17/2026
import os
import sqlite3
import sys
import traceback
from .qtfunctions import find_gnupg_home
from .dirwalker import index_system
from .gpgcrypto import encr
from .gpgcrypto import decr
from .hanlyparallel import hanly_parallel
from .pyfunctions import cprint
from .pyfunctions import unescf_py
from .pysql import clear_conn
from .pysql import create_db
from .pysql import collision_check
from .pysql import get_unique_files
from .pysql import get_total_throughput
from .pysql import insert
from .pysql import insert_files_time
from .pysql import insert_if_not_exists
from .pysql import table_has_data
from .qtdrivefunctions import get_idx_tables
from .query import blank_count
from .pyfunctions import cnc
from .rntchangesfunctions import removefile


def main(dbopt, dbtarget, xdata, complete, rout, cachermPATTERNS, user_setting, logging_values, total_time, total_files, dcr=False, iqt=False, strt=65, endp=90):

    # tempwork = logging_values[3]  # the script temp directory
    scr = logging_values[4]
    cerr = logging_values[5]
    # cache_f = logging_values[6]
    cache_s = logging_values[7]
    json_file = logging_values[8]
    gnupg_home = logging_values[9]

    user = user_setting['usr']
    basedir = user_setting['basedir']
    email = user_setting['email']
    model_type = user_setting['driveTYPE']
    analytics = user_setting['analytics']
    checksum = user_setting['checksum']
    cdiag = user_setting['cdiag']
    ps = user_setting['ps']
    compLVL = user_setting['compLVL']

    sys_tables, _, _ = get_idx_tables(basedir, cache_s)

    parsed = []

    csum = False
    new_profile = False
    new_database = False
    db_error = False
    goahead = True
    is_ps = False
    conn = None

    res = 0

    ha_total_time = logger_total_time = 0
    unique_files = 0
    total_throughput = 0

    # original with a temp dir cant leave db to reencrypt if everything succeeds but only reencryption fails. so leave in app directory with proper perms
    # tempdir = tempfile.gettempdir()
    # tempdir = tempfile.mkdtemp()
    # os.makedirs(tempdir, exist_ok=True)
    # with tempfile.TemporaryDirectory(dir=tempdir) as tempwork:
    # dbopt = name_of(dbtarget, 'db')   # generic output database
    # with tempfile.TemporaryDirectory(dir='/tmp') as tempdir:
    #     dbopt = os.path.join(tempdir, dbopt)

    # app_dir = os.path.dirname(dbtarget)
    # dbopt = os.path.join(app_dir, outfile)

    if not iqt:
        if os.path.isfile(dbtarget):
            result, err = decr(dbtarget, dbopt, user)
            if not result:
                print(err)
                return None, None
        else:
            try:
                conn = create_db(dbopt, sys_tables)
                cprint.green('Persistent database created')
                goahead = False
            except Exception as e:
                print("Failed to create db:", e)
                return None, None
    else:
        if not os.path.isfile(dbtarget):
            goahead = False

    try:
        if not os.path.isfile(dbopt):
            print("pstrg: cant find db unable to continue", dbopt)
            return None, None
        if not conn:
            conn = sqlite3.connect(dbopt)
    except Exception as e:
        print(f'failed with error: {e}')
        print()
        print("Unable to connect to database and do hybrid analysis")
        if not dcr:
            removefile(dbopt)
        return None, None

    try:
        c = conn.cursor()

        drive_sys_table = sys_tables[0]
        if table_has_data(conn, drive_sys_table):
            is_ps = True
        else:
            # initial Sys profile
            if ps and checksum and not iqt:

                new_profile = True

                gnupg_home = find_gnupg_home(json_file, str(gnupg_home))

                print('Generating system profile.')
                appdata_local = logging_values[2]
                res = index_system(appdata_local, dbopt, dbtarget, basedir, user, cache_s, email, analytics, False, gnupg_home, compLVL, iqt, strt, endp)
                if res != 0:
                    print("index_system from dirwalker failed to hash in pstsrg")

            elif ps and not iqt:
                print('Sys profile requires the setting checksum to index')

        # Analytics - Store the total files and total time for the search. Also get unique files and lifetime throughput.
        if total_files:
            if total_time > 0:
                insert_files_time(c, total_files, total_time)  # insert the run file count and time
                conn.commit()
            unique_files = get_unique_files(c)

            if not unique_files:
                goahead = False
                new_database = True

            # it is not the first run
            # Lifetime throughput
            # get the lifetime total files processed and total time since app or database was made
            else:

                total_throughput = get_total_throughput(c)

                if not total_throughput:
                    print("pstsrg couldnt get analytics. skipped")
                # end Lifetime throughput

        # Log
        if xdata:

            if goahead:  # Hybrid analysis. Skip first pass ect.

                try:
                    if iqt:
                        print(f"Progress: {strt}", flush=True)

                    csum, ha_total_time, logger_total_time = hanly_parallel(model_type, rout, scr, cerr, xdata, cachermPATTERNS, checksum, cdiag, dbopt, is_ps, user, logging_values, sys_tables, iqt, strt, endp)

                except Exception as e:
                    print(f"hanlydb failed to process : {type(e).__name__} : {e} \n{traceback.format_exc().strip()}", file=sys.stderr)

            for record in xdata:
                parsed.append(record[:16])  # trim escf_path from end sortcomplete

        if parsed:
            try:

                insert(parsed, conn, c, "logs", "mtime_us")

                count = blank_count(c)
                if count % 10 == 0:
                    print(f'{count + 1} searches in gpg database')

                if checksum and cdiag:
                    if collision_check(xdata, cerr, sys_tables, c, ps):
                        csum = True

            except Exception as e:
                print(f'log db failed insert err: {e} {type(e).__name__}  \n{traceback.format_exc()}')
                db_error = True

            if model_type.lower() != 'hdd':
                x = os.cpu_count()
                if x:
                    if not csum:
                        print(f'Detected {x} CPU cores.')

        # Stats
        if rout:

            if complete:  # store no such files
                rout.extend(" ".join(map(str, item)) for item in complete)

            try:
                for record in rout:
                    # parts = record.strip().split(None, 5)  # original
                    parts = record.strip().split(maxsplit=5)
                    if len(parts) < 6:
                        continue
                    action = parts[0]
                    timestamp = f'{parts[1]} {parts[2]}'
                    changetime = f'{parts[3]} {parts[4]}'
                    fp_escaped = parts[5]
                    fp = unescf_py(fp_escaped)
                    insert_if_not_exists(action, timestamp, fp, changetime, conn, c)

            except Exception as e:
                print(f'stats db failed to insert err: {e}  \n{traceback.format_exc()}')
                db_error = True

        sts = False

        # Encrypt if o.k.
        if not db_error:
            try:
                conn.commit()
                nc = cnc(dbopt, compLVL)
                if new_profile:
                    dcr = False
                sts = encr(dbopt, dbtarget, email, user=user, no_compression=nc, dcr=dcr)
                if not sts:
                    res = 3  # & 2 gpg problem
                    print(f'Failed to encrypt database. Run   gpg --yes -e -r {email} -o {dbtarget} {dbopt}  before running again to preserve data.')

            except Exception as e:
                res = 3
                print(f'Encryption failed pstsrg.py: {e}')

        else:
            conn.rollback()
            res = 4  # delete any changes made.
            print('There is a problem with the database.')
    finally:
        clear_conn(conn, c)

    data = (csum, unique_files, total_throughput, ha_total_time, logger_total_time)

    if not dcr and res != 3:
        removefile(dbopt)
    if res == 0 and new_profile:
        return "new_profile", data
    elif res == 0 and new_database:
        return "new_database", data
    elif res == 0:
        return dbopt, data
        # return 0
    elif res == 3:
        return "encr_error", data
    elif res == 4:
        return "db_error", data
    return None, None
