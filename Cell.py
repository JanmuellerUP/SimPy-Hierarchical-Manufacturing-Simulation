from ManufacturingAgent import ManufacturingAgent
from Buffer import Buffer, InterfaceBuffer, QueueBuffer
import Machine
from ProcessingStep import ProcessingStep
import itertools
import simpy
from Utils.log import get_log
import pandas as pd
import state_attributes
from copy import copy

import time_tracker
import time


class Cell:
    instances = []

    def __init__(self, env: simpy.Environment, agents: list, storage: QueueBuffer, input_buffer: InterfaceBuffer,
                 output_buffer: InterfaceBuffer, level, cell_id, cell_type):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None

        # Attributes
        self.ID = cell_id
        self.TYPE = cell_type
        self.PARENT = None  # Parent cell of this cell, None if cell is main cell
        self.LEVEL = level  # Hierarchy level of this cell, counting bottom up
        self.HEIGHT = None  # Physical distance between top and bottom of the cell, used for distance calculations
        self.WIDTH = None  # Physical distance between left and right side of the cell, used for distance calculations
        self.DISTANCES = []  # Array containing all possible paths within the cell with shortest length. Agent always use the shortest path to its destination
        self.AGENTS = agents  # Agents within the cell
        for agent in agents:
            agent.CELL = self
            agent.PARTNER_AGENTS = len(agents) - 1
        self.INPUT_BUFFER = input_buffer  # Input buffer of the cell, Interface with parent cell.
        self.OUTPUT_BUFFER = output_buffer  # Output buffer of the cell, Interface with parent cell.
        self.STORAGE = storage  # Storage buffer of the cell. Only one Storage per cell.
        self.POSSIBLE_POSITIONS = [input_buffer, output_buffer, storage]  # All possible positions for agents within this cell
        self.CELL_CAPACITY = sum([pos.STORAGE_CAPACITY for pos in self.POSSIBLE_POSITIONS]) + len(self.MACHINES) * 3 + len(self.AGENTS)
        self.PERFORMABLE_TASKS = []  # Amount of machines in this cell or its childs for each processing step. Used to determine if orders can be completly processed in this tree branch

        # State
        self.orders_in_cell = []  # Items currently located within this cell
        self.expected_orders = []  # Announced Orders, that will be available within this cell within next time (Order, Time, Position, Agent)

        self.__class__.instances.append(self)
        self.result = None
        self._excluded_keys = ["logs", "HEIGHT", "WIDTH", "SIMULATION_ENVIRONMENT", "env", "DISTANCES",
                               "POSSIBLE_POSITIONS", "PERFORMABLE_TASKS"]  # Attributes excluded from log
        self._continuous_attributes = []  # Attributes that have to be calculated for states between discrete events

    def orders_available(self):
        non_locked = [order for order in self.orders_in_cell if not order.locked_by or order.processing]
        if len(non_locked) > 0:
            return True
        return False

    def inform_incoming_order(self, agent, item, time, position):
        self.expected_orders.append((item, time, position, agent))

    def cancel_incoming_order(self, order_cancel):
        if self.expected_orders:
            for item in self.expected_orders:
                order, time, position, agent = item
                if order == order_cancel:
                    self.expected_orders.remove(item)
                    return

    def all_tasks_included(self, order, all_tasks=True, alternative_tasks=None):
        """Test if all tasks within the orders work schedule can be performed by this cell.
        Alternative list of tasks is possible. Return True or False"""
        if alternative_tasks:
            performable_tasks = alternative_tasks
        else:
            performable_tasks = self.PERFORMABLE_TASKS
        if all_tasks:
            work_schedule = order.work_schedule
        else:
            work_schedule = order.remaining_tasks
        for task in work_schedule:
            task_possible = False
            for (perform_task, machines) in performable_tasks:
                if task == perform_task and machines > 0:
                    task_possible = True
            if not task_possible:
                return 0
        return 1

    def occupancy(self, requester: ManufacturingAgent, criteria: dict):
        buffer = [self.INPUT_BUFFER.occupancy("Input", criteria["buffer"], self)] + [self.OUTPUT_BUFFER.occupancy("Output", criteria["buffer"], self)]

        storage = [self.STORAGE.occupancy("Storage", criteria["buffer"], self)]

        agents = [agent.occupancy(criteria["agent"], requester=requester) for agent in self.AGENTS]

        machines = [machine.occupancy(criteria["machine"]) for machine in self.MACHINES]

        interfaces_in = [interface.occupancy("Interface-In", criteria["buffer"]) for interface in self.INTERFACES_IN]
        interfaces_out = [interface.occupancy("Interface-Out", criteria["buffer"]) for interface in self.INTERFACES_OUT]

        result = buffer + storage + agents + machines + interfaces_in + interfaces_out

        return [{**item, **pos_attr} for sublist, pos_attr in result for item in sublist]

    def get_cell_state(self, requester: ManufacturingAgent):
        if requester.RULESET.dynamic:
            criteria = state_attributes.smart_state
            ranking_criteria = []
        else:
            criteria = state_attributes.normal_state
            ranking_criteria = requester.ranking_criteria

        # Get occupancy of all available slots within this cell
        now = time.time()
        #occupancy_states = pd.DataFrame(self.occupancy(requester, criteria), columns=["order", "pos", "pos_type"] + attribute_columns)
        occupancy_states = pd.DataFrame(self.occupancy(requester, criteria))
        time_tracker.time_occupancy_calc += time.time() - now

        # Add attributes for each order within this cell
        now = time.time()
        occupancy_states = self.add_order_attributes(occupancy_states, requester, criteria["order"] + list(set(ranking_criteria) - set(criteria["order"])))
        time_tracker.time_order_attr_calc += time.time() - now

        return occupancy_states

    def add_order_attributes(self, occupancy, requester: ManufacturingAgent, attributes: list):

        current_time = self.env.now

        occupancy["attributes"] = occupancy["order"].apply(get_order_attributes, args=(requester, attributes, current_time))

        now = time.time()
        occupancy = occupancy.join(pd.DataFrame(occupancy.pop("attributes").values.tolist()))
        time_tracker.b += time.time() - now

        return occupancy

    def inform_agents(self):
        """Inform all agents that the cell states have changed. Idling agent will check for new tasks"""
        for agent in self.AGENTS:
            agent.state_change_in_cell()

    def new_order_in_cell(self, order):
        order.current_cell = self
        order.in_cell_since = self.env.now
        self.cancel_incoming_order(order)
        self.orders_in_cell.append(order)

    def remove_order_in_cell(self, order):
        order.in_cell_since = None
        self.orders_in_cell.remove(order)

