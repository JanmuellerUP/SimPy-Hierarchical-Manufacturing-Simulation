import numpy as np
import Cell
from Order import Order, ProcessingStep
import simpy
import os
from treelib import Tree
import json
from Ruleset import RuleSet
from Utils.text_input import _input, yes_no_question
import threading


def add_final_events():
    for buffer in Cell.InterfaceBuffer.instances:
        buffer.end_event()
    for buffer in Cell.QueueBuffer.instances:
        buffer.end_event()
    for order in Order.instances:
        order.end_event()
    for agent in Cell.ManufacturingAgent.instances:
        agent.end_event()
    for machine in Cell.Machine.Machine.instances:
        machine.end_event()


def show_progress_func(env, sim_env):
    """Print out the current progress while simulating"""
    periods = 10
    period_length = sim_env.SIMULATION_TIME_RANGE/periods
    counter = 1
    while counter <= periods:
        yield env.timeout(period_length)
        print("Finished", (100/periods)*(counter), "% of the simulation!")
        counter += 1


def new_cell_setup(config):
    """Create a new Setup from config. User can decide how the setup should look like
    and save it at the end of the process."""
    nodes_id = 0
    setup_tree = Tree()

    def initialize_tree():
        nonlocal nodes_id
        setup_tree.create_node("Main_Interface", nodes_id, data={"type": "Interface", "capacity": _input("How many slots should the Interface of the main cell have?\n", int)})
        nodes_id += 1
        setup_tree.create_node("Main_Cell", nodes_id, parent=0, data={"type": "Cell"})
        nodes_id += 1
        setup_tree.create_node("Storage", nodes_id, parent=1, data={"type": "Storage", "capacity": _input("How many slots should the storage buffer of the main cell have?\n", int)})
        nodes_id += 1
        for agent in range(0, _input("How many agents should the main cell have?\n", int)):
            show_possible_rulesets()
            ruleset = get_agent_ruleset(agent + 1)
            setup_tree.create_node("Agent", nodes_id, parent=1, data={"type": "Agent", "ruleset": ruleset})
            nodes_id += 1

    def create_new_cell(parent: int, in_capacity: int, storage_capacity: int, agents: list, machines=0):
        nonlocal nodes_id
        setup_tree.create_node("Interface", nodes_id, parent=parent, data={"type": "Interface", "capacity": in_capacity})
        nodes_id += 1
        new_node_id = nodes_id
        setup_tree.create_node("Cell", nodes_id, parent=nodes_id-1, data={"type": "Cell"})
        nodes_id += 1
        setup_tree.create_node("Storage", nodes_id, parent=new_node_id, data={"type": "Storage", "capacity": storage_capacity})
        nodes_id += 1
        for agent_ruleset in agents:
            setup_tree.create_node("Agent", nodes_id, parent=new_node_id, data={"type": "Agent", "ruleset": agent_ruleset})
            nodes_id += 1
        for machine_num in range(machines):
            print("Nutzung der Tasks")
            print("\nAvailable machine tasks:")
            for task in ProcessingStep.instances:
                print("ID: %d TYPE: %s" %(task.id, task.name))
            print("\nCreate new machine:")
            setup_tree.create_node("Machine", nodes_id, parent=new_node_id, data={"type": "Machine", "task_id": _input("Which task should the machine perform? (ID)\n", int)})
            nodes_id += 1

    def show_configuration():
        setup_tree.show(idhidden=False)

    def show_configuration_cells():
        setup_tree.show(idhidden=False, filter=lambda x:x.data["type"] in {'Cell', 'Interface'})

    def save_configuration():
        while 1:
            try:
                name = _input("Please choose a name for your setup:\n") + '.txt'
                name.replace(" ", "_")
                setup_formatted = setup_tree.to_json(with_data=True)
                with open('./setups/' + name, 'w') as outfile:
                    json.dump(setup_formatted, outfile)
                break
            except:
                print("\nAn Error occured: Unable to save the configuration. Please try again!")
                pass

    def get_parent():
        while 1:
            try:
                parent = _input("Which cell should be the parent of the new cell? (ID)\n", int)
                if setup_tree.get_node(parent).data["type"] != "Cell": raise Exception
                return parent
            except:
                print("The chosen cell can not be parent of this cell!")
                pass

    def get_machines(parent):
        machines = _input("How many machines should the cell have?\n", int)
        for node in setup_tree.children(parent):
            if node.data['type'] == 'Machine':
                setup_tree.remove_node(node.identifier)
        if machines >= 0:
            return machines
        else: raise AssertionError("Number of machines can not be negative!")

    def get_agent_ruleset(agent_num: int):
        while 1:
            try:
                ruleset_id = _input("\nPlease choose a ruleset (ID) for Agent " + str(agent_num) + ":\n", int)
                if len([ruleset for ruleset in RuleSet.instances if ruleset.id == ruleset_id]) == 0: raise Exception
                return ruleset_id
            except:
                print("The chosen number can not be matched with any of the useable rulesets!")
                pass

    def show_possible_rulesets():
        """Print out a list of all useable rulesets and its IDs"""
        print("\nUseable Rulesets (ID / Name):")
        for ruleset in RuleSet.instances:
            print(ruleset.id, "/", ruleset.name)

    print("Create a new setup...\nInitial setup:\n")
    initialize_tree()
    show_configuration()
    while yes_no_question("\nDo you want to add another Cell? [Y/N]\n"):
        parent = get_parent()
        machines = get_machines(parent)
        agents = _input("How many agents should the cell have?\n", int)
        agent_rulesets = []
        show_possible_rulesets()
        for agent in range(0, agents):
            ruleset_id = get_agent_ruleset(agent + 1)
            agent_rulesets.append(ruleset_id)
        storage_slots = _input("\nHow many slots should the storage of the cell have?\n", int)
        interface_slots = _input("How many slots should the Interface of the cell to its parent have?\n", int)
        create_new_cell(parent, interface_slots, storage_slots, agent_rulesets, machines)
        print("New cell created sucessfully.\n\nCurrent setup:\n")
        show_configuration()

    if yes_no_question("\nSetup finished!\nDo you want to save your current setup? [Y/N]\n"):
        save_configuration()
        print("File saved!")

    return setup_tree.to_json(with_data=True)


