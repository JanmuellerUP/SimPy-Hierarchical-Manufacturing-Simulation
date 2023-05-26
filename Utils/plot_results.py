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

import matplotlib.pyplot as plt
import pandas as pd
import plotly.figure_factory as ff


def plot_gantt(data_periods: pd.DataFrame):
    data_periods = data_periods[["Start", "End", "Value"]].rename(columns={"End": "Finish", "Value": "Task"})
    data_periods["Resource"] = data_periods["Task"]
    print(data_periods)

    fig = ff.create_gantt(data_periods, colors={True: "rgb(124, 252, 0)", False: "rgb(255, 0, 0)"}, index_col="Resource", show_colorbar=True)
    fig.update_layout(xaxis_type='linear')
    fig.show()
