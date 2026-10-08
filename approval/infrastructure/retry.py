import random
import time

class TransientFailure(Exception): pass
class PermanentFailure(Exception): pass
class InvalidModelOutput(Exception): pass

def retry(operation, attempts=3, sleep=time.sleep, jitter=random.random):
    for attempt in range(attempts):
        try: return operation()
        except TransientFailure:
            if attempt + 1 == attempts: raise
            sleep(min(8, 2 ** attempt) + jitter())
