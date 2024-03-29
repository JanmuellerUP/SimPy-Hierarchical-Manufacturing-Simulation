"""Copyright 2022 Jannis Müller/ janmueller@uni-potsdam.de

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License."""

# -*- coding: utf-8 -*-
import json
from ProcessingStep import load_processing_steps, ProcessingStep
import simpy
from copy import copy
import numpy as np
import Machine
import matplotlib.pyplot as plt
from Utils.consecutive_performable_tasks import consecutive_performable_tasks


class Order:
    instances = []
    finished_instances = []

    def __init__(self, env: simpy.Environment, sim_env, start, due_to, urgency: int,
                 type, complexity=1):
        self.env = env
        self.SIMULATION_ENVIRONMENT = sim_env

        # Attributes
        self.type = type  # Type of order. New Types can be defined in Order_types.json.
        self.composition = self.type.composition  # Material composition of the order. Defined by order type.
        self.work_schedule = copy(self.type.work_schedule)  # The whole processing steps to be performed on this item to be completed
        self.start = start  # Time when the order arrived/will arrive
        self.starting_position = sim_env.main_cell.INPUT_BUFFER  # The position where the item will spawn once it started
        self.due_to = due_to  # Due to date of the order
        self.urgency = urgency  # Parameter that can be used to further rank orders
        self.complexity = complexity  # Numerical value, modifier for processing time within machines

        # State
        self.started = False
        self.overdue = False
        self.tasks_finished = False
        self.processing = False
        self.wait_for_repair = False
        self.completed = False
        self.completed_at = None
        self.remaining_tasks = copy(self.work_schedule)
        self.next_task = self.remaining_tasks[0]
        self.position = None
        self.current_cell = None
        self.in_cell_since = None  # Time when the item entered its current cell over the interface buffer
        self.picked_up_by = None  # The agent which picked up the item
        self.blocked_by = None  # Other order that might block the further processing of this order
        self.locked_by = None  # Locked by Agent X. A locked Order can´t be part of other agent tasks
        self.waiting_agent_pos = []  # Agent waiting for this order to be processed. Tuple: (agent, position)

        self.__class__.instances.append(self)
        self.result = None
        self._excluded_keys = ["logs", "_excluded_keys", "env", "SIMULATION_ENVIRONMENT", "work_schedule", "starting_positon", "waiting_agent_pos", "_continuous_attributes"]
        self._continuous_attributes = []

        self.env.process(self.set_order_overdue())

    def save_event(self, event_type: str):
        db = self.SIMULATION_ENVIRONMENT.db_con
        cursor = self.SIMULATION_ENVIRONMENT.db_cu

        time = self.env.now

        if self.blocked_by:
            blocked = True
        else:
            blocked = False

        if self.picked_up_by:
            picked_up = True
            picked_by = id(self.picked_up_by)
            transportation = self.picked_up_by.moving
        else:
            picked_up = False
            picked_by = None
            transportation = False

        if self.current_cell:
            cell = id(self.current_cell)
        else:
            cell = None

        if self.position:
            pos = id(self.position)
            pos_type = type(self.position).__name__
        else:
            pos = None
            pos_type = None

        if self.locked_by:
            lock_by = id(self.locked_by)
        else:
            lock_by = None

        tasks_remaining = len(self.remaining_tasks)

        cursor.execute("INSERT INTO item_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (id(self), time, event_type, self.started, self.overdue, blocked, self.tasks_finished,
                        self.completed, picked_up, transportation, self.processing, self.wait_for_repair, tasks_remaining,
                        cell, pos, str(pos_type), picked_by, lock_by))
        db.commit()

    def end_event(self):
        if not self.completed:
            self.save_event("End_of_Time")

    def order_finished(self):
        if self.position == self.SIMULATION_ENVIRONMENT.main_cell.OUTPUT_BUFFER and self.tasks_finished:
            self.position.items_in_storage.remove(self)
            self.current_cell = None
            self.position = None
            self.completed = True
            self.completed_at = self.env.now
            self.__class__.finished_instances.append(self)
            print("Order finished! Nr ", len(self.__class__.finished_instances))

    def processing_step_finished(self):
        if len(self.remaining_tasks) == 1:
            del self.remaining_tasks[0]
            self.next_task = ProcessingStep.dummy_processing_step
            self.tasks_finished = True
        else:
            del self.remaining_tasks[0]
            self.next_task = self.remaining_tasks[0]

    def order_arrival(self):
        #print(self.env.now, "Arrival of new Item", self.starting_position.items_in_storage, self.starting_position.STORAGE_CAPACITY, len([o for o in self.starting_position.items_in_storage if o.locked_by]))
        if len(self.starting_position.items_in_storage) < self.starting_position.STORAGE_CAPACITY:
            self.position = self.starting_position
            self.started = True
            self.position.items_in_storage.append(self)
            if len(self.position.items_in_storage) == self.position.STORAGE_CAPACITY:
                self.position.full = True
            print(self.env.now, "Arrival of new Item")
            self.SIMULATION_ENVIRONMENT.main_cell.new_order_in_cell(self)
            self.SIMULATION_ENVIRONMENT.main_cell.inform_agents()
            self.save_event("order_arrival")
            self.position.save_event("order_arrival")
        else:
            self.starting_position.items_waiting.append((self, self.env.now))
            self.save_event("incoming_order")

    def set_order_overdue(self):
        """Event if order wasn´t finished in time set order over due"""
        yield self.env.timeout(self.due_to - self.start)
        if not self.completed:
            self.overdue = True
            self.save_event("over_due")

    def machine_failure(self, new):
        if new:
            self.wait_for_repair = True
            self.save_event("machine_failure")
        else:
            self.wait_for_repair = False

    def get_additional_ranking_criteria(self, requesting_agent):

        distance = requesting_agent.time_for_distance(
            self.position)  # How long does it take the agent to get to my position?

        if not distance:
            distance = 0

        est_accessable_in = 0
        if isinstance(self.position, Machine.Machine):
            if self.processing:
                est_accessable_in = self.position.remaining_manufacturing_time - (self.env.now - self.position.manufacturing_start_time) - distance
            elif self.wait_for_repair:
                est_accessable_in = self.position.failure_fixed_in - (self.env.now - self.position.failure_time) + self.position.remaining_manufacturing_time - distance
            elif self == self.position.item_in_input and self.position.item_in_machine:

                item_in_machine = self.position.item_in_machine
                setup_time, type = self.position.calculate_setup_time(self)
                own_processing_time = self.position.calculate_processing_time(self, self.next_task)

                if item_in_machine.processing:
                    est_accessable_in = self.position.remaining_manufacturing_time - (self.env.now - self.position.manufacturing_start_time) + setup_time + own_processing_time - distance
                elif item_in_machine.wait_for_repair:
                    est_accessable_in = self.position.failure_fixed_in - (self.env.now - self.position.failure_time) + self.position.remaining_manufacturing_time + setup_time + own_processing_time - distance
                elif self.position.setup:
                    est_accessable_in = self.position.remaining_setup_time - (self.env.now - self.position.setup_start_time) + self.position.calculate_processing_time(self.position.item_in_machine, self.position.item_in_machine.next_task) + own_processing_time - distance
            else:
                est_accessable_in = 0
        if est_accessable_in < 0:
            est_accessable_in = 0

        remaining_tasks = len(self.remaining_tasks)

        tasks_in_cell_performable = consecutive_performable_tasks(self.remaining_tasks, self.current_cell.PERFORMABLE_TASKS)

        if self.processing:
            remaining_tasks -= 0.5
            tasks_in_cell_performable -= 1

        order_length = self.due_to - self.start

        relative_order_duration = (self.env.now - self.start) / order_length

        return {"distance": distance, "est_accessable_in": est_accessable_in, "remaining_tasks": remaining_tasks,
                "tasks_in_cell_performable": tasks_in_cell_performable, "order_length": order_length,
                "relative_order_duration": relative_order_duration}


