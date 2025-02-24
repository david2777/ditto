from time import perf_counter

class Timer:
    def __init__(self):
        self.start = perf_counter()

    def get_elapsed_time(self, precision: int = 4) -> float:
        return round(perf_counter() - self.start, precision)
