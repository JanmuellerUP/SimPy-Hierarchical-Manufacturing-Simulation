import json


class ProcessingStep:
    instances = []

    def __init__(self, task_config: dict):
        self.__class__.instances.append(self)
        self.id = task_config['id']
        self.name = task_config['title']
        self.base_duration = task_config['base_duration']
        self.tool_change = task_config['tool_change_needed']


def load_processing_steps():
    """Load possible processing steps from json file and create an object for each"""
    processing_steps = json.load(open("ProcessingSteps.json"))
    for step in processing_steps['tasks']:
        ProcessingStep(step)