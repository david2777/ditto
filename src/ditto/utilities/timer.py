from time import perf_counter


class Timer:
    def __init__(self):
        self.start = perf_counter()

    def get_elapsed_time(self, precision: int = 4) -> float:
        return round(perf_counter() - self.start, precision)

    def get_elapsed_time_ms(self) -> float:
        return (perf_counter() - self.start) * 1000
