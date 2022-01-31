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
        self.orders_waiting = []
        self.agents_at_position = []
        self.waiting_agents = []
        self.expected_orders = []  # (order, time, agent)
        self.expected_orders_to_left = []  # (order, time, agent)

        self.__class__.instances.append(self)
        self.logs = []
        self._excluded_keys = ["logs", "env", "RESPONSIBLE_AGENTS", "_excluded_keys"]

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


class QueueBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int):
        super().__init__(config, env, size)


class InterfaceBuffer(Buffer):

    def __init__(self, config: dict, env: simpy.Environment, size: int, lower_cell=None, upper_cell=None):
        self.lower_cell = lower_cell
        self.upper_cell = upper_cell
        super().__init__(config, env, size)

