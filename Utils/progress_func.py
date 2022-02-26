import simpy


def show_progress_func(env, sim_env):
    """Print out the current progress while simulating"""
    periods = 10
    period_length = sim_env.SIMULATION_TIME_RANGE/periods
    counter = 1

    def show_occupancy():
        print("\nCurrent orders per cell:")
        for cell in sim_env.cells:
            order_amount = len(cell.orders_in_cell)
            capacity = cell.CELL_CAPACITY
            bar = '█' * order_amount
            bar = bar or '▏'
            label = "Cell {id} ({type})".format(id=cell.ID, type=cell.TYPE)
            print(f'{label.rjust(15)} ▏ {order_amount:#2d} / {capacity:#2d} {bar}')
        print()

    while counter <= periods:
        yield env.timeout(period_length)
        print("Finished", (100/periods)*(counter), "% of the simulation!")
        show_occupancy()
        counter += 1
