import Cell
from Order import load_order_types, order_arrivals
import time
from Ruleset import load_rulesets
from Utils import calculate_measures, database
from Utils.init_simulation_env import *


class SimulationEnvironment:

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

        self.db_con, self.db_cu = database.set_up_db(self)


def simulation(config: dict, show_progress=False):
    """Main function of the simulation: Create project setup and run simulation on it"""
    load_order_types()
    load_rulesets()
    env = simpy.Environment()

    if yes_no_question("Do you want to load an existing cell setup? [Y/N]\n"):
        setup_json = load_setup_from_config(config)
    else:
        setup_json = new_cell_setup(config)

    simulation_environment = set_up_sim_env(config, env, setup_json)
    set_env_in_cells(simulation_environment)

    print('----------------------------------------------------------------------------')
    start_time = time.time()

    env.process(order_arrivals(env, simulation_environment, config))

    if show_progress:
        env.process(show_progress_func(env, simulation_environment))

    env.run(until=simulation_environment.SIMULATION_TIME_RANGE)

    print('\nSimulation finished in %d seconds!' % (time.time() - start_time))

    add_final_events()

    #check_environment(simulation_environment)

    print("\nCalculate measures for each machine")

    for machine in Cell.Machine.Machine.instances:
        print(calculate_measures.machine_measures(simulation_environment, machine, ["setup_time", "setup_events", "idle_time", "processing_time", "processed_quantity", "failure_events", "mean_time_between_failure", "mean_time_to_repair", "mean_processing_time_between_failure", "availability"]))

    print("\nCalculate measures for each cell")

    for cell in Cell.Cell.instances:
        print(calculate_measures.cell_measures(simulation_environment, cell,
                                                  ["mean_items_in_cell", "mean_time_in_cell", "storage_utilization"]))

    print("\nCalculate global measures")

    print(calculate_measures.global_measures(simulation_environment, ["processed_in_time_rate", "mean_tardiness", "mean_lateness", "in_time_rate_by_order_type", "processed_by_order_type"]))

    database.save_as_excel(simulation_environment)
    database.close_connection(simulation_environment)


def set_up_sim_env(config: dict, env: simpy.Environment, setup):
    main_components = generator_from_json(setup, config, env)
    main_components['main_cell'].INPUT_BUFFER = main_components['main_input']
    main_components['main_cell'].POSSIBLE_POSITIONS.append(main_components['main_cell'].INPUT_BUFFER)
    main_components['main_cell'].OUTPUT_BUFFER = main_components['main_output']
    main_components['main_cell'].POSSIBLE_POSITIONS.append(main_components['main_cell'].OUTPUT_BUFFER)
    init_cells_responsible_agents()
    set_parents_in_tree(main_components['main_cell'], None)
    tree = get_tree_levels(main_components['main_cell'])
    set_tree_levels(tree)
    calculate_distances_tree(config, tree)
    init_performable_tasks()
    set_agents_positions(main_components['main_cell'])
    return SimulationEnvironment(env, config, main_components['main_cell'])