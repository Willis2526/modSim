""" Utility classes and functions """
import signal

class SignalHandler:
    """Handle Signals"""

    def __init__(self):
        self.stop = False

        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def shutdown(self, signum, frame):
        """Callback for signals"""
        self.stop = True