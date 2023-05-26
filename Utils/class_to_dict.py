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

def class_to_dict(cls):
    discrete_att = dict(
        (key, value)
        for (key, value) in cls.__dict__.items()
        if key not in cls._excluded_keys
        and key not in cls._continuous_attributes
    )

    continuous_att = dict(
        (key, get_continuous_att(cls, key))
        for (key, value) in cls.__dict__.items()
        if key not in cls._excluded_keys
        and key in cls._continuous_attributes
    )

    if continuous_att:
        return discrete_att.update(continuous_att)
    else:
        return discrete_att


def get_continuous_att(obj, attribute: str):
    result = getattr(obj, attribute)
    end_attr = getattr(obj, end_times[attribute])

    if result and end_attr:
        result = end_attr - obj.env.now

    return result


end_times = {"remaining_moving_time": "moving_end_time",
               "remaining_manufacturing_time": "manufacturing_end_time",
               "remaining_setup_time": "setup_finished_at",
               "failure_fixed_in": "failure_fixed_at"}
