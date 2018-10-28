import random
import threading


# Removes and returns a random item from a list
def pop_random_item(lst):
    return lst.pop(random.randrange(len(lst)))


# Decorator for repeating a function every `interval` seconds
def repeat_every(interval: float):
    def wrapper(f):
        stopped = threading.Event()

        def inner(*args):
            def loop():
                while not stopped.wait(interval):
                    f(*args)

            threading.Thread(target=loop).start()

        inner.cancel = stopped.set
        return inner

    return wrapper
