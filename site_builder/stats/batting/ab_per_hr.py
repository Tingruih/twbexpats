"""AB/HR — at-bats per home run."""


def compute_ab_per_hr(ab, hr):
    if ab is None or not hr or hr <= 0:
        return None
    return round(ab / hr, 1)
