import pandas as pd


def evaluate_choice(choice):

    # Penalty criteria for forbidden choices
    criteria = [
        choice["order"] == 0,
        choice["locked"] == 2,
        choice["picked_up"] == 1,
        choice["in_m_input"] == 1,
        choice["in_m"] == 1,
        choice["processing"] == 1,
        choice["in_same_cell"] == 0,
        choice["_destination"] == -1
    ]

    penalty = -1000 * sum(criteria)

    return penalty


def reward_action():
    return 0