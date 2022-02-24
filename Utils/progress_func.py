import simpy


def show_progress_func(env, sim_env):
    """Print out the current progress while simulating"""
    periods = 10
    period_length = sim_env.SIMULATION_TIME_RANGE/periods
    counter = 1
    while counter <= periods:
        yield env.timeout(period_length)
        print("Finished", (100/periods)*(counter), "% of the simulation!")
        counter += 1