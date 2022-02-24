# -*- coding: utf-8 -*-
import numpy as np
import Cell
from Order import ProcessingStep
import simpy
import os
from Ruleset import RuleSet
from Utils.text_input import _input, yes_no_question
import threading
import pandas as pd
from copy import copy
import ast


def new_cell_setup():
    """Create a new Setup from config. User can decide how the setup should look like
    and save it at the end of the process."""

    def save_configuration(setup: pd.DataFrame):
        del setup["Cell Title"]
        while 1:
            try:
                name = _input("Please choose a name for your setup:\n") + '.txt'
                name.replace(" ", "_")
                with open('./setups/' + name, 'w') as outfile:
                    setup.to_csv(outfile, sep=";")
                break
            except:
                print("\nAn Error occured: Unable to save the configuration. Please try again!")
                pass

    def normalize_setup(setup: pd.DataFrame):
        tasks = get_tasks()
        rulesets = get_agent_types()

        def find_task_id(value):

            task_index = [tasks[tasks["Task"] == task_name].index.astype(int)[0] for task in value for task_name in tasks["Task"] if task_name == task]

            if len(value) is not len(task_index):
                raise Exception("Can not find task from setup. Please check if the task name has changed: " + str(value))
            return task_index

        def find_ruleset_id(value):
            ruleset_index = [rulesets[rulesets["Priority Ruleset"] == ruleset_name].index.astype(int)[0] for ruleset in value for ruleset_name in rulesets["Priority Ruleset"] if ruleset_name == ruleset]
            if len(value) is not len(ruleset_index):
                raise Exception("Can not find ruleset from setup. Please check if the task name has changed: " + str(value))
            return ruleset_index

        setup["Machines"] = setup["Machines"].apply(find_task_id)
        setup["Agents"] = setup["Agents"].apply(find_ruleset_id)
        return setup

    def init_machine_cells(number: int):

        types = [task.name.decode("UTF-8") for task in ProcessingStep.instances if not task.hidden]
        df = pd.DataFrame(0, index=np.arange(number), columns=types)
        df.index.names = ["Machine Cell"]
        return df

    def get_tasks():
        tasks = pd.DataFrame([{"Task": task.name.decode("UTF-8")} for task in ProcessingStep.instances if not task.hidden], columns=["Task"], index=[task.id for task in ProcessingStep.instances if not task.hidden])
        return tasks

    def get_agent_types():
        types = [{"Priority Ruleset": ruleset.name.decode("UTF-8"), "Description": ruleset.description.decode("UTF-8")} for ruleset in RuleSet.instances]
        df = pd.DataFrame(types, columns=["Priority Ruleset", "Description"])
        return df

    def multiply_values_in_df(value):
        index_col = list(value.index.values)
        values = value.tolist()
        value = [[a]*b for a,b in zip(index_col,values)]

        return value

    def add_distribution_cells(df: pd.DataFrame, df_map: pd.DataFrame, level=1, last_cell=0):

        if level is not 1:
            remaining_cells = df[str(level - 1)].nunique()

            if df[df.columns[-1]].nunique() == 1 and level is not 1:
                return df, df_map

        else:
            remaining_cells = len(df["0"])
            print("\nPlease define the distribution cells needed for your manufacturing cells to build a hierachy.\n")

        df[str(level)] = 0
        position = 0

        while remaining_cells > 0:
            print("Current hierachy:\n", df_map)
            number_to_add = _input("\nHow many cells are childs of the next distribution cell?\n", int, max=remaining_cells)
            last_cell += 1

            if level is not 1:
                last_level_cells = df.loc[position:, ].groupby(str(level-1))[str(level-1)].count()
                rows = last_level_cells.head(number_to_add).sum()
            else:
                rows = number_to_add

            df.loc[position:position + rows - 1, str(level)] = last_cell

            if rows == 1:
                df_map.loc[position:position + rows - 1, str(level)] = "─"
            elif rows == 2:
                df_map.loc[position:position + 1 - 1, str(level)] = "┐"
                df_map.loc[position+1:position + rows - 1, str(level)] = "┘"
            else:
                df_map.loc[position:position + 1 - 1, str(level)] = "┐"
                df_map.loc[position + 1:position + rows - 2, str(level)] = "┤"
                df_map.loc[position + rows -1:position + rows - 1, str(level)] = "┘"

            remaining_cells -= number_to_add
            position += rows

        return add_distribution_cells(df, df_map, level + 1, last_cell)

    def add_agents_and_storage(cells_layout: pd.DataFrame):

        amount_dist_cell = cells_layout[cells_layout.columns[-1]].max()

        cells = cells_layout["0"].to_frame(name="Machines")
        cells.index.name = None
        cells["Cell Title"] = "Manufacturing Cell "
        cells["Cell Title"] = cells["Cell Title"] + cells.index.astype(str)
        cells["Type"] = "Man"

        for i in range(1, amount_dist_cell+1):
            cells = cells.append({"Machines":[],"Cell Title":"Distribution Cell " + str(i), "Type": "Dist"}, ignore_index=True)

        cells = cells[["Type", "Cell Title", "Machines"]]
        cells["Agents"] = None
        cells["StorageCap"] = None
        cells["InputCap"] = None
        cells["OutputCap"] = None

        # Get Storage Capacity
        if yes_no_question("\nDo all manufacturing cells have the same storage capacity?\n"):
            capacity = _input("\nHow many storage slots should each manufacturing cell storage have? ", int)
            cells.loc[(cells.Type == "Man"), "StorageCap"] = capacity
        else:
            for index, row in cells.loc[(cells.Type == "Man")].iterrows():
                print("\nCurrent Setup:\n", cells)
                cells.loc[index,"StorageCap"] = abs(_input("\nHow many storage slots should the next manufacturing cell storage have? ", int))

        if yes_no_question("\nDo all Distribution Cells have the same storage capacity?\n"):
            capacity = _input("\nHow many storage slots should each distribution cell storage have? ", int)
            cells.loc[(cells.Type == "Dist"), "StorageCap"] = capacity
        else:
            for index, row in cells.loc[(cells.Type == "Dist")].iterrows():
                print("\nCurrent Setup:\n", cells)
                cells.loc[index,"StorageCap"] = abs(_input("\nHow many storage slots should the next distribution cell storage have?", int))

        # Get Inputbuffer Capacity
        if yes_no_question("\nDo all cells have the same inputbuffer capacity?\n"):
            capacity = _input("\nHow many storage slots should each cells inputbuffer have? ", int)
            cells["InputCap"] = capacity
        else:
            for index, row in cells.iterrows():
                print("\nCurrent Setup:\n", cells)
                cells.loc[index, "InputCap"] = abs(_input("\nHow many storage slots should the input buffer of the next cell storage have? ", int))

        # Get Outputbuffer Capacity
        if yes_no_question("\nDo all cells have the same outputbuffer capacity?\n"):
            capacity = _input("\nHow many storage slots should each cells outputbuffer have? ", int)
            cells["OutputCap"] = capacity
        else:
            for index, row in cells.iterrows():
                print("\nCurrent Setup:\n", cells)
                cells.loc[index, "OutputCap"] = abs(_input("\nHow many storage slots should the outputbuffer of the next cell storage have? ", int))

        # Agents
        agent_types = get_agent_types()
        print("\n\nWhat ruleset should the agents in each cell follow?")

        if yes_no_question("\nDo all manufacturing cells have the same agent amount of each type?\n"):
            print("Available rulesets:\n", agent_types)
            agents = _input("\nWhat agents should each cell have? Use comma seperated values e.g. 1,1,3 for two agents of type 1 and one of type 3\n", str)
            agents = [abs(int(value)) for value in agents.split(",")]
            agents = [agent_types.loc[ruleset, "Priority Ruleset"] for ruleset in agents]
            cells.loc[(cells.Type == "Man"), "Agents"] = pd.Series([agents] * len(cells.loc[(cells.Type == "Man")]))
            print("\nCurrent Setup:\n", cells)
        else:
            for index, row in cells.loc[(cells.Type == "Man")].iterrows():
                print("\nCurrent Setup:\n", cells)
                agents = _input(
                    "\nWhat agents should the next manufacturing cell have? Use comma seperated values e.g. 1,1,3 for two agents of type 1 and one of type 3\n",
                    str)
                agents = [abs(int(value)) for value in agents.split(",")]
                agents = [agent_types.loc[ruleset, "Priority Ruleset"] for ruleset in agents]
                cells.loc[index, "Agents"] = agents

        if yes_no_question("\nDo all distribution cells have the same agent amount of each type?\n"):
            print("Available rulesets:\n", agent_types)
            agents = _input("\nWhat agents should each distribution cell have? Use comma seperated values e.g. 1,1,3 for two agents of type 1 and one of type 3\n", str)
            agents = [abs(int(value)) for value in agents.split(",")]
            agents = [agent_types.loc[ruleset, "Priority Ruleset"] for ruleset in agents]
            first_index = min(cells.loc[(cells.Type == "Dist"), "Agents"].index.tolist())
            result = pd.Series([agents] * len(cells.loc[(cells.Type == "Dist")]))
            result.index += first_index
            cells.loc[(cells.Type == "Dist"), "Agents"] = result
            print("\nCurrent Setup:\n", cells)
        else:
            for index, row in cells.loc[(cells.Type == "Dist")].iterrows():
                print("\nCurrent Setup:\n", cells)
                agents = _input(
                    "\nWhat agents should the next distribution cell have? Use comma seperated values e.g. 1,1,3 for two agents of type 1 and one of type 3\n",
                    str)
                agents = [abs(int(value)) for value in agents.split(",")]
                agents = [agent_types.loc[ruleset, "Priority Ruleset"] for ruleset in agents]
                cells.loc[index, "Agents"] = agents

        return cells

    def add_parents(cells: pd.DataFrame, cell_hierachie: pd.DataFrame):
        machine_cells = len(cells[cells["Type"] == "Man"])
        cells["Parent"] = None
        cells["Level"] = None
        hierachy_levels = int(cell_hierachie.columns[-1]) + 1

        for index, row in cell_hierachie.iterrows():
            cells.loc[index, "Parent"] = row[1] + machine_cells -1
            cells.loc[index, "Level"] = 0

        for index, row in cell_hierachie.iterrows():
            for column_int in range(1, hierachy_levels -1):
                cells.loc[machine_cells + int(row[str(column_int)]) - 1, "Parent"] = row[str(column_int+1)] + machine_cells - 1
                cells.loc[machine_cells + int(row[str(column_int)]) - 1, "Level"] = column_int

        cells["Level"] = cells["Level"].replace(np.nan, hierachy_levels-1)
        return cells

    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('expand_frame_repr', False)

    print("Create a new setup:\n")
    machine_cells = _input("How many machine cell should the setup have?\n", int)
    machine_types = init_machine_cells(machine_cells)

    for index, row in machine_types.iterrows():
        valid = False
        while not valid:
            print("Current Setup:\n", machine_types)
            machines = _input("\nHow many machines of each type should the next cell have? Separate with comma's!\n", str)
            machines = [abs(int(value)) for value in machines.split(",")]

            if len(machines) <= machine_types.shape[1] and len([num for num in machines if num is not 0]) > 0:
                valid = True
                machine_types.loc[index,] = machines + [0] * (machine_types.shape[1] - len(machines))
            else:
                print("This is not an valid input. Please choose another one!\n")

    cells = machine_types.T
    cells = cells.apply(multiply_values_in_df)

    for column in cells:
        cells[column][0] = cells[column].sum()

    cells = cells.head(1).T
    cells.columns = ["0"]

    cells_layout, cells_layout_map = add_distribution_cells(cells, copy(cells))

    print("\nYour final layout with IDs:\n", cells_layout)

    cells = add_agents_and_storage(cells_layout)

    cells = add_parents(cells, cells_layout)
    cells = normalize_setup(cells)

    if yes_no_question("\nSetup finished!\nDo you want to save your current setup? [Y/N]\n"):
        save_configuration(cells)
        print("File saved!")

    return cells


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
                    configuration = pd.read_csv(infile, sep=";", converters={'COLUMN_NAME': pd.eval})
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
        setup = pd.read_csv(infile, sep=";", converters={'COLUMN_NAME': pd.eval})
    return setup


