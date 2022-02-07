def check_configuration_file(config: dict):

    limitations = {
        "SETUP_FILE":{
            "data_type": str
        },
        "SIMULATION_RANGE": {
            "data_type": float,
            "minimum": 100
        },
        "SEED_MACHINE_INTERRUPTIONS": {
            "data_type": int,
            "minimum": 0
        },
        "MACHINE_FAILURE_RATE": {
            "data_type": int,
            "minimum": 0,
            "maximum": 100
        },
        "FAILURE_MINIMAL_LENGTH": {
            "data_type": float,
            "minimum": 1,
            "lower_than": "SIMULATION_RANGE"
        },
        "FAILURE_MAXIMAL_LENGTH": {
            "data_type": float,
            "greater_than": "FAILURE_MINIMAL_LENGTH",
            "lower_than": "SIMULATION_RANGE"
        },
        "SEED_INCOMING_ORDERS": {
            "data_type": int,
            "minimum": 0
        },
        "NUMBER_OF_ORDERS": {
            "data_type": int,
            "minimum": 1,
            "maximum": 1000
        },
        "ORDER_MINIMAL_LENGTH": {
            "data_type": float,
            "minimum": 1,
            "lower_than": "ORDER_MAXIMAL_LENGTH"
        },
        "ORDER_MAXIMAL_LENGTH": {
            "data_type": float,
            "lower_than": "SIMULATION_RANGE",
            "greater_than": "ORDER_MINIMAL_LENGTH"
        },
        "SPREAD_ORDER_COMPLEXITY": {
            "data_type": float,
            "minimum": 0,
            "maximum": 1
        },
        "AGENT_SPEED": {
            "data_type": float,
            "minimum": 1
        },
        "AGENT_LONGEST_WAITING_TIME": {
            "data_type": float,
            "minimum": 1,
        },
        "MACHINE_SETUP_TIME": {
            "data_type": float,
            "minimum": 1,
            "lower_than": "SIMULATION_RANGE"
        },
        "DB_IN_MEMORY": {
            "data_type": bool
        },
        "TIME_FOR_ITEM_PICK_UP": {
            "data_type": float,
            "minimum": 0.001,
            "lower_than": "SIMULATION_RANGE"
        },
        "TIME_FOR_ITEM_STORE": {
            "data_type": float,
            "minimum": 0.001,
            "lower_than": "SIMULATION_RANGE"
        },
        "BASE_HEIGHT": {
            "data_type": float,
            "minimum": 0.001,
        },
        "BASE_WIDTH": {
            "data_type": float,
            "minimum": 0.001
        },
        "INTERFACE_DISTANCE": {
            "data_type": float,
            "minimum": 0
        },
        "DISTANCE_BETWEEN_CELLS": {
            "data_type": float,
            "minimum": 0.1
        },
        "MULTIPLICATOR_UPPER_CELL": {
            "data_type": float,
            "minimum": 0.5,
            "maximum": 1.5
        },
        "MULTIPLICATOR_LOWER_CELL": {
            "data_type": float,
            "minimum": 0.5,
            "maximum": 1.5
        },
        "SEED_GEN_M_INTERRUPTIONS": {
            "data_type": int
        },
        "SEED_GEN_INC_ORDERS": {
            "data_type": int
        }
    }

    def data_type(value, limit_v):
        if limit_v == float and type(value) == int:
            return True
        else:
            return type(value) == limit_v

    def minimum(value, limit_v):
        return value >= limit_v

    def maximum(value, limit_v):
        return value <= limit_v

    def lower_than(value, limit_v):
        return value < config[limit_v]

    def greater_than(value, limit_v):
        return value > config[limit_v]

    functionList = {'data_type': data_type,
                    "minimum": minimum,
                    "maximum": maximum,
                    "lower_than": lower_than,
                    "greater_than": greater_than}

    def check_config_values(con: dict):
        for key, value in con.items():
            if isinstance(value, dict):
                check_config_values(value)
            else:
                limits = limitations[key]
                for limit_k, limit_v in limits.items():
                    parameters = {'value': value, 'limit_v': limit_v}
                    permitted = functionList[limit_k](**parameters)
                    if not permitted:
                        raise ValueError("The chosen configuration value for {name} is not permitted! It violates the {rule} : {value}".format(name=key, rule=limit_k, value=limit_v))

    check_config_values(config)