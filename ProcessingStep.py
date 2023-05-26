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

# -*- coding: utf-8 -*-
import json


class ProcessingStep:
    instances = []
    dummy_processing_step = None

    def __init__(self, task_config: dict, hidden=False):
        self.id = task_config["id"]
        self.name = task_config["title"].encode()
        self.base_duration = task_config["base_duration"]

        self.hidden = hidden
        if hidden:
            self.__class__.dummy_processing_step = self

        self.__class__.instances.append(self)


def load_processing_steps():
    """Load possible processing steps from json file and create an object for each"""
    processing_steps = json.load(open("ProcessingSteps.json", encoding="UTF-8"))

    # Hidden dummy processing step for finished orders
    ProcessingStep({"id": -1, "title": "Order finished", "base_duration": 0}, hidden=True)

    for step in processing_steps['tasks']:
        ProcessingStep(step)
