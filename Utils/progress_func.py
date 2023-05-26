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
