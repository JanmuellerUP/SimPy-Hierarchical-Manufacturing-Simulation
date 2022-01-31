import simpy
from Machine import Machine
from Buffer import *
import random
from Ruleset import RuleSet
import pandas as pd
import threading
from Utils.log import write_log
from Utils.consecutive_performable_tasks import consecutive_performable_tasks


class ManufacturingAgent:
    instances = []

    def __init__(self, env: simpy.Environment, config: dict, position, ruleset_id=None):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None
        self.lock = None

        # Attributes
        self.RULESET = None
        for ruleset in RuleSet.instances:
            if ruleset.id == ruleset_id:
                self.RULESET = ruleset  # Reference to the priority ruleset of the agent
                break
        self.CELL = None
        self.PARTNER_AGENTS = None  # Other Agents within the same Cell
        self.SPEED = config["AGENT_SPEED"]  # Configured moving speed of the agent: How much distance can be moved within one time points
        self.LONGEST_WAITING_TIME = config["AGENT_LONGEST_WAITING_TIME"]  # Configured time after which the agent stops its current waiting task if nothing happend
        self.TIME_FOR_ITEM_PICK_UP = config["TIME_FOR_ITEM_PICK_UP"]
        self.TIME_FOR_ITEM_STORE = config["TIME_FOR_ITEM_STORE"]

        # State
        self.moving = False # Is the agent currently moving from one position to another?
        self.position = position # Position object of the agent, None if agent is currently moving
        self.next_position = None # Destination if agent is currently moving
        self.moving_time = 0  # How long does it take the agent to perform the whole route
        self.moving_start_time = None  # When did the agent start moving
        self.moving_start_position = None  # Where did the agent start moving
        self.remaining_moving_time = 0  # How much moving time of the current route is remaining

        self.waiting = False  # Agent has an active waiting task, only interruptable by the position or after a specific time passed (LONGEST_WAITING_TIME)
        self.has_task = False  # Has the agent an active task it performs? Waiting counts as task...

        self.locked_item = None  # Item locked by this agent. Locked items are not interactable by other agents
        self.picked_up_item = None  # Item the agent is holding, only one at a time

        self.started_prio_tasks = 0  # Amount of started tasks because of defined priority tasks
        self.started_normal_tasks = 0  # Amount of started tasks because of ranking by agents ruleset

        # Current tasks
        self.current_task = None  # The current task the agent is performing
        self.current_subtask = None  # Current subtask the agent is performing (Subtasks are part of the current task e.g. "move to position x" as part of "bring item y from z to x")
        self.current_waitingtask = None  # Current waiting task. Agents starts waiting task if its subtask/task cant be performed currently (e.g. wait for processing of item in machine)

        self.__class__.instances.append(self)
        self.logs = []
        self._excluded_keys = ["logs", "_excluded_keys", "env", "RULESET", "SPEED", "INVENTORY_SPACE", "CELL"]  # Attributes excluded from log

        self.env.process(self.initial_event())  # Write initial event in event log when simulation starts
        self.main_proc = self.env.process(self.main_process())  # Initialize first main process of the agent when simulation starts

    def save_event(self, event_type: str, next_position=None, travel_time=None):
        db = self.SIMULATION_ENVIRONMENT.db_con
        cursor = self.SIMULATION_ENVIRONMENT.db_cu

        time = self.env.now

        if next_position:
            nxt_pos = id(next_position)
        else:
            nxt_pos = None

        if self.position:
            pos = id(self.position)
        else:
            pos = None

        if self.picked_up_item:
            pui = id(self.picked_up_item)
        else:
            pui = None

        if self.locked_item:
            locki = id(self.locked_item)
        else:
            locki = None

        cursor.execute("INSERT INTO agent_events VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (id(self), time, event_type, nxt_pos, travel_time, self.moving, self.waiting, self.has_task, pos, pui, locki))
        db.commit()

    def initial_event(self):
        self.save_event("Initial")
        yield self.env.timeout(0)

    def end_event(self):
        self.save_event("End_of_Time")

    def recalculate(self):
        """Interrupt the main process and start the it again afterwards, to calculate next steps"""
        if self.main_proc:
            if self.main_proc.is_alive:
                #print("Recalculate ", self, "at", self.env.now, "Current tasks", self.main_proc, self.current_task, self.current_subtask, self.current_waitingtask)
                self.main_proc.interrupt("Recalculate")
            else:
                self.main_proc = self.env.process(self.main_process())
        else:
            self.main_proc = self.env.process(self.main_process())

    def main_process(self):
        """Main process of the agent. Decisions about its behavior are made in this process.
        Endless loop: Interruptable with self.recalculate(self.main_proc).
        """
        try:
            # Check for priority tasks (Free Input, Blocked Items in machines)
            self.lock.acquire()
            #print("New Main Process", self, self.env.now, self.current_task, self.current_subtask, self.current_waitingtask)
            cell_states = self.CELL.calculate_states(requester=self)

            if not self.picked_up_item:
                ranking = self.rank_order(cell_states)
                prio_task, prio_order = self.check_priority_tasks(cell_states, ranking)

                # Prefer priority tasks over normal tasks
                if prio_task:
                    next_task = prio_task
                    next_order = prio_order
                    task_type = "prio"
                else:
                    next_task, next_order = self.get_next_task(ranking)
                    task_type = "normal"

            else:
                next_task, next_order = self.get_next_task([self.picked_up_item])
                task_type = "continue"

            # Perform next task if there is one
            if next_task:
                self.has_task = True
                if task_type == "normal":
                    self.save_event("start_normal_task")
                    self.started_normal_tasks += 1
                elif task_type == "prio":
                    self.save_event("start_prio_task")
                    self.started_prio_tasks += 1

                if next_order:
                    #print("LOCK", self.env.now, self, next_order, "Bisher gelockt:", self.locked_item)
                    next_order.locked_by = self
                    self.locked_item = next_order
                    self.locked_item.save_event("locked")

                self.lock.release()
                yield next_task
                self.has_task = False
                self.save_event("end_of_main_process")
                self.main_proc = self.env.process(self.main_process())

            if self.lock.locked():
                self.lock.release()

        except simpy.Interrupt as interruption:
            #print("Interruption von main_proc", self, self.env.now)
            if self.current_task:
                #print("Send Interuption to current task", self, self.env.now)
                self.current_task.interrupt("Anweisung von Main Thread")
                yield self.current_task
            elif self.current_subtask:
                if self.current_subtask.generator.__name__ == "moving_proc":
                    #print("Send Interuption to current moving subtask", self, self.env.now)
                    self.current_subtask.interrupt("Anweisung von Main Thread")
                    yield self.current_subtask
                else:
                    #print("Wait for current subtask to end", self, self.env.now)
                    yield self.current_subtask
            #print("Interruption von main proc finished", self, self.env.now,"\n")

            self.has_task = False
            #print("Start new main process", self, self.env.now, self.main_proc, self.current_task, self.current_subtask, self.current_waitingtask)
            self.save_event("end_of_main_process_interruption")
            self.main_proc = self.env.process(self.main_process()) # Start new Main Process

    def check_priority_tasks(self, state, ranking):
        expected_orders = state["expected_orders"]

        # Keep Input-Buffer free
        capacity = self.CELL.INPUT_BUFFER.STORAGE_CAPACITY
        used_slots = state["input_buffer"][1]["items_in_storage"]
        if used_slots:
            locked_in_used_slots = [order for order in used_slots if order.locked_by]
        else:
            locked_in_used_slots = []
        expected_orders_input = len([order for (order, time, position, agent) in expected_orders if position is self.CELL.INPUT_BUFFER])
        if capacity == 1:
            input_overcrowded = capacity == len(used_slots) - len(locked_in_used_slots)
        else:
            input_overcrowded = capacity <= len(used_slots) + expected_orders_input - len(locked_in_used_slots)

        # Keep Machine Output free
        blocked_machines = []
        high_blocks = []
        low_blocks = []

        if self.CELL.MACHINES:
            blocked_machines = [machine for machine in self.CELL.MACHINES if machine.wait_for_output_proc]
            if blocked_machines:
                high_blocks = [machine for machine in blocked_machines if machine.item_in_input and machine.item_in_machine and not machine.item_in_output.locked_by]
                low_blocks = [machine for machine in blocked_machines if machine not in high_blocks and not machine.item_in_output.locked_by]

        # Keep Interface Out free
        blocked_interfaces = []

        if self.CELL.INTERFACES_OUT:
            state_interfaces_out = state["interfaces_out"]
            interfaces_out = [(interface, data["STORAGE_CAPACITY"], data["items_in_storage"], len(
                [order for (order, time, position, agent) in expected_orders if position is interface])) for (interface, data) in state_interfaces_out]
            for interface, capacity, used_slots, num_expected_orders in interfaces_out:
                if used_slots:
                    locked_in_used_slots = [order for order in used_slots if order.locked_by]
                else:
                    locked_in_used_slots = []
                interface_overcrowded = capacity <= len(used_slots) + num_expected_orders - len(locked_in_used_slots)
                if interface_overcrowded:
                    blocked_interfaces.append(interface)

        # Which priority task should be performed?
        free_output_capacity = self.CELL.OUTPUT_BUFFER.STORAGE_CAPACITY - len(state["output_buffer"][1]["items_in_storage"])
        if free_output_capacity > 0:
            if high_blocks or low_blocks:
                task, order = self.remove_machine_block(high_blocks + low_blocks, ranking)
            elif blocked_interfaces:
                task, order = self.free_interface_space(blocked_interfaces, ranking)
            elif input_overcrowded:
                task, order = self.free_input_space(ranking, high_blocks + low_blocks, blocked_interfaces)
            else:
                task = None
                order = None
        else:
            if input_overcrowded:
                task, order = self.free_input_space(ranking, high_blocks + low_blocks, blocked_interfaces)
            elif blocked_interfaces:
                task, order = self.free_interface_space(blocked_interfaces, ranking)
            elif high_blocks or low_blocks:
                task, order = self.remove_machine_block(high_blocks + low_blocks, ranking)
            else:
                task = None
                order = None
        return task, order

    def free_input_space(self, ranking, blocked_machines, blocked_interfaces):

        if self.CELL.STORAGE.STORAGE_CAPACITY > len(self.CELL.STORAGE.items_in_storage):
            # Storage has free Spaces
            next_item = [order for order in ranking if order in self.CELL.INPUT_BUFFER.items_in_storage][-1]
            self.current_task = self.env.process(self.item_from_to(next_item, next_item.position, self.CELL.STORAGE))
            return self.current_task, next_item
        else:
            # Storage full
            next_items = [(order, self.calculate_destination(order)) for order in ranking if order in self.CELL.INPUT_BUFFER.items_in_storage]
            for item in next_items:
                order, data = item
                destination, free_slot = data
                if free_slot:
                    self.current_task = self.env.process(self.item_from_to(order, order.position, destination))
                    return self.current_task, order
        if blocked_machines:
            return self.remove_machine_block(blocked_machines, ranking)
        elif blocked_interfaces:
            return self.free_interface_space(blocked_interfaces, ranking)
        else:
            return None, None

    def free_interface_space(self, blocks, ranking):
        blocking_items = []
        for interface in blocks:
            blocking_items += interface.items_in_storage
        blocking_items_ranked = [item for item in ranking if item in blocking_items]

        # Case 1: Cell output free and finished item blocking other items
        if self.CELL.OUTPUT_BUFFER.STORAGE_CAPACITY > len(self.CELL.OUTPUT_BUFFER.items_in_storage):
            for item in blocking_items_ranked:
                if item.tasks_finished or item.next_task not in [task for (task, amount) in
                                                                   self.CELL.PERFORMABLE_TASKS]:
                    self.current_task = self.env.process(self.item_from_to(item, item.position, self.CELL.OUTPUT_BUFFER))
                    return self.current_task, item

        # Case 2: Any Order in output has a free potential position
        for item in blocking_items_ranked:
            destination, free_slot = self.calculate_destination(item)
            if free_slot:
                self.current_task = self.env.process(self.item_from_to(item, item.position, destination))
                return self.current_task, item

        # Case 3: Free slot in storage buffer
        if self.CELL.STORAGE.STORAGE_CAPACITY > len(self.CELL.STORAGE.items_in_storage):
            prio_item = blocking_items_ranked[-1]
            self.current_task = self.env.process(self.item_from_to(prio_item, prio_item.position, self.CELL.STORAGE))
            return self.current_task, prio_item

        # Special Case: Can not free block in Interface! Try to free storage space!
        return self.free_storage_space(ranking, blocking_items_ranked)

    def remove_machine_block(self, blocks, ranking):
        blocking_items = [machine.item_in_output for machine in blocks]
        blocking_items_ranked = [item for item in ranking if item in blocking_items]

        # Case 1: Cell output free and finished item blocking other items
        if self.CELL.OUTPUT_BUFFER.STORAGE_CAPACITY > len(self.CELL.OUTPUT_BUFFER.items_in_storage):
            # Prüfe ob eines der blockierenden Items fertiggestellt ist
            for item in blocking_items_ranked:
                if item.tasks_finished or item.next_task not in [task for (task, amount) in
                                                                   self.CELL.PERFORMABLE_TASKS]:
                    self.current_task = self.env.process(self.item_from_to(item, item.position, self.CELL.OUTPUT_BUFFER))
                    return self.current_task, item

        # Case 2: Any Order in output has a free potential position
        for item in blocking_items_ranked:
            destination, free_slot = self.calculate_destination(item)
            if free_slot:
                self.current_task = self.env.process(self.item_from_to(item, item.position, destination))
                return self.current_task, item

        # Case 3: Free slot in storage buffer
        if self.CELL.STORAGE.STORAGE_CAPACITY > len(self.CELL.STORAGE.items_in_storage):
            blocked_items = [machine.item_in_machine for machine in blocks] + [machine.item_in_input for machine in blocks if machine.item_in_input]
            blocked_items_ranked = [order for order in ranking if order in blocked_items]
            prio_item = blocked_items_ranked[0].position.item_in_output

            self.current_task = self.env.process(self.item_from_to(prio_item, prio_item.position, self.CELL.STORAGE))
            return self.current_task, prio_item

        # Special Case: Can not free block in Machine! Try to free storage space!
        return self.free_storage_space(ranking, blocking_items_ranked)

    def free_storage_space(self, ranking, blocking_items):
        storage_items_ranked = [item for item in ranking if item in self.CELL.STORAGE.items_in_storage]
        for order in storage_items_ranked:
            destination, free_slot = self.calculate_destination(order)
            if free_slot:
                self.current_task = self.env.process(self.item_from_to(order, order.position, destination))
                return self.current_task, order

        # Storage can not be cleared. Move to position of best blocking item
        for item in blocking_items:
            if item.tasks_finished or item.next_task not in [task for (task, amount) in
                                                             self.CELL.PERFORMABLE_TASKS]:

                self.current_subtask = self.env.process(self.moving_proc(item.position))
                return self.current_subtask, None

        self.current_subtask = self.env.process(self.moving_proc(blocking_items[0].position))
        return self.current_subtask, None

    def calculate_destination(self, order):

        if isinstance(order.position, Machine):
            if (
                    order == order.position.item_in_input or order == order.position.item_in_machine) and order.next_task == order.position.PERFORMABLE_TASK:
                if len(order.remaining_tasks) > 1:
                    next_processing_step = order.remaining_tasks[1]
                    next_steps = order.remaining_tasks[1:]
                    tasks_finished = False
                else:
                    next_processing_step = None
                    next_steps = []
                    tasks_finished = True
            else:
                next_processing_step = order.next_task
                next_steps = order.remaining_tasks
                tasks_finished = False
        else:
            next_processing_step = order.next_task
            next_steps = order.remaining_tasks

            tasks_finished = False

        if order.tasks_finished or tasks_finished or next_processing_step not in [task for (task, amount) in self.CELL.PERFORMABLE_TASKS if amount > 0]:
            destination = self.CELL.OUTPUT_BUFFER
            free_slot = len(destination.items_in_storage) < destination.STORAGE_CAPACITY
            return destination, free_slot
        elif self.CELL.MACHINES:

            potential_machines = [machine for machine in self.CELL.MACHINES if
                                  next_processing_step == machine.PERFORMABLE_TASK]

            potential_times = sorted([(machine, machine.item_in_input, machine.calculate_processing_time(order, next_processing_step)) for machine
                               in potential_machines], key=lambda tup: tup[2])

            destination = [machine for (machine, item_in_input, processing_time) in potential_times if not item_in_input]
            free_slot = True
            if not destination:
                destination = potential_times[0][0]
                free_slot = False
                return destination, free_slot

            return destination[0], free_slot

        else:
            #Distributionszelle
            possibilities = []
            for cell in self.CELL.CHILDS:
                possibilities.append((cell, cell.check_best_path(order, include_all=False), cell.PERFORMABLE_TASKS))
            best_possibilities = sorted([(cell, shortest_path, cell.INPUT_BUFFER.STORAGE_CAPACITY - len(cell.INPUT_BUFFER.items_in_storage)) for (cell, shortest_path, performable_tasks) in possibilities if shortest_path], key=lambda tup: tup[1])
            if best_possibilities:
                destination = [cell for (cell, shortest_path, free_spaces) in best_possibilities if free_spaces > 0]
                free_slot = True
            else:
                # Prefer the one that can perform the most continuous tasks and has a free Input Slot.
                result = [(cell, consecutive_performable_tasks(next_steps, performable_tasks)) for (cell, shortest_path, performable_tasks) in possibilities]
                result = sorted([(cell, amount) for (cell, amount) in result if amount > 0], key=lambda tup: tup[1], reverse=True)
                if result:
                    best_cell, amount = result[0]
                    for cell, amount in result:
                        if not cell.INPUT_BUFFER.full:
                            best_cell = cell
                            break
                    return best_cell.INPUT_BUFFER, not best_cell.INPUT_BUFFER.full
            if not destination:
                destination = possibilities[0][0].INPUT_BUFFER
                free_slot = False
                return destination, free_slot
            return destination[0].INPUT_BUFFER, free_slot

    def rank_order(self, cell_state):
        """Calculate a ranking for current orders
        in this cell. Use the criteria set in the ruleset of the agent."""

        local_qualified_orders = [(order, attributes) for (order, attributes) in cell_state['orders_currently_in_cell'] if
                                  not attributes['locked_by'] and not attributes['picked_up_by']]

        if local_qualified_orders:

            if not self.RULESET: # Check if the Agent has a Ruleset selected
                print("Atleast one Agent has no ruleset defined. Please choose a ruleset or the agent wont do anything!")
                return []

            elif self.RULESET.random: # When Ruleset is random...
                random.seed(self.RULESET.seed)
                random.shuffle(local_qualified_orders)

                return [order for (order, attributes) in local_qualified_orders]

            else: # Ruleset selected and not random

                def calculate_criteria(df_row, measure: str):
                    order = df_row["Order"]
                    attributes = df_row["Attributes"]
                    try:
                        return attributes[measure]
                    except:
                        raise Exception("Criteria " + measure + " can not be calculated!")

                def add_normalized_score(df: pd.DataFrame, measure: str, weight, r_order):
                    if r_order == "DESC":
                        df["S" + measure] = 1 - (df[measure] - df[measure].min()) / (
                                    df[measure].max() - df[measure].min())

                    else:
                        df["S-" + measure] = (df[measure] - df[measure].min()) / (df[measure].max() - df[measure].min())
                    df["WS-" + measure] = weight * df["S-" + measure]
                    return df

                local_qualified_orders = pd.DataFrame(local_qualified_orders, columns=["Order", "Attributes"])  # Change array to df

                for criteria in self.RULESET.numerical_criteria:
                    m_title = criteria["measure"]
                    local_qualified_orders[m_title] = local_qualified_orders.apply(calculate_criteria, measure=m_title, axis=1)
                    local_qualified_orders = add_normalized_score(local_qualified_orders, m_title, criteria["weight"], criteria["ranking_order"])

                del local_qualified_orders["Attributes"]

                order_scores = local_qualified_orders.filter(regex="WS-")
                local_qualified_orders["Score"] = order_scores.sum(axis=1)
                pd.set_option('display.max_columns', None)
                local_qualified_orders.sort_values(by=["Score"], inplace=True)

                return list(local_qualified_orders["Order"])

        return []

    def get_next_task(self, ranking):
        """Check which Task should be performed next based on a ranked order list"""
        if ranking:
            next_order = ranking[0]
            destination, free_slot = self.calculate_destination(next_order)

            if next_order == self.picked_up_item:
                time, over_pos = self.time_for_distance(destination)
                if over_pos:
                    from_pos = over_pos
                else:
                    from_pos = self.position
                self.current_task = self.env.process(
                self.item_from_to(next_order, from_pos, destination, over_pos))
            else:
                self.current_task = self.env.process(self.item_from_to(next_order, next_order.position, destination))
            return self.current_task, next_order
        else:
            # There is currently no Order available
            position_next_item, item = self.CELL.get_position_of_next_expected_order()
            if position_next_item and position_next_item is not self.position:
                self.current_subtask = self.env.process(self.moving_proc(position_next_item))
            elif self.position != self.CELL.INPUT_BUFFER:
                self.current_subtask = self.env.process(self.moving_proc(self.CELL.INPUT_BUFFER))
            else:
                self.current_subtask = None
            return self.current_subtask, None

    def moving_proc(self, destination, announce=False):
        """SUBTASK: Agent is moving to its target position.
        After destination is reached: Call store_item if an item was held, else stop."""
        try:
            # Statechanges
            announced = False

            if isinstance(destination, Machine) and self.picked_up_item:
                if self.picked_up_item.next_task != destination.PERFORMABLE_TASK:
                    print("ALARM", self, self.picked_up_item, self.picked_up_item.next_task, destination,
                          destination.PERFORMABLE_TASK)

            if self.position:
                if not self.moving and self.position != destination:
                    self.position.agents_at_position.remove(self)
                    self.moving = True
                    self.moving_start_position = self.position
                    self.moving_start_time = self.env.now
                    self.next_position = destination
                    self.moving_time = self.time_for_distance(destination)[0]
                    self.remaining_moving_time = self.moving_time
                    if self.picked_up_item:
                        self.picked_up_item.position = None
                else:
                    return
                self.position = None

            else:
                if destination is self.moving_start_position:
                    #Turn around
                    next_pos = self.next_position
                    self.next_position = self.moving_start_position
                    self.moving_start_position = next_pos
                    self.moving_start_time = self.env.now - self.remaining_moving_time

                    self.remaining_moving_time = self.moving_time - self.remaining_moving_time

            if announce:
                #print(self, "Announce!")
                if self.picked_up_item and (isinstance(destination, Machine) or isinstance(destination, QueueBuffer)):
                    #print(self, self.env.now, "Append1", self.picked_up_item, destination)
                    destination.expected_orders.append(
                        (self.picked_up_item, self.env.now + self.remaining_moving_time, self))
                    announced = True
                elif self.picked_up_item and isinstance(destination, InterfaceBuffer):
                    if destination.upper_cell == self.CELL:
                        destination.lower_cell.inform_incoming_order(self, self.picked_up_item,
                                                                     self.env.now + self.remaining_moving_time + self.TIME_FOR_ITEM_STORE,
                                                                     destination)
                        #print(self, self.env.now, "Append2", self.picked_up_item, destination)
                        destination.expected_orders.append(
                            (self.picked_up_item, self.env.now + self.remaining_moving_time, self))
                        announced = True
                    elif destination.upper_cell is not None:
                        destination.upper_cell.inform_incoming_order(self, self.picked_up_item,
                                                                     self.env.now + self.remaining_moving_time + self.TIME_FOR_ITEM_STORE,
                                                                     destination)
                        #print(self, self.env.now, "Append3", self.picked_up_item, destination)
                        destination.expected_orders.append(
                            (self.picked_up_item, self.env.now + self.remaining_moving_time, self))
                        announced = True
                    else:
                        #print(self, self.env.now, "Append4", self.picked_up_item, destination)
                        destination.expected_orders.append(
                            (self.picked_up_item, self.env.now + self.remaining_moving_time, self))
                        announced = True

            # Perform moving (Wait remaining moving time and change status afterwards)
            self.save_event("moving_start", next_position=self.next_position, travel_time=self.remaining_moving_time)
            if self.picked_up_item:
                self.picked_up_item.save_event("transportation_start")
            yield self.env.timeout(self.remaining_moving_time)
            self.moving = False
            self.remaining_moving_time = 0
            self.moving_time = 0
            self.position = self.next_position
            self.next_position = None
            self.position.agents_at_position.append(self)
            if self.picked_up_item:
                self.picked_up_item.position = self.position
                self.picked_up_item.save_event("transportation_end")
            self.save_event("moving_end")

            self.current_subtask = None
        except simpy.Interrupt as interruption:
            self.moving = False
            moved_time = self.env.now - self.moving_start_time
            self.remaining_moving_time = self.remaining_moving_time - moved_time
            self.current_subtask = None

            if self.picked_up_item and announce and announced:
                #print(self, self.env.now, "REMOVE2", self.picked_up_item, destination)
                destination.expected_orders.remove([(order, time, agent) for order, time, agent in destination.expected_orders if agent == self][0])
                if isinstance(destination, InterfaceBuffer):
                    if destination.upper_cell == self.CELL:
                        destination.lower_cell.cancel_incoming_order(self.picked_up_item)
                    elif destination.upper_cell is not None:
                        destination.upper_cell.cancel_incoming_order(self.picked_up_item)
                if isinstance(destination, Machine):
                    destination.cancel_expected_order(self.picked_up_item)
            self.save_event("moving_interrupted")

    def pick_up(self, item):
        """SUBTASK: Pick up item from position if inventory is empty"""
        try:
            if self.picked_up_item is None:
                if isinstance(self.position, Machine):
                    if self.position.item_in_output != item:
                        self.current_waitingtask = self.env.process(self.wait_for_item_processing(item, self.position))
                        yield self.current_waitingtask
                    if self.position.item_in_output == item:
                        self.save_event("pick_up_start")
                        yield self.env.timeout(self.TIME_FOR_ITEM_PICK_UP)
                        self.picked_up_item = item
                        item.picked_up_by = self
                        item.position = None
                        self.position.item_in_output = None
                        if self.position.wait_for_output_proc:
                            self.position.wait_for_output_proc.interrupt("Output free again")
                        item.save_event("picked_up")
                        self.save_event("pick_up_end")

                if isinstance(self.position, Buffer):
                    #print(self, "Position Buffer", item, item.locked_by==self, self.position.items_in_storage)
                    if item in self.position.items_in_storage:
                        self.save_event("pick_up_start")
                        yield self.env.timeout(self.TIME_FOR_ITEM_PICK_UP)
                        self.picked_up_item = item
                        item.picked_up_by = self
                        self.position.items_in_storage.remove(item)
                        self.position.full = False
                        if len(self.position.waiting_agents) > 0:
                            self.position.waiting_agents[0].current_waitingtask.interrupt("New space free")
                        self.position.save_event("item_picked_up", item)
                        item.position = None
                        item.save_event("picked_up")
                        self.save_event("pick_up_end")
            self.CELL.recalculate_agents()
            self.current_subtask = None
        except simpy.Interrupt as interruption:
            self.current_subtask = None
            if self.current_waitingtask:
                self.current_waitingtask.interrupt("Interrupted by pick-up subtask")
            self.save_event("pick_up_interruption")

    def store_item(self):
        """SUBTASK: Put down item and inform Position"""
        try:
            item = self.picked_up_item
            if isinstance(self.position, Machine):
                if self.position.item_in_input: # Position besetzt
                    self.current_waitingtask = self.env.process(self.wait_for_free_slot())
                    yield self.current_waitingtask
                    #print(self, "MARKER1", self.picked_up_item)
                    self.current_subtask = self.env.process(self.store_item())
                    yield self.current_subtask
                    #print(self, "Neuer Store Auftrag abgeschlossen")
                    return
                else:
                    self.save_event("store_item_start")

                    if self.picked_up_item.next_task is not self.position.PERFORMABLE_TASK:
                        raise Exception("Placed item in wrong machine. Next task can not be performed by this machine!", self.picked_up_item, self.position, self)

                    yield self.env.timeout(self.TIME_FOR_ITEM_STORE)
                    #print("Store Item in Machine:", self, self.env.now, "ITEM:", self.picked_up_item, "Machine:", self.position.next_expected_order, self.position.expected_orders, "Plausibel:", self.picked_up_item == self.position.next_expected_order)
                    #print("Maschine", self.position.item_in_input, self.position.item_in_machine, self.position.setup, self.position.manufacturing, self.position.wait_for_item_proc)
                    #print(self, self.env.now, "REMOVE1", item, "from", self.position.expected_orders, self.position)
                    self.position.expected_orders.remove(
                        [(order, time, agent) for order, time, agent in self.position.expected_orders if
                         order == item][0])
                    #print(self, self.env.now, "RESULT:", self.position.expected_orders)
                    self.position.item_in_input = item
                    if self.position.wait_for_item_proc:
                        self.position.wait_for_item_proc.interrupt("Order arrived")
                    if item.waiting_agent_pos:

                        for agent, position in item.waiting_agent_pos:
                            if position == item.position:
                                agent.current_subtask.interrupt("Order is at position")
            elif isinstance(self.position, Buffer):
                if not self.position.full:
                    self.save_event("store_item_start")
                    yield self.env.timeout(self.TIME_FOR_ITEM_STORE)
                    #print("REMOVE1", item, self, self.position.expected_orders)
                    self.position.expected_orders.remove(
                        [(order, time, agent) for order, time, agent in self.position.expected_orders if order == item][0])
                    #print("RESULT", self.position.expected_orders)
                    self.position.items_in_storage.append(item)
                    if len(self.position.items_in_storage) == self.position.STORAGE_CAPACITY:
                        self.position.full = True
                    if isinstance(self.position, InterfaceBuffer):
                        item.save_event("cell_change")
                        self.CELL.remove_order_in_cell(item)
                        if self.position.upper_cell == self.CELL:
                            next_cell = self.position.lower_cell
                            next_cell.new_order_in_cell(item)

                        elif self.position.upper_cell is not None:
                            next_cell = self.position.upper_cell
                            item.current_cell = next_cell
                            next_cell.new_order_in_cell(item)

                        elif not self.position.upper_cell:
                            item.order_finished()
                            self.CELL.recalculate_agents()

                    self.position.save_event("item_stored", item)
                else: # Position besetzt
                    #print(self, "start waiting", self.picked_up_item)
                    self.current_waitingtask = self.env.process(self.wait_for_free_slot())
                    yield self.current_waitingtask
                    #print(self, "MARKER2", self.picked_up_item, self.env.now)
                    self.current_subtask = self.env.process(self.store_item())
                    yield self.current_subtask
                    #print(self, "Neuer Store Auftrag abgeschlossen")
                    return
            #print(self,"ITEM abgelegt!", self.env.now)
            self.picked_up_item = None
            item.picked_up_by = None
            self.current_subtask = None
            item.save_event("put_down")
            self.save_event("store_item_end")
        except simpy.Interrupt as interruption:
            self.save_event("store_item_interruption")
            self.current_subtask = None
            if self.current_waitingtask:
                self.current_waitingtask.interrupt("Interrupted by store-item subtask")

    def wait_for_item_processing(self, item, pos):
        """SUBTASK: Endless loop. Wait for an item to be processed by a machine. Remove waiting agent from order after interruption"""
        try:
            item.waiting_agent_pos.append((self, pos))
            self.waiting = True
            self.save_event("wait_for_processing_start")
            yield self.env.timeout(self.LONGEST_WAITING_TIME)
            self.waiting = False
            self.save_event("wait_for_processing_timeout")
            self.recalculate()
            while True:
                yield self.env.timeout(100000)
        except simpy.Interrupt as interruption:
            self.current_waitingtask = None
            self.waiting = False
            item.waiting_agent_pos.remove((self, pos))
            self.save_event("wait_for_processing_end")
            #print("interrupted waiting task", interruption)

    def wait_for_free_slot(self):
        """SUBTASK: Endless loop. Wait for an item slot at current position to be free again.
        Interruption removes waiting agent from position"""
        try:
            self.position.waiting_agents.append(self)
            self.waiting = True
            self.save_event("wait_for_slot_start")
            yield self.env.timeout(self.LONGEST_WAITING_TIME)
            self.waiting = False
            self.save_event("wait_for_slot_timeout")
            self.recalculate()
            while True:
                yield self.env.timeout(100000)
        except simpy.Interrupt as interruption:
            self.current_waitingtask = None
            self.waiting = False
            self.position.waiting_agents.remove(self)
            self.save_event("wait_for_slot_end")
            #print(self, "interrupted waiting task", interruption)

    def item_from_to(self, item, from_pos, to_pos, over_pos=None):
        """TASK: Get an item from position and put it down on another position within the same cell"""
        try:
            #print("FROM-TO:", self, item, from_pos, to_pos, over_pos)
            if over_pos:
                if over_pos == to_pos:
                    self.current_subtask = self.env.process(self.moving_proc(over_pos, announce=True))
                else:
                    self.current_subtask = self.env.process(self.moving_proc(over_pos))
                yield self.current_subtask

            if self.position != from_pos:
                self.current_subtask = self.env.process(self.moving_proc(from_pos))
                yield self.current_subtask
            if isinstance(from_pos, Machine):
                if item is not from_pos.item_in_output:
                    item.waiting_agent = (self, from_pos)
                    self.current_waitingtask = self.env.process(self.wait_for_item_processing(item, from_pos))
                    yield self.current_waitingtask
            if not self.picked_up_item:
                self.current_subtask = self.env.process(self.pick_up(item))
                yield self.current_subtask
                #print(self, "Picked up", self.picked_up_item, self.position, item.position, self.current_subtask, self.current_waitingtask)
            self.current_subtask = self.env.process(self.moving_proc(to_pos, announce=True))
            yield self.current_subtask
            #print(self, "MARKER3", self.picked_up_item, self.env.now)
            self.current_subtask = self.env.process(self.store_item())
            yield self.current_subtask

            #print("FROM-TO ENDED REGULAR:", self, item)
            #print("UNLOCK", self.env.now, self, self.locked_item)
            item.locked_by = None
            item.save_event("unlocked")
            self.locked_item = None
            self.current_task = None
            self.CELL.recalculate_agents()
            if item.current_cell is not self.CELL and item.current_cell:
                item.current_cell.recalculate_agents()
        except simpy.Interrupt as interruption:
            #print("FROM-TO ENDED INTERRUPTION:", self, item)
            #print("Interrupt item from to process", self, self.env.now, interruption)
            if self.current_subtask:
                if self.current_subtask.generator.__name__ == "moving_proc":
                    #print(self, "Interrupt current moving proc", self.env.now)
                    self.current_subtask.interrupt("Interrupted by Item-From-To task")
                elif not self.current_waitingtask:
                    #print(self, "Wait for current subtask to end", self.env.now)
                    yield self.current_subtask
                else:
                    # There is a current waiting task
                    #print(self, "interrupt waiting and subtask")
                    self.current_waitingtask.interrupt("Interrupted by Item-From-To task")
                    self.current_subtask.interrupt("Interrupted by Item-From-To task")
            elif self.current_waitingtask:
                #print(self, "Interrupt waiting")
                self.current_waitingtask.interrupt("Interrupted by Item-From-To task")

            self.current_task = None
            #print("UNLOCK", self.env.now, self, self.locked_item)
            self.locked_item.locked_by = None
            self.locked_item.save_event("unlocked")
            self.locked_item = None
            self.save_event("INTERRUPT ITEM_FROM_TO")
            #print(self, "Finished interruption of item from to", self.env.now, self.current_waitingtask, self.current_subtask, self.position, self.picked_up_item)

    def time_for_distance(self, destination):
        """Calculate the needed Time for a given route"""

        if not destination:
            return 0, None

        def get_distance(start_pos, end_pos):
            if start_pos == end_pos:
                return 0
            for start, end, length in self.CELL.DISTANCES:
                if start == start_pos and end == end_pos:
                    return length / self.SPEED

        if self.position:
            if destination == self.position:
                return 0, None
            else:
                return get_distance(self.position, destination), None
        else:
            over_positions = [(self.next_position, self.remaining_moving_time), (self.moving_start_position, self.moving_time - self.remaining_moving_time)]
            complete_distances = [(pos, dist_to_start + get_distance(pos, destination)) for pos, dist_to_start in over_positions]
            shortest_over, distance = min(complete_distances, key=lambda t: t[1])
            return distance, shortest_over

    def machine_failure(self):
        """Triggers recalculation of the agent. Called on machine failure in its cell"""
        self.recalculate()

    def state_change_in_cell(self, failure=False):
        if failure:
            #print("Agent Machine Failure", self)
            self.machine_failure()
        elif not self.main_proc.is_alive:
            self.main_proc = self.env.process(self.main_process())