def load_setup_process():
    """Load an existing setup by printing all available setups. Choose one with console input."""
    myPath = "./setups/"
    if len([f for f in os.listdir(myPath) if f.endswith('.txt') and os.path.isfile(os.path.join(myPath, f))]) > 0:
        while 1:
            try:
                print("\nAvailable Setups:")
                for file in (f for f in os.listdir(myPath) if f.endswith('.txt')):
                    print(file.replace(".txt", ""))
                name = _input("\nWhich setup do you want to load?\n") + '.txt'
                with open('./setups/' + name) as infile:
                    configuration = json.load(infile)
                return configuration
            except:
                print("\nAn Error occured: Unable to load the configuration. Please try again!")
                pass
    else:
        print("\nThere is no saved setup. Please create a new setup.\n")


def load_setup_from_config(config):
    """Load an existing setup file as named in config"""
    file_name = config["SETUP_FILE"]
    if file_name == "":
        setup = load_setup_process()
        return setup
    print("Loading setup file from configuration file...")
    with open('./setups/' + file_name) as infile:
        setup = json.load(infile)
    return setup


def generator_from_json(setup, config, env: simpy.Environment):
    """Create instances of setup as json and build first connections between the objects"""
    setup_json = json.loads(setup)
    list_cells = []
    list_agents = []

    def recursive(d):
        if 'children' in d.keys():
            child_objects = []
            for child in d['children']:
                child_objects.append(recursive(child))
            return child_objects
        elif 'Main_Cell' in d.keys():
            objects = recursive(d['Main_Cell'])
            agents = [agent for agent in objects if isinstance(agent, Cell.ManufacturingAgent)]
            storage = next(object for object in objects if isinstance(object, Cell.QueueBuffer))
            if any(isinstance(x, Cell.Machine.Machine) for x in objects):
                machines = [machine for machine in objects if isinstance(machine, Cell.Machine.Machine)]
                new_cell = Cell.ManufacturingCell(machines, env, agents, storage)
                return new_cell
            else:
                interfaces = [item for item in objects if isinstance(item, dict)]
                child_list = []
                for childs in interfaces:
                    child = childs["child_cell"]
                    child.INPUT_BUFFER = childs["in_buffer"]
                    child.POSSIBLE_POSITIONS.append(child.INPUT_BUFFER)
                    child.OUTPUT_BUFFER = childs["out_buffer"]
                    child.POSSIBLE_POSITIONS.append(child.OUTPUT_BUFFER)
                    child_list.append(child)
                new_cell = Cell.DistributionCell(child_list, env, agents, storage)
                return new_cell
        elif 'Cell' in d.keys():
            objects = recursive(d['Cell'])
            agents = [agent for agent in objects if isinstance(agent, Cell.ManufacturingAgent)]
            storage = next(object for object in objects if isinstance(object, Cell.QueueBuffer))
            if any(isinstance(x, Cell.Machine.Machine) for x in objects):
                machines = [machine for machine in objects if isinstance(machine, Cell.Machine.Machine)]
                new_cell = Cell.ManufacturingCell(machines, env, agents, storage)
                return new_cell
            else:
                interfaces = [item for item in objects if isinstance(item, dict)]
                child_list = []
                for childs in interfaces:
                    child = childs["child_cell"]
                    child.INPUT_BUFFER = childs["in_buffer"]
                    child.POSSIBLE_POSITIONS.append(child.INPUT_BUFFER)
                    child.OUTPUT_BUFFER = childs["out_buffer"]
                    child.POSSIBLE_POSITIONS.append(child.OUTPUT_BUFFER)
                    child_list.append(child)
                new_cell = Cell.DistributionCell(child_list, env, agents, storage)
                return new_cell
        elif 'Main_Interface' in d.keys():
            size = d['Main_Interface']['data']['capacity']
            interface_in = Cell.InterfaceBuffer(config, env, size)
            interface_out = Cell.InterfaceBuffer(config, env, size)
            main_cell = recursive(d['Main_Interface'])
            return {"main_cell": main_cell[0], "main_input": interface_in, "main_output": interface_out}
        elif 'Interface' in d.keys():
            size = d['Interface']['data']['capacity']
            interface_in = Cell.InterfaceBuffer(config, env, size)
            interface_out = Cell.InterfaceBuffer(config, env, size)
            child_cell = recursive(d['Interface'])
            return {"in_buffer": interface_in, "out_buffer": interface_out, "child_cell": child_cell[0]}
        elif 'Machine' in d.keys():
            machine = Cell.Machine.Machine(env, config, d['Machine']['data']['task_id'])
            return machine
        elif 'Storage' in d.keys():
            storage = Cell.QueueBuffer(config, env, d['Storage']['data']['capacity'])
            return storage
        elif 'Agent' in d.keys():
            agent = Cell.ManufacturingAgent(env, config, None, ruleset_id=d['Agent']['data']['ruleset'])
            return agent
        else:
            return

    return recursive(setup_json)


