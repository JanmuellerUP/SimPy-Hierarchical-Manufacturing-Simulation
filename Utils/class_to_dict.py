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