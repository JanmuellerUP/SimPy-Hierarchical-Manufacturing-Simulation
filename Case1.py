from Config import configuration, evaluation_measures
import environment

# Test-Labor
sim_results = environment.simulation(configuration, evaluation_measures, show_progress=True, runs=1, change_interruptions=True, change_incoming_orders=True, train=True)