def set_parents_in_tree(cell: Cell.Cell, parent, first_iteration=True):
    """Set parent cells for each child cells in the tree. Input has to be the main (root) cell"""
    cell.PARENT = parent
    if first_iteration:
        cell.OUTPUT_BUFFER.upper_cell = None
        cell.INPUT_BUFFER.upper_cell = None
        cell.OUTPUT_BUFFER.lower_cell = cell
        cell.INPUT_BUFFER.lower_cell = cell
    if isinstance(cell, Cell.DistributionCell):
        for child in cell.CHILDS:
            child.INPUT_BUFFER.lower_cell = child
            child.INPUT_BUFFER.upper_cell = cell
            child.OUTPUT_BUFFER.lower_cell = child
            child.OUTPUT_BUFFER.upper_cell = cell
            set_parents_in_tree(child, cell, first_iteration=False)


def get_tree_levels(main_cell):
    """Group cells of tree by tree levels. Leaf Cells begin with index 0"""
    tree = []

    def recursive_levels(cells: list):
        nonlocal tree
        next_level = []
        for cell in cells:
            if isinstance(cell, Cell.DistributionCell):
                for child in cell.CHILDS:
                    next_level.append(child)
        if next_level:
            tree.append(next_level)
            recursive_levels(next_level)
        else: return

    tree.append([main_cell])
    recursive_levels([main_cell])
    tree.reverse()
    return tree


def finish_setup(tree):
    """Set the tree level of each cell in the tree, init agents and performable tasks"""
    level = 0
    for cells_of_level in tree:
        for cell in cells_of_level:
            cell.LEVEL = level
            cell.init_responsible_agents()
            cell.init_performable_tasks()
        level += 1


