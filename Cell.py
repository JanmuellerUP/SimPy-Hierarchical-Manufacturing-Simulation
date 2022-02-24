from ManufacturingAgent import ManufacturingAgent
from Buffer import Buffer, InterfaceBuffer, QueueBuffer
import Machine
from ProcessingStep import ProcessingStep
import itertools
import simpy
from Utils.log import get_log
import pandas as pd

import time_tracker
import time


class Cell:
    instances = []

    def __init__(self, env: simpy.Environment, agents: list, storage: QueueBuffer, input_buffer: InterfaceBuffer = None,
                 output_buffer: InterfaceBuffer = None, level=None):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None

        # Attributes
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
        self.PERFORMABLE_TASKS = []  # Amount of machines in this cell or its childs for each processing step. Used to determine if orders can be completly processed in this tree branch

        # State
        self.orders_in_cell = []  # Items currently located within this cell
        self.expected_orders = []  # Announced Orders, that will be available within this cell within next time (Order, Time, Position, Agent)

        self.__class__.instances.append(self)
        self.result = None
        self._excluded_keys = ["logs", "HEIGHT", "WIDTH", "SIMULATION_ENVIRONMENT", "env", "DISTANCES",
                               "POSSIBLE_POSITIONS", "PERFORMABLE_TASKS"]  # Attributes excluded from log
        self._continuous_attributes = []  # Attributes that have to be calculated for states between discrete events

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

    def occupancy(self, requester: ManufacturingAgent):
        buffer = [self.INPUT_BUFFER.occupancy("Input")] + [self.OUTPUT_BUFFER.occupancy("Output")]
        storage = [self.STORAGE.occupancy("Storage")]
        agents = [agent.occupancy(requester=requester) for agent in self.AGENTS]
        machines = [machine.occupancy() for machine in self.MACHINES]
        interfaces_in = [interface.occupancy("Interface-In") for interface in self.INTERFACES_IN]
        interfaces_out = [interface.occupancy("Interface-Out") for interface in self.INTERFACES_OUT]

        result = buffer + storage + agents + machines + interfaces_in + interfaces_out

        return [item for sublist in result for item in sublist]

    def get_cell_state(self, requester: ManufacturingAgent):


        # Get occupancy of all available slots within this cell
        now = time.time()
        occupancy_states = pd.DataFrame(self.occupancy(requester), columns=["order", "pos", "pos_type"])
        time_tracker.time_occupancy_calc += time.time() - now

        # Add attributes for each order within this cell
        now = time.time()
        occupancy_states = self.add_order_attributes(occupancy_states, requester)
        time_tracker.time_order_attr_calc += time.time() - now

        # Add attributes for each of the positions (machine, agent, buffer)
        now = time.time()
        occupancy_states = self.add_position_attributes(occupancy_states)
        time_tracker.time_pos_attr_calc += time.time() - now

        return occupancy_states

    def add_order_attributes(self, occupancy, requester: ManufacturingAgent):

        current_time = self.env.now
        attribute_columns = ["start", "due_to", "complexity", "type", "in_cell_since", "locked",
                             "picked_up", "processing", "tasks_finished", "remaining_tasks", "next_task",
                             "distance", "in_m_input", "in_m", "in_same_cell"]

        occupancy["attributes"] = occupancy["order"].apply(get_order_attributes,
                                                                     args=(requester, current_time))

        occupancy = pd.concat([occupancy.drop("attributes", axis=1), pd.json_normalize(occupancy["attributes"])], axis=1)

        if not len(occupancy.index):
            occupancy = pd.concat([occupancy, pd.DataFrame(columns=attribute_columns)])

        return occupancy

    def add_position_attributes(self, occupancy):

        current_time = self.env.now
        attribute_columns = ["agent_position", "moving", "remaining_moving_time", "next_position", "has_task",
                             "locked_item", "current_setup", "in_setup", "next_setup", "remaining_setup_time",
                             "manufacturing", "failure", "remaining_man_time", "failure_fixed_in", "Interface ingoing",
                             "Interface outgoing"]

        occupancy["pos_attributes"] = occupancy["pos"].apply(get_pos_attributes,
                                                                     args=(current_time, self))

        occupancy = pd.concat([occupancy.drop("pos_attributes", axis=1), pd.json_normalize(occupancy["pos_attributes"])], axis=1)

        if not len(occupancy.index):
            occupancy = pd.concat([occupancy, pd.DataFrame(columns=attribute_columns)])

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
        super().__init__(*args)
        self.MACHINES = machines
        self.INTERFACES_IN = []
        self.INTERFACES_OUT = []
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
        super().__init__(*args)
        self.CHILDS = childs
        self.MACHINES = []
        self.INTERFACES_IN = [child.INPUT_BUFFER for child in childs]
        self.INTERFACES_OUT = [child.OUTPUT_BUFFER for child in childs]
        self.POSSIBLE_POSITIONS += self.INTERFACES_IN
        self.POSSIBLE_POSITIONS += self.INTERFACES_OUT

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


