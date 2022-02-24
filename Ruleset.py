# -*- coding: utf-8 -*-
import json
import pickle


class RuleSet:
    instances = []

    def __init__(self, rules: dict):
        self.__class__.instances.append(self)
        self.id = rules['id']
        self.name = rules['name'].encode()
        self.description = rules['description'].encode()
        try:
            self.random = bool(rules['rules']['random'])
            self.seed = rules['rules']['seed']
        except:
            self.random = False
            self.seed = None
            pass

        try:
            self.numerical_criteria = rules['rules']['criteria']['numerical']
        except:
            self.numerical_criteria = []
            pass

        try:
            self.dynamic = rules['rules']['dynamic']
            self.model = pickle.loads(rules['rules']['trained_model'])
        except:
            self.dynamic = False
            self.model = None


def load_rulesets():
    """Load possible rulesets from json file and create an object for each"""
    rulesets_config = json.load(open("rulesets.json", encoding='utf-8'))
    for rule in rulesets_config['rulesets']:
        RuleSet(rule)