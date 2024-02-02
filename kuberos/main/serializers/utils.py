

def get_choice_value(choices, label):
    """
    Get the value of a choice by its human-readable label.
    """
    for value, display_label in choices.choices:
        if display_label == label:
            return value
    return None  # or raise an exception, if you prefer
