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

import simpy
from Utils.log import write_log


class Buffer:
    instances = []

    def __init__(self, config: dict, env: simpy.Environment, size: int):
        self.env = env
        self.SIMULATION_ENVIRONMENT = None
        self.CELL = None

        # Attributes
        self.RESPONSIBLE_AGENTS = None
        self.STORAGE_CAPACITY = size

        # State
        self.items_in_storage = []
        self.full = False
        self.items_waiting = []
        self.agents_at_position = []
        self.waiting_agents = []
        self.expected_orders = []  # (order, time, agent)
        self.expected_orders_to_left = []  # (order, time, agent)

        self.__class__.instances.append(self)
        self.result = None
        self._excluded_keys = ["logs", "env", "RESPONSIBLE_AGENTS", "_excluded_keys", "_continuous_attributes"]
        self._continuous_attributes = []

        self.env.process(self.initial_event())

    def save_event(self, event_type: str, item=None):
        db = self.SIMULATION_ENVIRONMENT.db_con
        cursor = self.SIMULATION_ENVIRONMENT.db_cu

        time = self.env.now

        if item:
            item = id(item)

        cursor.execute("INSERT INTO buffer_events VALUES(?,?,?,?,?,?)",
                       (id(self), time, event_type, item, self.full, len(self.items_in_storage)))
        db.commit()

    def end_event(self):
        self.save_event("End_of_Time")

    def initial_event(self):
        self.save_event("Initial")
        yield self.env.timeout(0)

    def free_slots(self):
        return self.STORAGE_CAPACITY > len(self.items_in_storage) - len(
            [order for order in self.items_in_storage if order.locked_by]) + len(
            self.expected_orders)

    def item_picked_up(self, item):
        self.items_in_storage.remove(item)
        if self.items_waiting:
            self.items_waiting = sorted(self.items_waiting, key=lambda tup: tup[1])
            self.items_waiting[0][0].order_arrival()
            del self.items_waiting[0]
        else:
            self.full = False
            if len(self.waiting_agents) > 0:
                self.waiting_agents[0].current_waitingtask.interrupt("New space free")
        self.save_event("item_picked_up", item)

    def occupancy(self, pos_type: str, attributes: list, cell=None):

        def interface_outgoing():
            if self.lower_cell == cell:
                # Input/Output of Cell
                if self == cell.INPUT_BUFFER:
                    return 0
                else:
                    return 1
            elif self.upper_cell == cell:
                if self == self.lower_cell.INPUT_BUFFER:
                    return 1
                else:
                    return 0

        def interface_ingoing():
            if self.lower_cell == cell:
                # Input/Output of Cell
                if self == cell.INPUT_BUFFER:
                    return 1
                else:
                    return 0
            elif self.upper_cell == cell:
                if self == self.lower_cell.INPUT_BUFFER:
                    return 0
                else:
                    return 1

        attr = {}
        if isinstance(self, InterfaceBuffer):
            for attribute in attributes:
                attr[attribute] = locals()[attribute]()

        return ([{"order": item, "pos": self, "pos_type": pos_type} for item in self.items_in_storage] \
               + [{"order": None, "pos": self, "pos_type": pos_type}] * (self.STORAGE_CAPACITY - len(self.items_in_storage)), attr)


class QueueBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int):
        super().__init__(config, env, size)


class InterfaceBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int, lower_cell=None, upper_cell=None):
        self.lower_cell = lower_cell
        self.upper_cell = upper_cell
        super().__init__(config, env, size)