def get_order_attributes(order, requester, now):
    if order:

        result = {}

        result["start"] = now - order.start
        result["due_to"] = now - order.due_to
        result["complexity"] = order.complexity
        result["type"] = order.type.type_id
        result["in_cell_since"] = now - order.in_cell_since

        if not order.locked_by:
            result["locked"] = 0
        elif order.locked_by == requester:
            result["locked"] = 1
        else:
            result["locked"] = 2

        if not order.picked_up_by:
            result["picked_up"] = 0
        elif order.picked_up_by == requester:
            result["picked_up"] = 1
        else:
            result["picked_up"] = 2

        result["processing"] = int(order.processing)
        result["tasks_finished"] = int(order.tasks_finished)
        result["remaining_tasks"] = len(order.remaining_tasks)

        if result["remaining_tasks"] is not 0:
            result["next_task"] = order.next_task.id
        else:
            result["next_task"] = -1

        if order.position:
            result["distance"] = requester.time_for_distance(order.position)
        else:
            result["distance"] = -1


        if isinstance(order.position, Machine.Machine):
            if order == order.position.item_in_input:
                result["in_m_input"] = 1
                result["in_m"] = 0
            elif order == order.position.item_in_machine:
                result["in_m_input"] = 0
                result["in_m"] = 1
            else:
                result["in_m_input"] = 0
                result["in_m"] = 0
        else:
            result["in_m_input"] = 0
            result["in_m"] = 0

        if order.current_cell == requester.CELL:
            result["in_same_cell"] = 1
        else:
            result["in_same_cell"] = 0

    else:
        result = {"start": 0, "due_to": 0, "complexity": 0, "type": 0, "in_cell_since": 0, "locked": 0,
                             "picked_up": 0, "processing": 0, "tasks_finished": 0, "remaining_tasks": 0, "next_task": 0,
                             "distance": 0, "in_m_input": 0, "in_m": 0, "in_same_cell": 0}

    return result


def get_pos_attributes(pos, now, cell: Cell):
    result = {}

    if isinstance(pos, ManufacturingAgent):
        # Attributes of agent

        result["agent_position"] = pos.position
        result["moving"] = int(pos.moving)
        if pos.moving:
            result["remaining_moving_time"] = pos.moving_end_time - now
            result["next_position"] = pos.next_position
        else:
            result["remaining_moving_time"] = 0
            result["next_position"] = -1

        result["has_task"] = int(pos.has_task)

        if pos.locked_item:
            result["locked_item"] = pos.locked_item
        else:
            result["locked_item"] = -1

    elif isinstance(pos, Machine.Machine):
        # Attributes of machine

        if pos.current_setup:
            result["current_setup"] = pos.current_setup.type_id
        else:
            result["current_setup"] = -1

        result["in_setup"] = int(pos.setup)

        if pos.setup:
            result["next_setup"] = pos.next_expected_order.type.type_id
            result["remaining_setup_time"] = pos.setup_finished_at - now
        else:
            result["next_setup"] = result["current_setup"]
            result["remaining_setup_time"] = 0

        result["manufacturing"] = int(pos.manufacturing)
        result["failure"] = int(pos.failure)

        if pos.failure:
            result["remaining_man_time"] = pos.remaining_manufacturing_time
            result["failure_fixed_in"] = pos.failure_fixed_at - now
        elif pos.manufacturing:
            result["remaining_man_time"] = pos.manufacturing_end_time - now
            result["failure_fixed_in"] = 0
        else:
            result["remaining_man_time"] = 0
            result["failure_fixed_in"] = 0

    elif isinstance(pos, InterfaceBuffer):
        if pos.lower_cell == cell:
            # Input/Output of Cell
            if pos == cell.INPUT_BUFFER:
                result["Interface outgoing"] = 0
                result["Interface ingoing"] = 1
            else:
                result["Interface outgoing"] = 1
                result["Interface ingoing"] = 0
        elif pos.upper_cell == cell:
            if pos == pos.lower_cell.INPUT_BUFFER:
                result["Interface outgoing"] = 1
                result["Interface ingoing"] = 0
            else:
                result["Interface outgoing"] = 0
                result["Interface ingoing"] = 1

    return result