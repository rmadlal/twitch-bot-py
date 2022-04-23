import threading
from typing import Callable


# Decorator for repeating a function every `interval` seconds
def repeat_every(interval: float):
    def wrapper(func):
        def inner(*args) -> Callable:
            stopped = threading.Event()

            def loop():
                while not stopped.wait(interval):
                    func(*args)

            threading.Thread(target=loop).start()
            return stopped.set

        return inner

    return wrapper
