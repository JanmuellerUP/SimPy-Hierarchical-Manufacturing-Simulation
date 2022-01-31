import sqlite3
import os
import time

import pandas as pd


def set_up_db(sim_env):
    if sim_env.DB_IN_MEMORY:
        db_con = sqlite3.connect(":memory:")
    else:
        try:
            os.remove("data/current_run.db")
        except:
            pass
        db_con = sqlite3.connect("data/current_run.db")

    db_cu = db_con.cursor()

    db_cu.execute("""CREATE TABLE machine_events (
                    machine INTEGER NOT NULL,
                    time FLOAT NOT NULL,
                    event TEXT NOT NULL,
                    est_time FLOAT,
                    next_setup_type INTEGER,
                    current_setup_type INTEGER,
                    load_item INTEGER NOT NULL CHECK(load_item IN (0,1)),
                    manufacturing INTEGER NOT NULL CHECK(manufacturing IN (0,1)),
                    setup INTEGER NOT NULL CHECK(setup IN (0,1)),
                    idle INTEGER NOT NULL CHECK(idle IN (0,1)),
                    repair INTEGER NOT NULL CHECK(repair IN (0,1)),
                    item_in_input INTEGER,
                    item_in_machine INTEGER,
                    item_in_output INTEGER
    )""")

    db_cu.execute("""CREATE TABLE agent_events (
                    agent INTEGER NOT NULL,
                    time FLOAT NOT NULL,
                    event TEXT NOT NULL,
                    next_position INTEGER,
                    travel_time FLOAT,
                    moving INTEGER NOT NULL CHECK(moving IN (0,1)),
                    waiting INTEGER NOT NULL CHECK(waiting IN (0,1)),
                    task INTEGER NOT NULL CHECK(task IN (0,1)),
                    position INTEGER,
                    picked_up_item INTEGER,
                    locked_item INTEGER
    )""")

    db_cu.execute("""CREATE TABLE item_events (
                            item INTEGER NOT NULL,
                            time FLOAT NOT NULL,
                            event TEXT NOT NULL,
                            started INTEGER NOT NULL CHECK(started IN (0,1)),
                            over_due INTEGER NOT NULL CHECK(over_due IN (0,1)),
                            blocked INTEGER NOT NULL CHECK(blocked IN (0,1)),
                            tasks_finished INTEGER NOT NULL CHECK(tasks_finished IN (0,1)),
                            completed INTEGER NOT NULL CHECK(completed IN (0,1)),
                            picked_up INTEGER NOT NULL CHECK(picked_up IN (0,1)),
                            transportation INTEGER NOT NULL CHECK(transportation IN (0,1)),
                            processing INTEGER NOT NULL CHECK(processing IN (0,1)),
                            wait_for_repair INTEGER NOT NULL CHECK(wait_for_repair IN (0,1)),
                            tasks_remaining INTEGER,
                            cell INTEGER,
                            position INTEGER,
                            position_type TEXT,
                            picked_up_by INTEGER,
                            locked_by INTEGER
                            )""")

    db_cu.execute("""CREATE TABLE buffer_events (
                            buffer INTEGER NOT NULL,
                            time FLOAT NOT NULL,
                            event TEXT NOT NULL,
                            event_item INTEGER,
                            full INTEGER NOT NULL CHECK(full IN (0,1)),
                            items_in_storage INTEGER
                            )""")

    db_cu.execute("""CREATE TABLE agents (
                            agent INTEGER NOT NULL,
                            cell INTEGER NOT NULL,
                            ruleset INTEGER NOT NULL,
                            prio_tasks_started INTEGER,
                            normal_tasks_started INTEGER
                            )""")

    db_con.commit()
    return db_con, db_cu


def save_as_excel(sim_env):
    print("\nSave database tables as xlsx-files for further exploration")
    start_time = time.time()
    sim_env.db_cu.execute("SELECT name FROM sqlite_master WHERE type='table'")
    data = sim_env.db_cu.fetchall()
    for table in data:
        pd.read_sql_query("SELECT * from {table}".format(table=table[0]), sim_env.db_con).to_excel("data/{table}.xlsx".format(table=table[0]))
    print("Saving finished in %d seconds!" % (time.time() - start_time))


def close_connection(sim_env):
    sim_env.db_con.close()