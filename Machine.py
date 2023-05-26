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

from ProcessingStep import ProcessingStep
import simpy
import numpy as np
import json
from Utils.log import write_log


class Machine:
    instances = []

    def __init__(self, config: dict, env: simpy.Environment, task_id):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None
        self.CELL = None

        # Attributes
        self.RESPONSIBLE_AGENTS = None
        for task in ProcessingStep.instances:
            if task.id == int(task_id):
                self.PERFORMABLE_TASK = task
                break
        self.ERROR_RATE = config['MACHINE_FAILURE_RATE']
        self.FAILURE_MIN_LENGTH = config['FAILURE_MINIMAL_LENGTH']
        self.FAILURE_MAX_LENGTH = config['FAILURE_MAXIMAL_LENGTH']
        self.BASE_SETUP_TIME = config['MACHINE_SETUP_TIME']

        # State
        self.agents_at_position = []
        self.waiting_agents = []
        self.wait_for_item_proc = None
        self.wait_for_output_proc = None
        self.setup_proc = None
        self.wait_for_setup_and_load = False

        self.expected_orders = []  # (order, time, agent)
        self.next_expected_order = None
        self.expected_orders_to_left = []  # (order, time, agent)
        self.current_setup = None
        self.previous_item = None

        self.item_in_output = None
        self.item_in_machine = None
        self.item_in_input = None
        self.input_lock = False

        self.idle = True
        self.load_item = False

        self.manufacturing = False
        self.manufacturing_start_time = None
        self.manufacturing_time = 0
        self.remaining_manufacturing_time = 0
        self.manufacturing_end_time = None

        self.setup = False
        self.setup_start_time = None
        self.remaining_setup_time = 0
        self.setup_finished_at = None

        self.failure = False
        self.failure_time = None
        self.failure_fixed_in = 0
        self.failure_fixed_at = 0

        self.__class__.instances.append(self)
        self.result = None
        self._excluded_keys = ["logs", "env", "RESPONSIBLE_AGENTS", "_excluded_keys", "_continuous_attributes"]
        self._continuous_attributes = ["remaining_manufacturing_time", "remaining_setup_time", "failure_fixed_in"]

        self.env.process(self.initial_event())
        self.main_proc = self.env.process(self.main_process())

    def occupancy(self, attributes: list, requester=None):

        def machine_type():
            return self.PERFORMABLE_TASK.id

        def current_setup():
            if self.current_setup:
                return self.current_setup.type_id
            else:
                return -1

        def in_setup():
            return int(self.setup)

        def next_setup():
            if self.setup:
                return self.next_expected_order.type.type_id
            else:
                return current_setup()

        def remaining_setup_time():
            if self.setup:
                return self.setup_finished_at - self.env.now
            else:
                return 0

        def manufacturing():
            return int(self.manufacturing)

        def failure():
            return int(self.failure)

        def remaining_man_time():
            if self.failure:
                return self.remaining_manufacturing_time
            elif self.manufacturing:
                return self.manufacturing_end_time - self.env.now
            else:
                return 0

        def failure_fixed_in():
            if self.failure:
                return self.failure_fixed_at - self.env.now
            else:
                return 0

        attr = {}
        for attribute in attributes:
            attr[attribute] = locals()[attribute]()

        return ([{"order": self.item_in_input, "pos": self, "pos_type": "Machine-Input"},
                {"order": self.item_in_machine, "pos": self, "pos_type": "Machine-Internal"},
                {"order": self.item_in_output, "pos": self, "pos_type": "Machine-Output"}], attr)

    def save_event(self, event_type: str, est_time=None, next_setup_type=None):
        db = self.SIMULATION_ENVIRONMENT.db_con
        cursor = self.SIMULATION_ENVIRONMENT.db_cu

        time = self.env.now

        if next_setup_type:
            nst = id(next_setup_type)
        else:
            nst = None

        if self.current_setup:
            cst = id(self.current_setup)
        else:
            cst = None

        if self.item_in_input:
            iii = id(self.item_in_input)
        else:
            iii = None

        if self.item_in_machine:
            iim = id(self.item_in_machine)
        else:
            iim = None

        if self.item_in_output:
            iio = id(self.item_in_output)
        else:
            iio = None

        cursor.execute("INSERT INTO machine_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (id(self), time, event_type, est_time, nst, cst, self.load_item, self.manufacturing, self.setup, self.idle, self.failure, iii, iim, iio))

        db.commit()

    def initial_event(self):
        self.save_event("Initial")
        yield self.env.timeout(0)

    def end_event(self):
        self.save_event("End_of_Time")

    def main_process(self):
        try:
            if self.expected_orders or self.item_in_input:
                if self.item_in_input:
                    self.next_expected_order = self.item_in_input
                else:
                    min_time = float('inf')
                    for order, time, agent in self.expected_orders:
                        if time < min_time:
                            self.next_expected_order = order

                self.wait_for_setup_and_load = True
                laden = self.env.process(self.get_item())
                self.setup_proc = self.env.process(self.setup_process(self.next_expected_order))
                yield laden & self.setup_proc
                self.next_expected_order = None
                self.wait_for_setup_and_load = False
                yield self.env.process(self.starter())
                yield self.env.process(self.release_item_to_output())
                self.main_proc = self.env.process(self.main_process())
            else:
                self.wait_for_item_proc = self.env.process(self.wait_for_item())
                yield self.wait_for_item_proc
                self.main_proc = self.env.process(self.main_process())
        except simpy.Interrupt as interruption:
            #print(self, "UNTERBRECHE MAIN PROZESS", interruption, self.env.now)
            #print("Aktueller Status:", self.next_expected_order, self.wait_for_setup_and_load, self.wait_for_item_proc)
            self.main_proc = None
            if laden.is_alive:
                #print("Unterbreche Laden")
                laden.interrupt("The expected order arrival was cancel")
                #print(laden.is_alive, self.wait_for_item_proc)
            self.next_expected_order = None
            self.wait_for_setup_and_load = False
            self.main_proc = self.env.process(self.main_process())

    def wait_for_free_output(self):
        try:
            self.item_in_machine.blocked_by = self.item_in_output
            while 1:
                yield self.env.timeout(10)
        except simpy.Interrupt as interruption:
            self.item_in_machine.blocked_by = None
            self.wait_for_output_proc = None

    def wait_for_item(self):
        try:
            while 1:
                yield self.env.timeout(10)
        except simpy.Interrupt as interruption:
            self.wait_for_item_proc = None

    def get_item(self):
        """Load item from input into the machine"""
        try:
            if not self.item_in_input:
                self.wait_for_item_proc = self.env.process(self.wait_for_item())
                yield self.wait_for_item_proc

            if self.item_in_input is not None and self.item_in_machine is None and self.item_in_input.next_task == self.PERFORMABLE_TASK:
                self.idle = False
                self.load_item = True
                self.save_event("load_item_start")
                yield self.env.timeout(0.1)
                self.item_in_machine = self.item_in_input
                self.item_in_input = None
                self.load_item = False
                if not self.setup:
                    self.idle = True
                self.save_event("load_item_end")

                waiting_agents = [agent for agent in self.agents_at_position if agent.current_waitingtask]
                if len(waiting_agents) > 0:
                    waiting_agents[0].current_waitingtask.interrupt("New free slot in Machine Input")
                self.CELL.inform_agents()
            else:
                raise Exception("Can not load item from machine input!")
        except simpy.Interrupt as interruption:
            #print("Interrupt get item")
            if self.load_item:
                self.load_item = False
                if not self.setup:
                    self.idle = True
            if self.wait_for_item_proc:
                self.wait_for_item_proc.interrupt()

    def setup_process(self, next_item):
        """Planned Setup if next item has other type than the previous one"""
        if self.manufacturing or self.failure:
            #print(self, "ist am produzieren oder in reperatur")
            return

        setup_time, new_task = self.calculate_setup_time(item=next_item)
        if setup_time == 0:
            #print(self, "kein setup noetig", self.env.now)
            return
        else:
            self.idle = False
            self.setup = True
            self.setup_start_time = self.env.now
            self.remaining_setup_time = setup_time
            self.setup_finished_at = self.setup_start_time + self.remaining_setup_time
            self.save_event("setup_start", next_setup_type=new_task)
            #print("Start setup", self, self.env.now, "OLD:", self.current_setup, "NEW", new_task, "Dauer:", self.remaining_setup_time, "ITEM", next_item, next_item.type)
            yield self.env.timeout(self.remaining_setup_time)
            self.setup = False
            if not self.load_item:
                self.idle = True
            self.remaining_setup_time = 0
            self.setup_finished_at = None
            self.setup_start_time = None
            self.current_setup = new_task
            self.save_event("setup_end")
            #print("Finished Setup:", self, self.current_setup, self.env.now, next_item, next_item.type)
            #print("Machine Status:", self.item_in_input, self.item_in_machine, self.expected_orders)
            #print("End setup", self, self.env.now, "Current:", new_task)

    def calculate_setup_time(self, item=None):
        """Calculate Time needed for setup"""
        current_type = self.current_setup
        if item.type == current_type:
            return 0, None
        else:
            return self.BASE_SETUP_TIME, item.type

    def release_item_to_output(self):
        """Release finished Item to output slot of this machine"""
        if self.manufacturing or not self.item_in_machine:
            #print("Machine Error: Can not release Item!")
            return
        if self.item_in_output:
            self.item_in_machine.blocked_by = self.item_in_output
            self.wait_for_output_proc = self.env.process(self.wait_for_free_output())
            yield self.wait_for_output_proc
            self.item_in_machine.blocked_by = None
        self.idle = False
        self.save_event("release_item_start")
        yield self.env.timeout(0.1)
        released_item = self.item_in_machine
        self.item_in_machine = None
        self.item_in_output = released_item

        for agent, place in self.item_in_output.waiting_agent_pos:
            if place == self:
                agent.current_waitingtask.interrupt("Finished Production")
        if not self.setup and not self.load_item:
            self.idle = True
        self.save_event("release_item_end")
        self.CELL.inform_agents()

    def calculate_processing_time(self, item, task):
        """
        Calculate how long an item will take to be processed by this machine

        :param item: Which item should be processed?
        :param task: What task should be performed?
        :return: Manufacturing time needed for this item
        """
        material_attributes = []
        materials = json.load(open("Materials.json"))
        for composition_element in item.composition:
            for material in materials['materials']:
                if material['title'] == composition_element:
                    material_complexity = material['complexity']
                    material_hardness = material['hardness']
                    break
            material_attributes.append((item.composition[composition_element], material_complexity, material_hardness))
        manufacturing_time = (task.base_duration * item.complexity * sum([amount*(complexity+(hardness/2)) for amount, complexity, hardness in material_attributes]))/10
        return manufacturing_time

    def get_remaining_time(self):
        return self.remaining_manufacturing_time - (self.env.now - self.manufacturing_start_time)

    def get_remaining_repair_time(self):
        return self.failure_fixed_in - (self.env.now - self.failure_time)

    def starter(self):
        manufacturing_process = self.env.process(self.process_manufacturing(new=True))
        yield manufacturing_process

    def process_manufacturing(self, new: bool):
        """
        Perform the main manufacturing process of the machine
        :param new: Is the item in machine an new item or an partly processed one?
        """
        if self.setup:
            print("Machine Error: Machine is in Setup!")
            return
        if self.item_in_machine is None or self.item_in_machine.next_task is not self.PERFORMABLE_TASK:
            print("Machine Error: There is not an useful item in the machine!")
            return
        elif self.item_in_machine.type is not self.current_setup:
            print("Machine Error: Machine is in wrong setup!", self, self.current_setup, self.env.now, self.item_in_machine)
            #print(self.item_in_machine, self.item_in_machine.type, self.setup, self.current_setup, self.item_in_input, new)
            return

        def start_new():
            self.manufacturing_time = self.calculate_processing_time(self.item_in_machine, self.PERFORMABLE_TASK)
            self.remaining_manufacturing_time = self.manufacturing_time
            self.idle = False
            self.manufacturing = True
            self.manufacturing_start_time = self.env.now
            self.manufacturing_end_time = self.manufacturing_start_time + self.manufacturing_time
            self.item_in_machine.processing = True
            self.item_in_machine.save_event("processing_start")
            self.save_event("production_start", est_time=self.manufacturing_time)

        def continue_process():
            self.idle = False
            self.manufacturing = True
            self.manufacturing_start_time = self.env.now
            self.manufacturing_end_time = self.manufacturing_start_time + self.remaining_manufacturing_time
            self.item_in_machine.processing = True
            self.item_in_machine.save_event("processing_continue")
            self.save_event("failure_end")

        if new:
            start_new()
        else:
            continue_process()

        if self.ERROR_RATE > 0:
            errors = np.random.uniform(low=0, high=1000, size=self.ERROR_RATE)
            errors.sort()
            first_error = errors[0]
        else:
            first_error = float('inf')
        if first_error < self.remaining_manufacturing_time:
            yield self.env.timeout(first_error)
            yield self.env.process(self.failure_event())
        else:
            yield self.env.timeout(self.remaining_manufacturing_time)
            self.manufacturing = False
            self.idle = True
            self.manufacturing_start_time = None
            self.remaining_manufacturing_time = 0
            self.previous_item = self.item_in_machine
            #self.env.process(testing_machines_single(self.env))
            self.item_in_machine.processing = False
            self.item_in_machine.processing_step_finished()
            if self.item_in_output:
                self.item_in_machine.blocked_by = self.item_in_output
            self.item_in_machine.save_event("processing_finished")
            self.save_event("production_end")

    def failure_event(self):
        """Machine has an unplanned Failure Event. Calculate length of repair and continue production afterwards"""
        #print("FAILURE EVENT", self.env.now, self)
        self.failure = True
        self.failure_time = self.env.now
        self.failure_fixed_in = np.random.uniform(low=self.FAILURE_MIN_LENGTH, high=self.FAILURE_MAX_LENGTH)
        self.failure_fixed_at = self.failure_fixed_in + self.failure_time
        self.manufacturing = False
        self.remaining_manufacturing_time = self.manufacturing_time - (self.env.now - self.manufacturing_start_time)
        self.manufacturing_end_time = self.failure_fixed_at + self.remaining_manufacturing_time
        self.save_event("failure_start", est_time=self.failure_fixed_in)

        self.item_in_machine.machine_failure(True)
        yield self.env.timeout(self.failure_fixed_in)

        self.failure = False
        self.failure_time = None
        self.failure_fixed_in = 0
        self.failure_fixed_at = None
        self.item_in_machine.machine_failure(False)
        yield self.env.process(self.process_manufacturing(new=False))

    def cancel_expected_order(self, order):
        if order == self.next_expected_order:

            if self.main_proc and self.wait_for_setup_and_load:
                if self.setup_proc:
                    if self.setup_proc.is_alive:
                        print("Setup is currently performed")
                        yield self.setup_proc
                self.main_proc.interrupt("Expected Order canceled")



