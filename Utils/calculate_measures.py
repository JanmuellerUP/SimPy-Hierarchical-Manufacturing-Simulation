"""Copyright 2022 Jannis Müller/ janmueller@uni-potsdam.de

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""

import statistics
import pandas as pd
import numpy as np
from Order import Order, OrderType
from Utils.devisions import div_possible_zero


def machine_measures(sim_env, obj, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    result = {}
    event_counts = event_count_single_object("machine", obj, db_con)

    def setup_events():
        setup_events = event_counts[(event_counts["event"] == "setup_start")]["#events"]

        if setup_events.empty:
            return 0
        else:
            return setup_events.values[0].item()

    def setup_time():
        return boolean_times_single_object("machine", obj, "setup", db_con)

    def idle_time():
        return boolean_times_single_object("machine", obj, "idle", db_con)

    def pick_up_time():
        return boolean_times_single_object("machine", obj, "load_item", db_con)

    def processing_time():
        return boolean_times_single_object("machine", obj, "manufacturing", db_con)

    def processed_quantity():
        processed = event_counts[(event_counts["event"] == "production_start")]["#events"]

        if processed.empty:
            return 0
        else:
            return processed.values[0].item()

    def finished_quantity():
        finished = event_counts[(event_counts["event"] == "production_end")]["#events"]

        if finished.empty:
            return 0
        else:
            return finished.values[0].item()

    def time_to_repair():
        if failure_events():
            return boolean_times_single_object("machine", obj, "repair", db_con)
        else:
            return 0

    def failure_events():
        failures = event_counts[event_counts["event"] == "failure_start"]
        if not failures.empty:
            return failures["#events"].values[0].item()
        else:
            return 0

    def mean_time_between_failure():
        if failure_events():
            return (simulation_length - time_to_repair())/failure_events()
        else:
            return None

    def mean_processing_time_between_failure():
        if failure_events():
            return processing_time()/failure_events()
        else:
            return None

    def mean_time_to_repair():
        if failure_events():
            starts = event_times_single_object("machine", obj, "failure_start", db_con)
            ends = event_times_single_object("machine", obj, "failure_end", db_con)
            df = pd.merge(starts, ends, left_index=True, right_index=True)
            df["time_to_repair"] = df["time_y"] - df["time_x"]
            return df["time_to_repair"].mean().item()
        else:
            return None

    def availability():
        return ((simulation_length - time_to_repair())/simulation_length) * 100

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def order_measures(sim_env, obj, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    result = {}
    event_counts = event_count_single_object("item", obj, db_con)

    def completion_time():
        if obj.completed_at:
            return (obj.completed_at - obj.start).item()
        else:
            return None

    def tardiness():
        if obj.completed_at and obj.overdue:
            return (obj.completed_at - obj.due_to).item()
        else:
            return None

    def lateness():
        if obj.completed_at:
            return (obj.completed_at - obj.due_to).item()
        else:
            return None

    def transportation_time():
        return boolean_times_single_object("item", obj, "transportation", db_con).item()

    def average_transportation_time():
        return transportation_time()/event_counts[(event_counts["event"] == "transportation_start")]["#events"].values[0].item()

    def time_at_pos():
        return time_by_dimension("item", obj, "position", db_con)

    def time_at_pos_type():
        return time_by_dimension("item", obj, "position_type", db_con)

    def time_at_machines():
        df = time_at_pos_type()
        result = df[df["position_type"] == "Machine"]
        return result["length"].iloc[0].item()

    def time_in_interface_buffer():
        df = time_at_pos_type()
        result = df[df["position_type"] == "InterfaceBuffer"]
        return result["length"].iloc[0].item()

    def time_in_queue_buffer():
        df = time_at_pos_type()
        result = df[df["position_type"] == "QueueBuffer"]
        if not result.empty:
            return result["length"].iloc[0].item()
        else:
            return 0

    def production_time():
        return (boolean_times_single_object("item", obj, "processing", db_con) - wait_for_repair_time()).item()

    def wait_for_repair_time():
        result = boolean_times_single_object("item", obj, "wait_for_repair", db_con)
        if isinstance(result, int):
            return result
        else:
            return result.item()

    def time_in_cells():
        return time_by_dimension("item", obj, "cell", db_con)

    def different_cells_run_through():
        df = pd.read_sql_query("SELECT COUNT(DISTINCT cell) as 'amount' FROM item_events WHERE item={object}".format(object=id(obj)), db_con)
        return df["amount"].iloc[0].item()

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def agent_measures(sim_env, obj, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    result = {}
    event_counts = event_count_single_object("agent", obj, db_con)

    def moving_time():
        return boolean_times_single_object("agent", obj, "moving", db_con)

    def transportation_time():
        df = pd.read_sql_query(
            "SELECT time, moving, picked_up_item FROM agent_events WHERE agent={object} and picked_up_item NOT NULL".format(object=id(obj)), db_con)
        df = remove_events_without_changes(df, "moving")
        df["length"] = df["time"].shift(periods=-1, axis=0) - df["time"]
        result = df.groupby(["moving"], as_index=False)["length"].sum()

        if result.empty:
            return 0

        return result[result["moving"] == 1]["length"].values[0].item()

    def waiting_time():
        result = boolean_times_single_object("agent", obj, "waiting", db_con)
        if isinstance(result, int):
            return result
        else:
            return result.item()

    def idle_time():
        return simulation_length - task_time()

    def task_time():
        return boolean_times_single_object("agent", obj, "task", db_con)

    def started_tasks():
        started = event_counts[(event_counts["event"] == "start_task")]["#events"]

        if started.empty:
            return 0
        else:
            return started.values[0].item()

    def average_task_length():
        return div_possible_zero(task_time(), started_tasks())

    def time_at_pos():
        return time_by_dimension("agent", obj, "position", db_con)

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def buffer_measures(sim_env, obj, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    result = {}
    event_counts = event_count_single_object("buffer", obj, db_con)
    capacity = obj.STORAGE_CAPACITY

    def time_full():
        return boolean_times_single_object("buffer", obj, "full", db_con)

    def overfill_rate():
        return (time_full()/simulation_length)*100

    def mean_items_in_storage():
        df = time_by_dimension("buffer", obj, "items_in_storage", db_con)
        df["factor"] = df["length"] * df["items_in_storage"]
        return df["factor"].sum()/simulation_length

    def mean_time_in_storage():
        df = time_by_dimension("buffer", obj, "event_item", db_con)
        return df["length"].mean()

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def cell_measures(sim_env, obj, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    orders = pd.read_sql_query("SELECT DISTINCT item as item FROM item_events WHERE cell={}".format(id(obj)), db_con)["item"]
    result = {}

    def mean_time_in_cell():
        results = []

        for order_id in orders:
            df = time_by_dimension("item", order_id, "cell", db_con, object_as_id=True)
            results.append(df[df["cell"] == id(obj)]["length"].iloc[0])

        if len(results) == 0:
            return 0

        return statistics.mean(results)

    def mean_items_in_cell():
        return (len(orders) * mean_time_in_cell())/simulation_length

    def capacity():
        cap = obj.INPUT_BUFFER.STORAGE_CAPACITY + obj.OUTPUT_BUFFER.STORAGE_CAPACITY + obj.STORAGE.STORAGE_CAPACITY
        if obj.MACHINES:
            cap += len(obj.MACHINES) * 3
        if obj.INTERFACES_IN:
            cap += sum([interface.STORAGE_CAPACITY for interface in obj.INTERFACES_IN])
            cap += sum([interface.STORAGE_CAPACITY for interface in obj.INTERFACES_OUT])
        #cap += len(cell.AGENTS)
        return cap

    def storage_utilization():
        return (mean_items_in_cell()/capacity())*100

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def simulation_measures(sim_env, measures=[]):
    db_con = sim_env.db_con
    simulation_length = sim_env.SIMULATION_TIME_RANGE
    orders = [order for order in Order.instances if order.SIMULATION_ENVIRONMENT == sim_env]
    orders_completed = [order for order in orders if order.completed]
    result = {}

    def arrived_orders():
        return len(orders)

    def processed_quantity(alt_list=None):
        if alt_list:
            return len(alt_list)
        else:
            return len(orders_completed)

    def processed_in_time(alt_list=None):
        if alt_list:
            return len([order for order in alt_list if order.completed_at <= order.due_to])
        else:
            return len([order for order in orders_completed if order.completed_at <= order.due_to])

    def processed_in_time_rate(alt_list=None):
        return (processed_in_time(alt_list)/processed_quantity(alt_list))*100

    def in_time_rate_by_order_type():
        order_types = OrderType.instances
        result = []

        for o_type in order_types:
            alt_list = [order for order in orders_completed if order.type == o_type]
            result.append((o_type.name.decode("UTF-8"), processed_in_time_rate(alt_list)))

        return result

    def processed_by_order_type():
        order_types = OrderType.instances
        result = []

        for o_type in order_types:
            alt_list = [order for order in orders_completed if order.type == o_type]
            result.append((o_type.name.decode("UTF-8"), len(alt_list)))

        return result

    def mean_tardiness():
        results = []
        for order in orders_completed:
            results.append(order_measures(sim_env, order, measures=["tardiness"])["tardiness"])
        results = [0 if v is None else v for v in results]
        return statistics.mean(results)

    def mean_lateness():
        results = []
        for order in orders_completed:
            results.append(order_measures(sim_env, order, measures=["lateness"])["lateness"])
        results = [0 if v is None else v for v in results]
        return statistics.mean(results)

    for measure in measures:
        result[measure] = locals()[measure]()

    return result


def boolean_times_single_object(focus: str, object, measure: str, db_con, periods=1):
    """Calculate the absolute amount of time per boolean value in event_log for a specific object"""
    df = pd.read_sql_query("SELECT time, {measure} FROM {focus}_events WHERE {focus}={object}".format(measure=measure, focus=focus, object=id(object)), db_con)
    df = remove_events_without_changes(df, measure)
    if periods == 1:
        df["length"] = df["time"].shift(periods=-1, axis=0) - df["time"]
        result = df.groupby([measure], as_index=False)["length"].sum()
        if result[result[measure] == 1].empty:
            result = 0
        else:
            result = result[result[measure] == 1]["length"].values[0]
    else:
        df = add_time_periods(df, periods)
        df["length"] = df["time"].shift(periods=-1, axis=0) - df["time"]
        result = df.groupby(["time_bin", measure], as_index=False)["length"].sum()
    #result = result[result[measure] == 1].drop(measure, axis=1).reset_index(drop=True)
    return result


def time_by_dimension(focus: str, object, dimension: str, db_con, object_as_id=False):
    if object_as_id:
        object_id = object
    else:
        object_id = id(object)

    df = pd.read_sql_query(
        "SELECT time, {dimension} FROM {focus}_events WHERE {focus}={object}".format(dimension=dimension, focus=focus,
                                                                                   object=object_id), db_con)
    df = remove_events_without_changes(df, dimension)
    df["length"] = df["time"].shift(periods=-1, axis=0) - df["time"]
    result = df.groupby([dimension], as_index=False)["length"].sum()
    return result


def event_count_single_object(focus: str, object, db_con, periods=1):
    if periods == 1:
        result = pd.read_sql_query(
            "SELECT event, COUNT(time) as '#events' FROM {focus}_events WHERE {focus}={object} GROUP BY event".format(focus=focus,
                                                                                                object=id(object)), db_con)
    else:
        df = pd.read_sql_query(
            "SELECT time, event FROM {focus}_events WHERE {focus}={object}".format(focus=focus, object=id(object)), db_con)
        df = add_time_periods(df, periods=periods)
        del df["time"]
        result = df.groupby(["time_bin", "event"], as_index=False).size()
        result.rename(columns={'size': '#events'}, inplace=True)
    return result


def event_times_single_object(focus: str, object, event: str, db_con, periods=1):
    if periods == 1:
        result = pd.read_sql_query(
            "SELECT time FROM {focus}_events WHERE {focus}={object} AND event='{event}'".format(focus=focus, object=id(object), event=event), db_con)
        return result


def event_count_all_objects(focus: str, db_con, periods=1):
    if periods == 1:
        result = pd.read_sql_query(
            "SELECT event, COUNT(time) as '#events' FROM {focus}_events GROUP BY event".format(focus=focus), db_con)
    else:
        df = pd.read_sql_query(
            "SELECT time, event FROM {focus}_events".format(focus=focus), db_con)
        df = add_time_periods(df, periods=periods)
        del df["time"]
        result = df.groupby(["time_bin", "event"], as_index=False).size()
        result.rename(columns={'size': '#events'}, inplace=True)
    return result


def add_time_periods(df, periods: int):
    start = df["time"].min()
    end = df["time"].max()
    period_length = (end - start)/periods
    timestamps = [start + i * period_length for i in range(1, periods)]
    concat_data = pd.DataFrame({"time": timestamps, "marker": [True for i in range(1, periods)]})
    df = pd.concat([df, concat_data], ignore_index=True).sort_values("time", axis=0).reset_index(drop=True)
    for column in df.columns:
        if column != "time" and column != "marker":
            df[column] = np.where(df["marker"] == True, df[column].shift(periods=1, axis=0), df[column])

    del df["marker"]
    timestamps = timestamps + [start, end]
    df["time_bin"] = pd.cut(df["time"], sorted(timestamps), right=False)
    return df


def remove_events_without_changes(df: pd.DataFrame, column: str):

    if df.empty:
        return df

    last_row = df.iloc[-1]
    df["to_drop"] = df[column].shift(periods=1, axis=0) == df[column]
    df = df.drop(df[df["to_drop"]].index)
    del df["to_drop"]
    df = df.append(last_row)
    return df
