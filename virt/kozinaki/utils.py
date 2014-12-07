from functools import wraps
import time


def timeout_call(wait_period, timeout):
    """
    This decorator calls given method repeatedly
    until it throws exception. Loop ends when method
    returns.
    """
    def _inner(f):
        @wraps(f)
        def _wrapped(*args, **kwargs):
            start = time.time()
            if '_timeout' in kwargs and kwargs['_timeout']:
                _timeout = kwargs['_timeout']
                end = start + _timeout
            else:
                end = start + timeout
            exc = None
            while(time.time() < end):
                try:
                    return f(*args, **kwargs)
                except Exception as exc:
                    time.sleep(wait_period)
            raise exc
        return _wrapped
    return _inner

# test
@timeout_call(wait_period=3, timeout=600)
def func():
    raise Exception('none')

if __name__ == "__main__":
    func(_timeout=3)