def generator_from_setup(setup, config, env: simpy.Environment):
    """Create instances of setup as json and build first connections between the objects"""
    setup["agent_obj"] = None
    setup["machine_obj"] = None

    for index, column in setup.iterrows():
        # Create objects in cells
        setup.loc[index, "storage_obj"] = Cell.QueueBuffer(config, env, column["StorageCap"])
        setup.loc[index, "input_obj"] = Cell.InterfaceBuffer(config, env, column["InputCap"])
        setup.loc[index, "output_obj"] = Cell.InterfaceBuffer(config, env, column["OutputCap"])

        if isinstance(column["Agents"], list):
            agents = [Cell.ManufacturingAgent(config, env, setup.loc[index, "input_obj"],
                                              int(ruleset_id)) for ruleset_id in column["Agents"]]
        else:
            agents = [Cell.ManufacturingAgent(config, env, setup.loc[index, "input_obj"],
                        int(ruleset_id)) for ruleset_id in ast.literal_eval(column["Agents"])]

        setup.at[index, "agent_obj"] = agents

        if isinstance(column["Machines"], list):
            machines = [Cell.Machine.Machine(config, env, int(task_id))
                        for task_id in column["Machines"]]
        else:
            machines = [Cell.Machine.Machine(config, env, int(task_id))
                    for task_id in ast.literal_eval(column["Machines"])]

        setup.at[index, "machine_obj"] = machines

    for index, column in setup.iterrows():
        # Create each cell
        if column["Type"] == "Man":
            # Manufacturing cell
            setup.loc[index, "cell_obj"] = Cell.ManufacturingCell(column["machine_obj"], env, column["agent_obj"],
                                                                  column["storage_obj"], column["input_obj"],
                                                                  column["output_obj"], column["Level"])

        else:
            # Distribution cell
            childs = setup[setup["Parent"] == index]["cell_obj"].tolist()
            setup.loc[index, "cell_obj"] = Cell.DistributionCell(childs, env, column["agent_obj"],
                                                                  column["storage_obj"], column["input_obj"],
                                                                  column["output_obj"], column["Level"])

        column["input_obj"].lower_cell = setup.loc[index, "cell_obj"]
        column["output_obj"].lower_cell = setup.loc[index, "cell_obj"]

    # Set parents in cells and interfaces upper cell
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('expand_frame_repr', False)

    setup = setup.fillna(value=np.nan)

    for index, column in setup.iterrows():
        parent_id = column["Parent"]

        if not np.isnan(parent_id):
            column["cell_obj"].PARENT = setup.loc[parent_id, "cell_obj"]
            column["input_obj"].upper_cell = setup.loc[parent_id, "cell_obj"]
            column["output_obj"].upper_cell = setup.loc[parent_id, "cell_obj"]

    setup["cell_obj"].apply(finish_setup)

    return setup


def finish_setup(cell):
    """Set the tree level of each cell in the tree, init agents and performable tasks"""
    cell.init_responsible_agents()
    cell.init_performable_tasks()


def set_env_in_cells(sim_env, cells):
    for cell in cells.tolist():

        cell.SIMULATION_ENVIRONMENT = sim_env
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

