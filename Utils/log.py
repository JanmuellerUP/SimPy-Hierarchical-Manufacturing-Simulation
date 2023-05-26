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

from Utils.class_to_dict import class_to_dict
from Order import Order


def write_log(obj):
    """Write all current values of non excluded object attributes into the log array"""
    data = {"Time": obj.env.now, "Data": class_to_dict(obj)}
    obj.logs.append(data)


def get_log(obj, requester=None):

    data = class_to_dict(obj)

    if requester and isinstance(obj, Order):
        additional_criteria = obj.get_additional_ranking_criteria(requester)
        data = {**data, **additional_criteria}

    return data