def calculate_distances_tree(config, tree):
    """Take tree and calculate the width and height of each cell based on config and tree level"""
    level = 0
    dist = config['DISTANCES']
    base_width = dist['BASE_WIDTH']
    base_height = dist['BASE_HEIGHT']
    interface_distance = dist['INTERFACE_DISTANCE']
    distance_between_cells = dist['DISTANCE_BETWEEN_CELLS']
    multiplicator_upper = dist['MULTIPLICATOR_UPPER_CELL']
    multiplicator_lower = dist['MULTIPLICATOR_LOWER_CELL']

    def calculate_positions_in_cell(cell: Cell):
        if level == 0:
            cell.HEIGHT = multiplicator_upper * (base_height + interface_distance) + multiplicator_lower * (base_height + interface_distance)
            cell.WIDTH = len(cell.MACHINES) * base_width
            input_pos = (cell.WIDTH/2, 0)
            output_pos = (cell.WIDTH/2, cell.HEIGHT)
            storage_pos = (0, multiplicator_upper * (base_height + interface_distance))
            machine_positions = [(0 + (i+1)*base_width, multiplicator_upper * (base_height + interface_distance)) for i in range(0, len(cell.MACHINES))]
            junction_positions = [(i, multiplicator_upper * interface_distance) for i in np.arange(0, cell.WIDTH+base_width, step=base_width)]
            junction_positions += [(i, cell.HEIGHT - (multiplicator_lower * interface_distance)) for i in np.arange(0, cell.WIDTH+base_width, step=base_width)]
            cell.calculate_distances(input_pos, output_pos, storage_pos, junction_positions, machines=machine_positions)

        else:
            cell.HEIGHT = multiplicator_upper * (base_height + interface_distance) + multiplicator_lower * (base_height + interface_distance) + max([c.HEIGHT for c in cell.CHILDS])
            cell.WIDTH = len(cell.CHILDS)*distance_between_cells + sum([c.WIDTH for c in cell.CHILDS])
            input_pos = (cell.WIDTH/2, 0)
            output_pos = (cell.WIDTH/2, cell.HEIGHT)
            x_position = distance_between_cells
            interface_positions_in = []
            interface_positions_out = []
            junction_positions = []
            for child in cell.CHILDS:
                interface_position_x = x_position + (child.WIDTH/2)
                interface_positions_in.append((interface_position_x, multiplicator_upper * (base_height + interface_distance)))
                interface_positions_out.append((interface_position_x, cell.HEIGHT - multiplicator_upper * (base_height + interface_distance)))
                x_position += child.WIDTH
                if x_position + (distance_between_cells/2) < cell.WIDTH:
                    junction_positions.append((x_position + (distance_between_cells/2), (multiplicator_upper * interface_distance)))
                    junction_positions.append((x_position + (distance_between_cells / 2), cell.HEIGHT - (multiplicator_lower * interface_distance)))
                x_position += distance_between_cells
            junction_positions += [(i, multiplicator_upper * interface_distance) for i in [0] + [x for (x, y) in interface_positions_in]]
            junction_positions += [(i, cell.HEIGHT - (multiplicator_lower * interface_distance)) for i in [0] + [x for (x, y) in interface_positions_in]]
            x_in, y_in = interface_positions_in[0]
            x_out, y_out = interface_positions_out[0]
            storage_pos = (0, multiplicator_upper * (base_height + interface_distance) + (y_out-y_in)/2)
            cell.calculate_distances(input_pos, output_pos, storage_pos, junction_positions, interface_positions_in, interface_positions_out)

    for cells_of_level in tree:
        for cell in cells_of_level:
            calculate_positions_in_cell(cell)
        level += 1


def set_env_in_cells(simulation_env):
    """Set simulation environment of each cell and its components in the environment"""
    simulation_env.main_cell.SIMULATION_ENVIRONMENT = simulation_env
    set_env_in_components(simulation_env, simulation_env.main_cell)

    def recursive(cell):
        cell.SIMULATION_ENVIRONMENT = simulation_env
        set_env_in_components(simulation_env, cell)
        simulation_env.cells.append(cell)
        if isinstance(cell, Cell.DistributionCell):
            for child in cell.CHILDS:
                recursive(child)

    recursive(simulation_env.main_cell)


def set_env_in_components(sim_env, cell):
    cell.INPUT_BUFFER.SIMULATION_ENVIRONMENT = sim_env
    cell.OUTPUT_BUFFER.SIMULATION_ENVIRONMENT = sim_env
    cell.STORAGE.SIMULATION_ENVIRONMENT = sim_env

    lock = threading.Lock()
    for agent in cell.AGENTS:
        agent.SIMULATION_ENVIRONMENT = sim_env
        agent.lock = lock
    for machine in cell.MACHINES:
        machine.SIMULATION_ENVIRONMENT = sim_env
        machine.CELL = cell
    for interface in cell.INTERFACES_IN:
        interface.SIMULATION_ENVIRONMENT = sim_env
        interface.CELL = cell
    for interface in cell.INTERFACES_OUT:
        interface.SIMULATION_ENVIRONMENT = sim_env
        interface.CELL = cell

