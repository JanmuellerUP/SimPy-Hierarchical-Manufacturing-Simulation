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

    def occupancy(self, pos_type: str):
        return [{"order": item, "pos": self, "pos_type": pos_type} for item in self.items_in_storage] \
               + [{"order": None, "pos": self, "pos_type": pos_type}] * (self.STORAGE_CAPACITY - len(self.items_in_storage))

    def get_pos_attributes(self, now):
        return 0


class QueueBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int):
        super().__init__(config, env, size)


class InterfaceBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int, lower_cell=None, upper_cell=None):
        self.lower_cell = lower_cell
        self.upper_cell = upper_cell
        super().__init__(config, env, size)

