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
            #self.model = pickle.loads(rules['rules']['trained_model'])
        except:
            self.dynamic = False
            #self.model = None


def load_rulesets():
    """Load possible rulesets from json file and create an object for each"""
    rulesets_config = json.load(open("rulesets.json", encoding='utf-8'))
    for rule in rulesets_config['rulesets']:
        RuleSet(rule)
