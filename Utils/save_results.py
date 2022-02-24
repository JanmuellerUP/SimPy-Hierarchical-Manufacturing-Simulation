import json
import Cell
from copy import copy


class SimulationResults:
    instances = []

    def __init__(self, sim_env):
        sim_results = copy(schema_simulation)
        sim_results["run_number"] = len(self.__class__.instances) + 1
        sim_results["seed_incoming_orders"] = sim_env.SEED_INCOMING_ORDERS
        sim_results["seed_machine_interruptions"] = sim_env.SEED_MACHINE_INTERRUPTIONS
        sim_results["simulation_results"] = sim_env.result

        # Fill cell schema
        for cell in Cell.Cell.instances:
            cell_schema = copy(schema_cells)
            cell_schema["cell_results"] = cell.result

            # Fill agent schema
            for agent in cell.AGENTS:
                agent_schema = copy(schema_agents)
                agent_schema["ruleset"] = agent.RULESET.name.decode("UTF-8")
                agent_schema["agent_results"] = agent.result
                cell_schema["agents"].append(agent_schema)

            # Fill machine schema
            for machine in cell.MACHINES:
                machine_schema = copy(schema_machines)
                machine_schema["type"] = machine.PERFORMABLE_TASK.name.decode("UTF-8")
                machine_schema["machine_results"] = machine.result
                cell_schema["machines"].append(machine_schema)

            # Fill input buffer schema
            input_b_schema = copy(schema_buffer)
            input_b_schema["type"] = "Input-Buffer"
            input_b_schema["capacity"] = cell.INPUT_BUFFER.STORAGE_CAPACITY
            input_b_schema["buffer_results"] = cell.INPUT_BUFFER.result
            cell_schema["buffer"].append(input_b_schema)

            # Fill output buffer schema
            output_b_schema = copy(schema_buffer)
            output_b_schema["type"] = "Output-Buffer"
            output_b_schema["capacity"] = cell.OUTPUT_BUFFER.STORAGE_CAPACITY
            output_b_schema["buffer_results"] = cell.OUTPUT_BUFFER.result
            cell_schema["buffer"].append(output_b_schema)

            # Fill storage buffer schema
            storage_b_schema = copy(schema_buffer)
            storage_b_schema["type"] = "Storage-Buffer"
            storage_b_schema["capacity"] = cell.STORAGE.STORAGE_CAPACITY
            storage_b_schema["buffer_results"] = cell.STORAGE.result
            cell_schema["buffer"].append(storage_b_schema)

            # Fill interface buffers schema
            for interface in cell.INTERFACES_IN:
                interface_in_schema = copy(schema_buffer)
                interface_in_schema["type"] = "Interface-Buffer Outgoing"
                interface_in_schema["capacity"] = interface.STORAGE_CAPACITY
                interface_in_schema["buffer_results"] = interface.result
                cell_schema["buffer"].append(interface_in_schema)

            for interface in cell.INTERFACES_OUT:
                interface_out_schema = copy(schema_buffer)
                interface_out_schema["type"] = "Interface-Buffer Ingoing"
                interface_out_schema["capacity"] = interface.STORAGE_CAPACITY
                interface_out_schema["buffer_results"] = interface.result
                cell_schema["buffer"].append(interface_out_schema)

            sim_results["cells"].append(cell_schema)

        self.results = sim_results
        self.__class__.instances.append(self)


schema_simulation = json.loads("""{
                "run_number": null,
                "seed_incoming_orders": null,
                "seed_machine_interruptions": null,
                "simulation_results": null,
                "cells": []
            }""")

schema_cells = json.loads("""
        {
          "cell_results": null,
          "agents": [],
          "machines": [],
          "buffer": []
        }
        """)

schema_agents = json.loads("""
            {
              "ruleset": null,
              "agent_results": null
            }
        """)

schema_machines = json.loads("""
            {
              "type": null,
              "machine_results": null
            }
        """)

schema_buffer = json.loads("""
            {
              "type": null,
              "capacity": null,
              "buffer_results": null
            }
        """)