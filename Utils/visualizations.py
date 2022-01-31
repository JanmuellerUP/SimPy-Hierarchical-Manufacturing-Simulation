import simpy
import networkx as nx
import matplotlib.pyplot as plt
import Cell
import Machine


def testing_cell_multiple(sim_env, env: simpy.Environment, delay):
    yield env.timeout(delay)
    G = nx.Graph()
    labels = {}
    for cell in sim_env.cells:
        G.add_node(cell)
        labels[cell] = "Level: " + str(cell.LEVEL)+" Orders_in_Cell: " + str(len(cell.orders_in_cell))+" Expected_Orders: " + str(len(cell.expected_orders))

    edges = [(node, node.CHILDS) for node in sim_env.cells if isinstance(node, Cell.DistributionCell)]
    edges_plain = []
    for node, childs in edges:
        for child in childs:
            edges_plain.append((node, child))
    G.add_edges_from(edges_plain)
    plt.title("Timestamp: " + str(env.now))
    nx.draw(G, with_labels=True, labels=labels)
    plt.show()
    env.process(testing_cell_multiple(sim_env, env, delay))


def testing_machines_single(env: simpy.Environment, delay=10):
    yield env.timeout(delay)
    G = nx.Graph()
    labels = {}
    for machine in Machine.Machine.instances:
        G.add_node(machine)
        labels[machine] = "Setup: " + str(machine.setup)+" Manufacturing: " + str(machine.manufacturing)+" Current Setup: " + str(machine.current_setup) + " Item in Input: " + str(machine.item_in_input) + " Item in Machine: " + str(machine.item_in_machine) + " Item in Output: " + str(machine.item_in_output)

    plt.title("Timestamp: " + str(env.now))
    nx.draw(G, with_labels=True, labels=labels)
    plt.show()
    yield env.timeout(delay)