class ManufacturingCell(Cell):

    def __init__(self, machines: list, *args):
        self.MACHINES = machines
        self.INTERFACES_IN = []
        self.INTERFACES_OUT = []

        super().__init__(*args)

        self.POSSIBLE_POSITIONS += machines

        self.DISTANCES = [(start, end, 5) for start in self.POSSIBLE_POSITIONS for end in self.POSSIBLE_POSITIONS if
                          start is not end]

    def init_responsible_agents(self):
        """Set responsible agents of object within the cell to the cell agents"""
        self.INPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.OUTPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.STORAGE.RESPONSIBLE_AGENTS = self.AGENTS
        for machine in self.MACHINES:
            machine.RESPONSIBLE_AGENTS = self.AGENTS

    def init_performable_tasks(self):
        """Initialize self.PERFORMABLE_TASKS:
        Which tasks can be performed within this cell and how many machines are there for each?
        Iterate through complete tree branch"""
        result = []
        for task in ProcessingStep.instances:
            machine_counter = 0
            for machine in self.MACHINES:
                if machine.PERFORMABLE_TASK == task:
                    machine_counter += 1
            result.append((task, machine_counter))
        self.PERFORMABLE_TASKS = result

    def check_best_path(self, order, include_all=True):
        """Test if all tasks within the orders work schedule can be performed by this cell. Return True or False"""
        return self.all_tasks_included(order, all_tasks=include_all)


