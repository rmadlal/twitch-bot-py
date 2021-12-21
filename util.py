import threading


# Decorator for repeating a function every `interval` seconds
def repeat_every(interval: float):
    def wrapper(f):
        def inner(*args):
            stopped = threading.Event()

            def loop():
                while not stopped.wait(interval):
                    f(*args)

            threading.Thread(target=loop).start()
            return stopped.set

        return inner

    return wrapper
