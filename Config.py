configuration = {
    "SETUP_FILE": "medium_testsetup.txt",
    "SIMULATION_RANGE": 2500,
    "SEED_MACHINE_INTERRUPTIONS": 29378374,
    "MACHINE_FAILURE_RATE": 20,
    "FAILURE_MINIMAL_LENGTH": 20,
    "FAILURE_MAXIMAL_LENGTH": 50,
    "SEED_INCOMING_ORDERS": 10278347,
    "NUMBER_OF_ORDERS": 10,
    "ORDER_MINIMAL_LENGTH": 200,
    "ORDER_MAXIMAL_LENGTH": 300,
    "SPREAD_ORDER_COMPLEXITY": 0.1,
    "AGENT_SPEED": 1,
    "AGENT_LONGEST_WAITING_TIME": 10,
    "MACHINE_SETUP_TIME": 5,
    "DB_IN_MEMORY": True,
    "TIME_FOR_ITEM_PICK_UP": 0.1,
    "TIME_FOR_ITEM_STORE": 0.1,

    "DISTANCES": {
        "BASE_HEIGHT": 1,
        "BASE_WIDTH": 1,
        "INTERFACE_DISTANCE": 1,
        "DISTANCE_BETWEEN_CELLS": 0.5,
        "MULTIPLICATOR_UPPER_CELL": 1, # Derzeit keine extremen Werte möglich!
        "MULTIPLICATOR_LOWER_CELL": 1
    },

    "SEED_GENERATOR": {
        "SEED_GEN_M_INTERRUPTIONS": 2928337,
        "SEED_GEN_INC_ORDERS": 4848373
    }
}

evaluation_measures = {
    "machine": {
        "setup_events": True,
        "setup_time": True,
        "idle_time": True,
        "pick_up_time": True,
        "processing_time": True,
        "processed_quantity": True,
        "finished_quantity": True,
        "time_to_repair": True,
        "failure_events": True,
        "mean_time_between_failure": True,
        "mean_processing_time_between_failure": True,
        "mean_time_to_repair": True,
        "availability": True
    },

    "order": {
        "completion_time": True,
        "tardiness": True,
        "lateness": True,
        "transportation_time": True,
        "average_transportation_time": True,
        "time_at_pos": False,
        "time_at_pos_type": True,
        "time_at_machines": True,
        "time_in_interface_buffer": True,
        "time_in_queue_buffer": True,
        "production_time": True,
        "wait_for_repair_time": True,
        "time_in_cells": True,
        "different_cells_run_through": True
    },

    "agent": {
        "moving_time": True,
        "transportation_time": True,
        "waiting_time": True,
        "idle_time": True,
        "task_time": True,
        "started_prio_tasks": True,
        "started_normal_tasks": True,
        "average_task_length": True,
        "time_at_pos": True
    },

    "buffer": {
        "time_full": True,
        "overfill_rate": True,
        "mean_items_in_storage": True,
        "mean_time_in_storage": True
    },

    "cell": {
        "mean_time_in_cell": True,
        "mean_items_in_cell": True,
        "capacity": True,
        "storage_utilization": True
    },

    "simulation": {
        "arrived_orders": True,
        "processed_quantity": True,
        "processed_in_time": True,
        "processed_in_time_rate": True,
        "in_time_rate_by_order_type": True,
        "processed_by_order_type": True,
        "mean_tardiness": True,
        "mean_lateness": True
    }
}