class DistributionCell(Cell):

    def __init__(self, childs: list, *args):
        self.CHILDS = childs
        self.MACHINES = []
        self.INTERFACES_IN = [child.INPUT_BUFFER for child in childs]
        self.INTERFACES_OUT = [child.OUTPUT_BUFFER for child in childs]

        super().__init__(*args)

        self.POSSIBLE_POSITIONS += self.INTERFACES_IN
        self.POSSIBLE_POSITIONS += self.INTERFACES_OUT
        self.CELL_CAPACITY += sum([inpt.STORAGE_CAPACITY for inpt in self.INTERFACES_IN]) + sum([outpt.STORAGE_CAPACITY for outpt in self.INTERFACES_OUT])

        self.DISTANCES = [(start, end, 5) for start in self.POSSIBLE_POSITIONS for end in self.POSSIBLE_POSITIONS if start is not end]

    def init_responsible_agents(self):
        """Set responsible agents of object within the cell to the cell agents"""
        self.INPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.OUTPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.STORAGE.RESPONSIBLE_AGENTS = self.AGENTS
        for agent in self.AGENTS:
            agent.position = self.INPUT_BUFFER
            self.INPUT_BUFFER.agents_at_position.append(agent)

    def init_performable_tasks(self):
        """Initialize self.PERFORMABLE_TASKS:
        Which tasks can be performed within this cell and how many machines are there for each?
        Iterate through complete tree branch"""
        child_tasks = []
        for child in self.CHILDS:
            if len(child.PERFORMABLE_TASKS) == 0:
                child.init_performable_tasks()
            child_tasks.append(child.PERFORMABLE_TASKS)
        self.PERFORMABLE_TASKS = combine_performable_tasks(child_tasks)

    def check_best_path(self, order, include_all=True):
        """Calculate the minimal amount of manufacturing cells needed to
         process this order completely in each tree branch"""
        child_results = []
        for child in self.CHILDS:
            child_results.append(child.check_best_path(
                order))  # Rekursiver Aufruf im Teilbaum. Speichere Ergebnisse der Kinder in Liste.
        child_results[:] = (value for value in child_results if value != 0)
        if child_results:
            return min(child_results)  # Wenn Kinder Werte ausser 0 haben, gebe das Minimum zurueck
        elif self.all_tasks_included(order, all_tasks=include_all):
            if len(self.CHILDS) == 2:
                return 2  # Alle Arbeitsschritte durchführbar und exakt 2 Childs vorhanden -> Arbeit muss geteilt werden
            else:
                cells = list(self.CHILDS)
                min_combi = float('inf')
                for length in range(2, len(cells) + 1):
                    for subset in itertools.combinations(cells, length):
                        tasks_list = []
                        for cell in subset:
                            tasks_list.append(cell.PERFORMABLE_TASKS)
                        combination_to_test = combine_performable_tasks(tasks_list)
                        if self.all_tasks_included(order, alternative_tasks=combination_to_test) and len(
                                subset) < min_combi:
                            min_combi = len(subset)
                return min_combi
        else:
            return 0  # Tasks cannot be done in this cell alone


def combine_performable_tasks(task_array):
    """Util function to flatten multidimensional lists into one flat list
    with the amount of appearences within the list"""
    result = []
    flatten_list = []
    for child_cell in task_array:
        flatten_list += child_cell
    for task in ProcessingStep.instances:
        number_of_machines = 0
        for list_element in flatten_list:
            task_type, machines = list_element
            if task_type == task:
                number_of_machines += machines
        result.append((task, number_of_machines))
    return result


def get_order_attributes(order, requester: ManufacturingAgent, attributes: list, now):

        def start():
            return now - order.start

        def due_to():
            return now - order.due_to

        def complexity():
            return order.complexity

        def type():
            return order.type.type_id

        def time_in_cell():
            return now - order.in_cell_since

        def locked():
            if not order.locked_by:
                return 0
            elif order.locked_by == requester:
                return 1
            else:
                return 2

        def picked_up():
            if not order.picked_up_by:
                return 0
            elif order.picked_up_by == requester:
                return 1
            else:
                return 2

        def processing():
            return int(order.processing)

        def tasks_finished():
            return int(order.tasks_finished)

        def remaining_tasks():
            return len(order.remaining_tasks)

        def next_task():
                return order.next_task.id

        def distance():
            if order.position:
                return requester.time_for_distance(order.position)
            else:
                return -1

        def in_m():
            if isinstance(order.position, Machine.Machine):
                if order == order.position.item_in_machine:
                    return 1
                else:
                    return 0
            else:
                return 0

        def in_m_input():
            if isinstance(order.position, Machine.Machine):
                if order == order.position.item_in_input:
                    return 1
                else:
                    return 0
            else:
                return 0

        def in_same_cell():
            if order.current_cell == requester.CELL:
                return 1
            else:
                return 0

        attr = {}

        if order:
            for attribute in attributes:
                attr[attribute] = locals()[attribute]()

        return attr