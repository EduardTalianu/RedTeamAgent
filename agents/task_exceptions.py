"""
Task-related exceptions for the agent system.
"""

class FixableTaskException(Exception):
    """Base class for exceptions that can be fixed by retrying or adjusting parameters."""
    pass

class UnfixableTaskException(Exception):
    """Base class for exceptions that cannot be fixed and require task termination."""
    pass

class TaskTimeoutException(FixableTaskException):
    """Exception raised when a task times out."""
    def __init__(self, message):
        super().__init__(message)

class TaskImpossibleException(UnfixableTaskException):
    """Exception raised when a task is impossible to complete."""
    def __init__(self, message):
        super().__init__(message)

class TaskNeedTurningException(FixableTaskException):
    """Exception raised when a task needs to be turned or modified."""
    def __init__(self, message):
        super().__init__(message)