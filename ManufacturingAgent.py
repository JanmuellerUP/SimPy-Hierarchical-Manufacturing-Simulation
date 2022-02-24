import simpy
from Machine import Machine
from Buffer import *
import random
from Ruleset import RuleSet
import pandas as pd
from ProcessingStep import ProcessingStep
import threading
from Utils.log import write_log
from Utils.consecutive_performable_tasks import consecutive_performable_tasks
from Utils.devisions import div_possible_zero
import numpy as np

import time
import time_tracker


class ManufacturingAgent:
    instances = []

    def __init__(self, config: dict, env: simpy.Environment, position, ruleset_id=None):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None
        self.lock = None

        # Attributes
        self.RULESET = None
        for ruleset in RuleSet.instances:
            if ruleset.id == ruleset_id:
                self.RULESET = ruleset  # Reference to the priority ruleset of the agent
                break

        if not self.RULESET:  # Check if the Agent has a Ruleset selected
            raise Exception("Atleast one Agent has no ruleset defined. Please choose a ruleset or the agent wont do anything!")

        self.CELL = None
        self.PARTNER_AGENTS = None  # Other Agents within the same Cell
        self.SPEED = config["AGENT_SPEED"]  # Configured moving speed of the agent: How much distance can be moved within one time points
        self.LONGEST_WAITING_TIME = config["AGENT_LONGEST_WAITING_TIME"]  # Configured time after which the agent stops its current waiting task if nothing happend
        self.TIME_FOR_ITEM_PICK_UP = config["TIME_FOR_ITEM_PICK_UP"]
        self.TIME_FOR_ITEM_STORE = config["TIME_FOR_ITEM_STORE"]

        # State
        self.moving = False # Is the agent currently moving from one position to another?
        self.position = position # Position object of the agent, None if agent is currently moving
        self.position.agents_at_position.append(self)
        self.next_position = None # Destination if agent is currently moving
        self.moving_time = 0  # How long does it take the agent to perform the whole route
        self.moving_start_time = None  # When did the agent start moving
        self.moving_start_position = None  # Where did the agent start moving
        self.remaining_moving_time = 0  # How much moving time of the current route is remaining
        self.moving_end_time = None  # Estimated Time point on which the agent will arrive

        self.waiting = False  # Agent has an active waiting task, only interruptable by the position or after a specific time passed (LONGEST_WAITING_TIME)
        self.has_task = False  # Has the agent an active task it performs? Waiting counts as task...

        self.locked_item = None  # Item locked by this agent. Locked items are not interactable by other agents
        self.picked_up_item = None  # Item the agent is holding, only one at a time

        self.started_tasks = 0  # Amount of started tasks

        # Current tasks
        self.current_task = None  # The current task the agent is performing
        self.current_subtask = None  # Current subtask the agent is performing (Subtasks are part of the current task e.g. "move to position x" as part of "bring item y from z to x")
        self.current_waitingtask = None  # Current waiting task. Agents starts waiting task if its subtask/task cant be performed currently (e.g. wait for processing of item in machine)

        self.__class__.instances.append(self)
        self.logs = []
        self._excluded_keys = ["logs", "_excluded_keys", "env", "RULESET", "SPEED", "INVENTORY_SPACE", "CELL", "_continuous_attributes"]  # Attributes excluded from log
        self._continuous_attributes = ["remaining_moving_time"]

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

    def occupancy(self, requester=None):
        if requester == self:
            pos_type = "Agent - Self"
        else:
            pos_type = "Agent"

        if self.picked_up_item:
            return [{"order": self.picked_up_item, "pos": self, "pos_type": pos_type}]
        else:
            return [{"order": None, "pos": self, "pos_type": pos_type}]

    def main_process(self):
        """Main process of the agent. Decisions about its behavior are made in this process.
        Endless loop: Interruptable with self.recalculate(self.main_proc).
        """
        self.lock.acquire()

        # Get state of cell and orders inside this cell
        state_calc_start = time.time()
        cell_state = self.CELL.get_cell_state(requester=self)
        time_tracker.time_state_calc += time.time() - state_calc_start

        # For each order in state add the destination if this order would be chosen
        dest_calc_start = time.time()
        cell_state["_destination"] = cell_state.apply(self.add_destinations, axis=1)
        time_tracker.time_destination_calc += time.time() - dest_calc_start

        if self.RULESET.dynamic:
            next_task, next_order = self.get_smart_action(cell_state)
        else:
            next_task, next_order = self.get_action(cell_state)

        # Perform next task if there is one
        if next_task:
            self.current_task = next_task
            self.has_task = True
            self.save_event("start_task")
            self.started_tasks += 1

            if next_order:
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

    def get_action(self, order_state):

        useable_orders = order_state.loc[np.where((order_state["order"].notnull()) & (order_state["locked"] == 0)
                                         & (order_state["in_m_input"] == 0) & (order_state["in_m"] == 0) & order_state["in_same_cell"] == 1)]

        if useable_orders.empty:
            return None, None

        useable_with_free_destination = useable_orders[useable_orders["_destination"] != -1]

        if useable_with_free_destination.empty:
            return None, None

        elif len(useable_with_free_destination) == 1:
            next_order = useable_with_free_destination["order"].iat[0]

        elif self.RULESET.random:  # When Ruleset is random...
            ranking = useable_with_free_destination.sample(frac=1, random_state=self.RULESET.seed).reset_index(drop=True)
            next_order = useable_with_free_destination["order"].iat[0]

        else:
            criteria = [criteria["measure"] for criteria in self.RULESET.numerical_criteria]

            ranking = useable_with_free_destination[["order"] + criteria]

            for criterion in self.RULESET.numerical_criteria:
                weight = criterion["weight"]
                measure = criterion["measure"]
                order = criterion["ranking_order"]

                # Min Max Normalisation
                if order == "ASC":
                    ranking["WS-" + measure] = weight * div_possible_zero((ranking[measure] - ranking[measure].min()), (ranking[measure].max() - ranking[measure].min()))
                else:
                    ranking["WS-" + measure] = weight * (1 - div_possible_zero(
                        (ranking[measure] - ranking[measure].min()),
                        (ranking[measure].max() - ranking[measure].min())))

            order_scores = ranking.filter(regex="WS-")
            ranking["Score"] = order_scores.sum(axis=1)
            ranking.sort_values(by=["Score"], inplace=True)

            next_order = ranking["order"].iat[0]

        destination = useable_with_free_destination[useable_with_free_destination["order"] == next_order].reset_index(drop=True).loc[0, "_destination"]

        if destination:
            return self.env.process(self.item_from_to(next_order, next_order.position, destination)), next_order
        else:
            return None, next_order

    def get_smart_action(self, order_state):
        # Remove order column
        # Action space are potential slots + None for waiting
        # Get position for task
        # Rewards after task was completed
        return 0

    def calculate_destination(self, order):
        """Calculate the best next position for an agent to bring the order"""

        # Check if order is currently at a machine. If so the next task of the order is the one after the current one

        next_processing_step = order.next_task
        next_steps = order.remaining_tasks
        destination = None

        # Bring finished orders and orders that can not be performed in this cell always to the cell output buffer
        if order.tasks_finished or next_processing_step not in [task for (task, amount) in self.CELL.PERFORMABLE_TASKS if amount > 0]:
            if self.CELL.OUTPUT_BUFFER.free_slots():
                destination = self.CELL.OUTPUT_BUFFER
            elif self.CELL.STORAGE.free_slots():
                destination = self.CELL.STORAGE

        # Order is in machine cell
        elif self.CELL.MACHINES:

            potential_machines = [(machine, machine.item_in_input, machine.item_in_machine, len(machine.expected_orders), machine.current_setup) for machine in self.CELL.MACHINES if
                                  next_processing_step == machine.PERFORMABLE_TASK]

            optimal_machines = [machine for (machine, item_input, item_machine, expected_orders, setup) in potential_machines if item_input is None and expected_orders == 0 and setup == order.type]

            if len(optimal_machines) > 0:
                destination = optimal_machines[0]

            else:

                free_machines = [machine for (machine, item_input, item_machine, expected_orders, setup) in potential_machines if item_input is None and expected_orders == 0]
                if len(free_machines) > 0:
                    destination = free_machines[0]

            if destination is None:
                if self.CELL.STORAGE.free_slots():
                    destination = self.CELL.STORAGE

        else:
            # Order is in distribution cell

            possibilities = []

            for cell in self.CELL.CHILDS:
                possibilities.append((cell, cell.check_best_path(order, include_all=False), cell.PERFORMABLE_TASKS))
            best_possibilities = sorted([(cell, shortest_path, cell.INPUT_BUFFER.free_slots()) for (cell, shortest_path, performable_tasks) in possibilities if shortest_path], key=lambda tup: tup[1])

            if best_possibilities:
                destination = [cell.INPUT_BUFFER for (cell, shortest_path, free_slots) in best_possibilities if free_slots][0]
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
                    destination = best_cell.INPUT_BUFFER

        return destination

    def add_destinations(self, data):

        useable_order = (pd.notnull(data["order"])) and (data["locked"] == 0) and (data["in_m_input"] == 0) and (
                    data["in_m"] == 0)

        if useable_order:
            return self.calculate_destination(data["order"])

        return -1

    def moving_proc(self, destination, announce=False):
        """SUBTASK: Agent is moving to its target position.
        After destination is reached: Call store_item if an item was held, else stop."""

        # Statechanges
        announced = False

        if isinstance(destination, Machine) and self.picked_up_item:
            if self.picked_up_item.next_task != destination.PERFORMABLE_TASK:
                print("Warning:", self, self.picked_up_item, self.picked_up_item.next_task, destination,
                      destination.PERFORMABLE_TASK)

        if self.position:
            if not self.moving and self.position != destination:
                self.position.agents_at_position.remove(self)
                self.moving = True
                self.moving_start_position = self.position
                self.moving_start_time = self.env.now
                self.next_position = destination
                self.moving_time = self.time_for_distance(destination)
                self.remaining_moving_time = self.moving_time
                self.moving_end_time = self.moving_start_time + self.moving_time
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
                self.moving_end_time = self.env.now + self.remaining_moving_time
            self.moving = True

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
        self.moving_end_time = None
        self.position = self.next_position
        self.next_position = None
        self.position.agents_at_position.append(self)
        if self.picked_up_item:
            self.picked_up_item.position = self.position
            self.picked_up_item.save_event("transportation_end")
        self.save_event("moving_end")

        self.current_subtask = None

    def pick_up(self, item):
        """SUBTASK: Pick up item from position if inventory is empty"""
        #print(self, self.position == item.position)
        if self.picked_up_item is None:
            if isinstance(self.position, Machine):
                if self.position.item_in_output != item:
                    #print(self.position,"Agent begins to wait", self.env.now, item, item.position, self.position.item_in_input, self.position.item_in_machine, self.position.item_in_output)
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
                    self.position.save_event("item_picked_up")

            if isinstance(self.position, Buffer):
                #print(self, "Position Buffer", item, item.locked_by==self, self.position.items_in_storage)
                if item in self.position.items_in_storage:
                    self.save_event("pick_up_start")
                    yield self.env.timeout(self.TIME_FOR_ITEM_PICK_UP)
                    self.picked_up_item = item
                    item.picked_up_by = self
                    self.position.item_picked_up(item)
                    item.position = None
                    item.save_event("picked_up")
                    self.save_event("pick_up_end")

        self.CELL.inform_agents()
        self.current_subtask = None

    def store_item(self):
        """SUBTASK: Put down item and inform Position"""

        item = self.picked_up_item
        if isinstance(self.position, Machine):
            if self.position.item_in_input or self.position.input_lock: # Position besetzt
                self.current_waitingtask = self.env.process(self.wait_for_free_slot())
                yield self.current_waitingtask
                #print(self, "MARKER1", self.picked_up_item)
                self.current_subtask = self.env.process(self.store_item())
                yield self.current_subtask
                return
            else:
                self.save_event("store_item_start")

                if self.picked_up_item.next_task is not self.position.PERFORMABLE_TASK:
                    raise Exception("Placed item in wrong machine. Next task can not be performed by this machine!", self.picked_up_item, self.position, self)

                self.position.input_lock = True
                yield self.env.timeout(self.TIME_FOR_ITEM_STORE)
                self.position.input_lock = False

                self.position.expected_orders.remove(
                    [(order, time, agent) for order, time, agent in self.position.expected_orders if
                     order == item][0])

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

                self.position.expected_orders.remove(
                    [(order, time, agent) for order, time, agent in self.position.expected_orders if order == item][0])

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
                        self.CELL.inform_agents()

                self.position.save_event("item_stored", item)
            else: # Position besetzt

                self.current_waitingtask = self.env.process(self.wait_for_free_slot())
                yield self.current_waitingtask

                self.current_subtask = self.env.process(self.store_item())
                yield self.current_subtask
                return

        self.picked_up_item = None
        item.picked_up_by = None
        self.current_subtask = None
        item.save_event("put_down")
        self.save_event("store_item_end")
        self.position.save_event("item_stored")

    def wait_for_item_processing(self, item, pos):
        """SUBTASK: Endless loop. Wait for an item to be processed by a machine. Remove waiting agent from order after interruption"""
        try:
            item.waiting_agent_pos.append((self, pos))
            self.waiting = True
            self.save_event("wait_for_processing_start")
            while True:
                yield self.env.timeout(100000)
        except simpy.Interrupt as interruption:
            #print("Interrupt waiting agent at", self.position, self.env.now)
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

            while True:
                yield self.env.timeout(100000)
        except simpy.Interrupt as interruption:
            self.current_waitingtask = None
            self.waiting = False
            self.position.waiting_agents.remove(self)
            self.save_event("wait_for_slot_end")
            #print(self, "interrupted waiting task", interruption)

    def item_from_to(self, item, from_pos, to_pos):
        """TASK: Get an item from position and put it down on another position within the same cell"""

        if self.position != from_pos:
            self.current_subtask = self.env.process(self.moving_proc(from_pos))
            yield self.current_subtask
        if isinstance(from_pos, Machine) and from_pos != to_pos:
            if item is not from_pos.item_in_output:
                item.waiting_agent = (self, from_pos)
                self.current_waitingtask = self.env.process(self.wait_for_item_processing(item, from_pos))
                yield self.current_waitingtask
        if not self.picked_up_item:
            self.current_subtask = self.env.process(self.pick_up(item))
            yield self.current_subtask
        self.current_subtask = self.env.process(self.moving_proc(to_pos, announce=True))
        yield self.current_subtask
        self.current_subtask = self.env.process(self.store_item())
        yield self.current_subtask

        item.locked_by = None
        item.save_event("unlocked")
        self.locked_item = None
        self.current_task = None
        self.CELL.inform_agents()
        if item.current_cell is not self.CELL and item.current_cell:
            item.current_cell.inform_agents()

    def time_for_distance(self, destination):
        """Calculate the needed Time for a given route"""

        if not destination:
            raise Exception("Time for distance: Can not calculate the distance to destination None")

        def get_time(start_pos, end_pos):
            if start_pos == end_pos:
                return 0
            for start, end, length in self.CELL.DISTANCES:
                if start == start_pos and end == end_pos:
                    return length / self.SPEED

        if self.position:
            if destination == self.position:
                return 0
            else:
                return get_time(self.position, destination)

    def state_change_in_cell(self):
        if not self.main_proc.is_alive:
            self.main_proc = self.env.process(self.main_process())
