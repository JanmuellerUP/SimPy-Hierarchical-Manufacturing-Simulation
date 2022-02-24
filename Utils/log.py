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