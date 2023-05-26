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
