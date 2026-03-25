
class LogCollector:
    def __init__(self):
        self.logs = []
        self.log_count = 0

    def add_log(self, log):
        if log not in self.logs:
            self.logs.append(log)
            self.log_count += 1

    def get_logs(self):
        return self.logs.copy()  # safer to return a copy

    def clear_logs(self):
        self.logs = []
        self.log_count = 0

    def retrieve_log(self):
        """Return the oldest log (FIFO) and update log_count."""
        if not self.logs:
            return None
        self.log_count -= 1
        return self.logs.pop(0)






log_collector = LogCollector()


def itterator():
    for a in range(1):
        log_collector.add_log(f"Log entry {a}")


itterator()

print(log_collector.latest_log())
print(log_collector.get_logs())