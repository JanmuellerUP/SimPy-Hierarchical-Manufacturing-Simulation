def class_to_dict(cls):
    return dict(
        (key, value)
        for (key, value) in cls.__dict__.items()
        if key not in cls._excluded_keys
    )