class OrderType:
    instances = []

    def __init__(self, type_config: dict):
        self.__class__.instances.append(self)
        self.instance = len(self.__class__.instances)
        self.name = type_config['title'].encode()
        self.type_id = type_config['id']
        self.frequency_factor = type_config['frequency_factor']
        self.duration_factor = type_config['duration_factor']
        self.composition = type_config['composition']
        self.work_schedule = type_config['work_schedule']
        for processing_step in ProcessingStep.instances:
            self.work_schedule = [processing_step if x == processing_step.id else x for x in self.work_schedule]

    def __eq__(self, other):
        if other:
            return self.instance == other.instance
        else:
            return False

    def __lt__(self, other):
        return self.instance < other.instance


def load_order_types():
    """
    Create instances for order types from json
    """
    load_processing_steps()
    order_types = json.load(open("Order_types.json", encoding="UTF-8"))
    for type in order_types['order_types']:
        OrderType(type)


def order_arrivals(env: simpy.Environment, sim_env, config: dict):
    """
    Create incoming order events for the simulation environment

    :param env: SimPy environment
    :param sim_env: Object of class simulation environment
    :param config: Configuration with Parameter like number of orders, order length
    """

    orders_created = 0
    last_arrival = 0
    max_orders = config['NUMBER_OF_ORDERS']
    seed = config["SEED_INCOMING_ORDERS"]

    list_of_orders = get_orders_from_seed(max_orders, seed, config)
    sorted_list = list_of_orders[np.argsort(list_of_orders[:], order=["start", "urgency", "due_to"])]

    for order in sorted_list:
        yield env.timeout(order['start'] - last_arrival)
        new_order = Order(env, sim_env, env.now, order['due_to'], order['urgency'],
                          order['type'], complexity=order['complexity'])
        new_order.order_arrival()
        last_arrival = env.now
        orders_created += 1


def get_orders_from_seed(amount: int, seed: int, config: dict):
    """Create a list of random order attributes from seed"""
    np.random.seed(seed)

    possible_types = OrderType.instances
    frequency_factors = [order_type.frequency_factor for order_type in possible_types]
    factors_sum = sum(frequency_factors)
    frequency_factors = [factor/factors_sum for factor in frequency_factors]

    start_times = np.random.uniform(low=0, high=config['SIMULATION_RANGE'], size=amount)

    urgencies = np.random.randint(low=1, high=4, size=amount)
    types = np.random.choice(possible_types, amount, p=frequency_factors,  replace=True)
    duration_factors = np.asarray([order_type.duration_factor for order_type in types])
    base_lengths = np.random.randint(low=config['ORDER_MINIMAL_LENGTH'], high=config['ORDER_MAXIMAL_LENGTH'], size=amount)

    complexities = np.random.normal(loc=1, scale=config['SPREAD_ORDER_COMPLEXITY'], size=amount)

    # Check if random complexities are greater than 0
    for complexity in complexities:
        comp_value = complexity
        while comp_value <= 0:
            comp_value = np.random.normal(loc=1, scale=config['SPREAD_ORDER_COMPLEXITY'], size=1)
        complexities[complexities == complexity] = comp_value

    # Calculate order due_tue dates
    due_tues = start_times + base_lengths * duration_factors

    order_records = np.rec.fromarrays((start_times, due_tues, urgencies, complexities, types),
                                        names=('start', 'due_to', 'urgency', 'complexity', 'type'))

    return order_records
