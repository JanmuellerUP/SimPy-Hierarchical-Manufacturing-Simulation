from ManufacturingAgent import ManufacturingAgent
from Buffer import InterfaceBuffer, QueueBuffer
import Machine
from ProcessingStep import ProcessingStep
import itertools
import simpy
from Utils.log import get_log


class Cell:
    instances = []

    def __init__(self, env: simpy.Environment, agents: list, storage: QueueBuffer, input_buffer: InterfaceBuffer=None, output_buffer: InterfaceBuffer=None, parent_cell=None):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None

        # Attributes
        self.PARENT = parent_cell  # Parent cell of this cell, None if cell is main cell
        self.LEVEL = None  # Hierachie level of this cell, counting bottom up
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
        self.POSSIBLE_POSITIONS = [storage]  # All possible positions for agents within this cell
        self.PERFORMABLE_TASKS = []  # Amount of machines in this cell or its childs for each processing step. Used to determine if orders can be completly processed in this tree branch

        # State
        self.orders_in_cell = []  # Items currently located within this cell
        self.expected_orders = []  # Announced Orders, that will be available within this cell within next time (Order, Time, Position, Agent)

        self.__class__.instances.append(self)
        self.logs = []
        self._excluded_keys = ["logs", "HEIGHT", "WIDTH", "SIMULATION_ENVIRONMENT", "env", "DISTANCES", "POSSIBLE_POSITIONS", "PERFORMABLE_TASKS"] # Attributes excluded from log

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

    def calculate_states(self, requester=None):

        state = {
            "orders_currently_in_cell": [(order, get_log(order, requester)) for order in self.orders_in_cell],
            "expected_orders": [(order, get_log(order), timestamp, position) for order, timestamp, position, agent in self.expected_orders],
            "partner_agents": [(agent, get_log(agent)) for agent in self.AGENTS if agent != requester],
            "storage": (self.STORAGE, get_log(self.STORAGE)),
            "input_buffer": (self.INPUT_BUFFER, get_log(self.INPUT_BUFFER)),
            "output_buffer": (self.OUTPUT_BUFFER, get_log(self.OUTPUT_BUFFER))
        }

        if isinstance(self, ManufacturingCell):
            state["machines"] = [(machine, get_log(machine)) for machine in self.MACHINES]
            state["interfaces_in"] = []
            state["interfaces_out"] = []
        else:
            state["machines"] = []
            state["interfaces_in"] = [(interface, get_log(interface)) for interface in self.INTERFACES_IN]
            state["interfaces_out"] = [(interface, get_log(interface)) for interface in self.INTERFACES_OUT]

        return state

    def get_position_of_next_expected_order(self):
        """At which position is the next unblocked order expected?
        Useful to move agent to this position to save moving time"""
        min_time = float('inf')
        if not self.expected_orders:
            return None, None
        for order, time, position, agent in self.expected_orders:
            if order.next_locked_by and time > min_time:
                continue
            else:
                min_time = time
                next_position = position
                item = order
        return next_position, item

    def recalculate_agents(self, failure=False):
        """Inform all agents that the cell states have changed. Idling agent will check for new tasks"""
        for agent in self.AGENTS:
            agent.state_change_in_cell(failure)

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

    def calculate_distances(self, input_pos, output_pos, storage_pos, junctions, machines):
        """Calculate distances within this cell and initialize self.DISTANCES for length of paths"""
        junctions = junctions

        def shortest_route_one_junction(start, end):
            start_x, start_y = start
            end_x, end_y = end
            junctions_with_dist = []
            for junction in junctions:
                x, y = junction
                distance_from_start = abs(start_x-x) + abs(start_y-y)
                distance_to_end = abs(end_x - x) + abs(end_y - y)
                junctions_with_dist.append((junction, distance_from_start + distance_to_end))
            dist_min = float('inf')
            for (junction, dist) in junctions_with_dist:
                if dist < dist_min:
                    dist_min = dist
            return dist_min

        def shortest_route_two_junctions(start, end):
            start_x, start_y = start
            end_x, end_y = end
            junctions_with_dist = []
            for junction in junctions:
                x, y = junction
                distance_from_start = abs(start_x-x) + abs(start_y-y)
                distance_to_end = abs(end_x-x) + abs(end_y-y)
                junctions_with_dist.append((junction, distance_from_start, distance_to_end))
            dist_start_min = float('inf')
            junction_start_min = None
            dist_end_min = float('inf')
            junction_end_min = None
            for (junction, dist_start, dist_end) in junctions_with_dist:
                if dist_start < dist_start_min:
                    dist_start_min = dist_start
                    junction_start_min = junction
                if dist_end < dist_end_min:
                    dist_end_min = dist_end
                    junction_end_min = junction
            j1_x, j1_y = junction_start_min
            j2_x, j2_y = junction_end_min
            dist_junctions = abs(j1_x-j2_x) + abs (j1_y-j2_y)
            return dist_start_min + dist_end_min + dist_junctions

        self.DISTANCES = []
        position_coords = [storage_pos, machines, input_pos, output_pos]
        flat_coords = []
        for element in position_coords:
            if isinstance(element,list):
                for list_element in element:
                    flat_coords.append(list_element)
            else:
                flat_coords.append(element)
        self.POSSIBLE_POSITIONS = list(zip(self.POSSIBLE_POSITIONS, flat_coords))
        for start_obj in self.POSSIBLE_POSITIONS:
            ends = list(self.POSSIBLE_POSITIONS) # Copy by value!
            ends.remove(start_obj)
            for end_obj in ends:
                interface_and_machine_or_storage = (start_obj[0] == self.INPUT_BUFFER or start_obj[0] == self.OUTPUT_BUFFER) and (end_obj[0] in self.MACHINES or end_obj[0] == self.STORAGE)
                machine_or_storage_and_interface = (end_obj[0] == self.INPUT_BUFFER or end_obj[0] == self.OUTPUT_BUFFER) and (start_obj[0] in self.MACHINES or start_obj[0] == self.STORAGE)
                if interface_and_machine_or_storage or machine_or_storage_and_interface:
                    # Nur eine Abzweigung in Zelle nötig
                    shortest_distance = shortest_route_one_junction(start_obj[1], end_obj[1])
                else:
                    # Zwei Abzweigungen nötig
                    shortest_distance = shortest_route_two_junctions(start_obj[1], end_obj[1])
                self.DISTANCES.append((start_obj[0], end_obj[0], shortest_distance))

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

    def init_responsible_agents(self):
        """Set responsible agents of object within the cell to the cell agents"""
        self.INPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.OUTPUT_BUFFER.RESPONSIBLE_AGENTS = self.AGENTS
        self.STORAGE.RESPONSIBLE_AGENTS = self.AGENTS

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

    def calculate_distances(self, input_pos, output_pos, storage_pos, junctions, interfaces_in, interfaces_out):
        """Calculate distances within this cell and initialize self.DISTANCES for length of paths"""
        junctions = junctions

        def shortest_route_without_junction(start, end):
            start_x, start_y = start
            end_x, end_y = end
            dist = abs(start_x-end_x) + abs(start_y-end_y)
            return dist

        def shortest_route_over_storage(start, end):
            start_x, start_y = start
            end_x, end_y = end
            real_junctions = junctions
            for x_top, y_top in interfaces_in:
                real_junctions = [(x, y) for (x, y) in real_junctions if x != x_top]
            junctions_with_dist = []
            for junction in real_junctions:
                x, y = junction
                if x <= start_x:
                    distance_from_start = abs(start_x-x) + abs(start_y-y)
                else:
                    distance_from_start = float('inf')
                if x <= end_x:
                    distance_to_end = abs(end_x-x) + abs(end_y-y)
                else:
                    distance_to_end = float('inf')
                junctions_with_dist.append((junction, distance_from_start, distance_to_end))
            dist_start_min = float('inf')
            junction_start_min = None
            dist_start_end_min = float('inf')
            dist_end_min = float('inf')
            dist_end_start_min = float('inf')
            junction_end_min = None
            for (junction, dist_start, dist_end) in junctions_with_dist:
                if dist_start <= dist_start_min:
                    if (dist_start == dist_start_min and dist_end <= dist_start_end_min) or dist_start < dist_start_min:
                        dist_start_min = dist_start
                        dist_start_end_min = dist_end
                        junction_start_min = junction
                if dist_end <= dist_end_min:
                    if (dist_end == dist_end_min and dist_start <= dist_end_start_min) or dist_end < dist_end_min:
                        dist_end_min = dist_end
                        dist_end_start_min = dist_start
                        junction_end_min = junction
            j1_x, j1_y = junction_start_min
            j2_x, j2_y = junction_end_min
            dist_junctions = abs(j1_x-j2_x) + abs (j1_y-j2_y)
            dist = dist_start_min + dist_end_min + dist_junctions
            return dist

        def shortest_route_two_junctions(start, end):
            start_x, start_y = start
            end_x, end_y = end
            junctions_with_dist = []
            for junction in junctions:
                x, y = junction
                distance_from_start = abs(start_x-x) + abs(start_y-y)
                distance_to_end = abs(end_x-x) + abs(end_y-y)
                junctions_with_dist.append((junction, distance_from_start, distance_to_end))
            dist_start_min = float('inf')
            junction_start_min = None
            dist_end_min = float('inf')
            junction_end_min = None
            for (junction, dist_start, dist_end) in junctions_with_dist:
                if dist_start < dist_start_min:
                    dist_start_min = dist_start
                    junction_start_min = junction
                if dist_end < dist_end_min:
                    dist_end_min = dist_end
                    junction_end_min = junction
            j1_x, j1_y = junction_start_min
            j2_x, j2_y = junction_end_min
            dist_junctions = abs(j1_x-j2_x) + abs (j1_y-j2_y)
            dist = dist_start_min + dist_end_min + dist_junctions
            return dist

        self.DISTANCES = []
        position_coords = [storage_pos, interfaces_in, interfaces_out, input_pos, output_pos]
        flat_coords = []
        for element in position_coords:
            if isinstance(element,list):
                for list_element in element:
                    flat_coords.append(list_element)
            else:
                flat_coords.append(element)
        self.POSSIBLE_POSITIONS = list(zip(self.POSSIBLE_POSITIONS, flat_coords))
        for start_obj in self.POSSIBLE_POSITIONS:
            ends = list(self.POSSIBLE_POSITIONS) # Copy by value!
            ends.remove(start_obj)
            for end_obj in ends:
                int_in_global_and_local = start_obj[0] == self.INPUT_BUFFER and (end_obj[0] in self.INTERFACES_IN or end_obj[0] == self.STORAGE) or end_obj[0] == self.INPUT_BUFFER and (start_obj[0] in self.INTERFACES_IN or start_obj[0] == self.STORAGE)
                int_out_global_and_local = start_obj[0] == self.OUTPUT_BUFFER and (end_obj[0] in self.INTERFACES_OUT or end_obj[0] == self.STORAGE) or end_obj[0] == self.OUTPUT_BUFFER and (start_obj[0] in self.INTERFACES_OUT or start_obj[0] == self.STORAGE)
                int_local_and_local = (start_obj[0] in self.INTERFACES_IN and end_obj[0] in self.INTERFACES_IN) or (start_obj[0] in self.INTERFACES_OUT and end_obj[0] in self.INTERFACES_OUT)
                if int_in_global_and_local or int_out_global_and_local:
                    # Keine Abzweigung in Zelle nötig
                    shortest_distance = shortest_route_without_junction(start_obj[1], end_obj[1])
                elif int_local_and_local:
                    # Zwei Abzweigungen nötig, Pfad führt nicht über Storage Buffer
                    shortest_distance = shortest_route_two_junctions(start_obj[1], end_obj[1])
                else:
                    # Zwei Abzweigungen nötig, Pfad führt über Storage Buffer
                    shortest_distance = shortest_route_over_storage(start_obj[1], end_obj[1])
                self.DISTANCES.append((start_obj[0], end_obj[0], shortest_distance))

    def check_best_path(self, order, include_all=True):
        """Calculate the minimal amount of manufacturing cells needed to
         process this order completely in each tree branch"""
        child_results = []
        for child in self.CHILDS:
            child_results.append(child.check_best_path(order)) # Rekursiver Aufruf im Teilbaum. Speichere Ergebnisse der Kinder in Liste.
        child_results[:] = (value for value in child_results if value != 0)
        if child_results:
            return min(child_results) # Wenn Kinder Werte ausser 0 haben, gebe das Minimum zurueck
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
                        if self.all_tasks_included(order, alternative_tasks=combination_to_test) and len(subset) < min_combi:
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
