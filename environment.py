import Cell
from Order import load_order_types, order_arrivals, Order
import time
from Ruleset import load_rulesets
from Utils import calculate_measures, database, check_config
from Utils.init_simulation_env import *
from Utils.save_results import SimulationResults
from Utils.progress_func import show_progress_func
import numpy as np
import json
import time_tracker


class SimulationEnvironment:
    instances = []

    def __init__(self, env: simpy.Environment, config: dict, main_cell: Cell.DistributionCell):
        self.env = env

        # Attributes and Settings
        self.CONFIG_FILE = config
        self.SIMULATION_TIME_RANGE = config.get("SIMULATION_RANGE", 1000)
        self.SEED_MACHINE_INTERRUPTIONS = config.get("SEED_MACHINE_INTERRUPTIONS", 464638465)
        self.SEED_INCOMING_ORDERS = config.get("SEED_INCOMING_ORDERS", 37346463)
        self.NUMBER_OF_ORDERS = config.get("NUMBER_OF_ORDERS", 0)
        self.MIN_ORDER_LENGTH = config.get("ORDER_MINIMAL_LENGTH")
        self.MAX_ORDER_LENGTH = config.get("ORDER_MAXIMAL_LENGTH")
        self.ORDER_COMPLEXITY_SPREAD = config.get("SPREAD_ORDER_COMPLEXITY", 0)
        self.DB_IN_MEMORY = config.get("DB_IN_MEMORY")

        self.main_cell = main_cell
        self.cells = []

        self.result = None

        self.db_con, self.db_cu = database.set_up_db(self)
        self.__class__.instances.append(self)


def set_up_sim_env(config: dict, env: simpy.Environment, setup):
    # Generate objects from setup json file
    cells = generator_from_setup(setup, config, env)

    # Calculate the shortest distances between objects of each cell
    # calculate_distances(config, cells)

    # Create new simulation environment and set this to all cells
    main_cell = cells[np.isnan(cells["Parent"])]["cell_obj"].item()

    sim_env = SimulationEnvironment(env, config, main_cell)

    set_env_in_cells(sim_env, cells["cell_obj"])

    return sim_env


def simulation(config: dict, eval_measures: dict, runs=1, show_progress=False, save_log=True,
               change_interruptions=True, change_incoming_orders=True, train=False):
    """Main function of the simulation: Create project setup and run simulation on it"""
    check_config.check_configuration_file(config)
    load_order_types()
    load_rulesets()
    database.clear_files()

    if change_interruptions:
        np.random.seed(seed=config["SEED_GENERATOR"]["SEED_GEN_M_INTERRUPTIONS"])
        interruption_seeds = np.random.randint(99999999, size=runs)
    else:
        interruption_seeds = np.full([runs, ], config["SEED_MACHINE_INTERRUPTIONS"])

    if change_incoming_orders:
        np.random.seed(config["SEED_GENERATOR"]["SEED_GEN_INC_ORDERS"])
        order_seeds = np.random.randint(99999999, size=runs)
    else:
        order_seeds = np.full([runs, ], config["SEED_INCOMING_ORDERS"])

    # Switch between new setup and loading an existing one
    if yes_no_question("Do you want to load an existing cell setup? [Y/N]\n"):
        configuration = load_setup_from_config(config)
    else:
        configuration = new_cell_setup()

    # Run the set amount of simulations
    for sim_count in range(runs):
        config["SEED_MACHINE_INTERUPTIONS"] = interruption_seeds[sim_count].item()
        config["SEED_INCOMING_ORDERS"] = order_seeds[sim_count].item()
        env = simpy.Environment()

        simulation_environment = set_up_sim_env(config, env, configuration)

        print('----------------------------------------------------------------------------')
        start_time = time.time()

        env.process(order_arrivals(env, simulation_environment, config))

        if show_progress:
            env.process(show_progress_func(env, simulation_environment))

        env.run(until=config["SIMULATION_RANGE"])

        print('\nSimulation %d finished in %d seconds!' % (sim_count + 1, time.time() - start_time))

        print("Time Tracker:\nTime for state calculations:", time_tracker.time_state_calc, "\nTime for destination calculations:", time_tracker.time_destination_calc)
        print("\nState Calculations:\nTime for occupancy:", time_tracker.time_occupancy_calc, "\nTime for order attributes:", time_tracker.time_order_attr_calc, "\nTime for pos attributes:", time_tracker.time_pos_attr_calc)

        database.add_final_events()

        sim_run_evaluation(simulation_environment, eval_measures)

        if save_log:
            database.save_as_excel(simulation_environment, sim_count + 1)
        database.close_connection(simulation_environment)
        release_objects()

    schema = json.loads("""
                            {"simulation_runs":[]}
                            """)

    for run in SimulationResults.instances:
        schema["simulation_runs"].append(run.results)

    with open('result/last_runs.json', 'w') as f:
        json.dump(schema, f, indent=4, ensure_ascii=False)


def sim_run_evaluation(sim_env, eval_measures):
    print("\nCalculate the chosen measures for the finished simulation run!")
    start_time = time.time()

    functionList = {"machine": calculate_measures.machine_measures,
                    "buffer": calculate_measures.buffer_measures,
                    "agent": calculate_measures.agent_measures,
                    "cell": calculate_measures.cell_measures,
                    "order": calculate_measures.order_measures,
                    "simulation": calculate_measures.simulation_measures
                    }

    objectList = {  "machine": Cell.Machine.Machine.instances,
                    "buffer": Cell.Buffer.instances,
                    "agent": Cell.ManufacturingAgent.instances,
                    "cell": Cell.Cell.instances,
                    "order": Order.instances
                    }

    for focus in eval_measures.keys():
        measures = [key for key, value in eval_measures[focus].items() if value == True]
        if focus == "simulation":
            parameters = {'sim_env': sim_env, 'measures': measures}
            sim_env.result = functionList[focus](**parameters)
        else:
            objects = objectList[focus]
            for obj_to_check in objects:
                parameters = {'sim_env': sim_env, 'obj': obj_to_check, 'measures': measures}
                obj_to_check.result = functionList[focus](**parameters)

    result = SimulationResults(sim_env)

    print("\nCalculation finished in %d seconds!" % (time.time() - start_time))


def release_objects():
    SimulationEnvironment.instances.clear()
    Cell.Cell.instances.clear()
    Cell.Buffer.instances.clear()
    Cell.ManufacturingAgent.instances.clear()
    Cell.Machine.Machine.instances.clear()
    Order.instances.clear()
    Order.finished_instances.clear()

