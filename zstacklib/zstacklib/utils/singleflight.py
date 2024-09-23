import threading


class Result:
    def __init__(self, val=None, err=None, shared=False):
        self.value = val
        self.error = err
        self.shared = shared


class Call:
    def __init__(self, fn):
        self.fn = fn
        self.wg = threading.Event()
        self.result = Result()
        threading.Thread(target=self._run).start()

    def _run(self):
        try:
            self.result.value = self.fn()
        except Exception as e:
            self.result.error = e
        finally:
            self.wg.set()

    def wait(self):
        self.wg.wait()
        return self.result


class Group:
    def __init__(self):
        self.mu = threading.Lock()
        self.m = {}

    def do(self, key, fn):
        self.mu.acquire()
        if key in self.m:
            c = self.m[key]
            self.mu.release()
            result = c.wait()
            result.shared = True
            return result

        c = Call(fn)
        self.m[key] = c
        self.mu.release()

        result = c.wait()

        self.mu.acquire()
        del self.m[key]
        self.mu.release()

        return result
