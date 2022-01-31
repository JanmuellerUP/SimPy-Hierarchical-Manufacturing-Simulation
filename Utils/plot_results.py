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