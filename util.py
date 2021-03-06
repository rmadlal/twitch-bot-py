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


class swallow_exceptions:

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            return
        print(f'Suppressed exception: {exc_type.__name__}({exc_val})')
        return True
