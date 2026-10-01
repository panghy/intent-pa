"""Run python3 -m examples.demo for an offline timeout/restart demonstration."""

from pathlib import Path
from tempfile import TemporaryDirectory

from examples.lifecycle import Lifecycle, Receipt, Unknown


class FakeTransport:
    capabilities = set()

    def __init__(self):
        self.messages = {}
        self.send_count = 0

    def send(self, key, text):
        self.send_count += 1
        self.messages[key] = Receipt("fake-message-1", "delivered")
        raise Unknown("Provider accepted it, but the response was lost")

    def lookup(self, key):
        return self.messages.get(key)


def main():
    transport = FakeTransport()
    with TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.sqlite"
        lifecycle = Lifecycle(path)
        lifecycle.bind_owner("example-owner")
        lifecycle.receive("principal", "direct", "request-1", 0)
        lifecycle.enqueue("reply-1", "The requested draft is ready.")
        lifecycle.flush(transport, 0)
        lifecycle.close()
        restarted = Lifecycle(path)
        restarted.flush(transport, 30)
        assert transport.send_count == 1
        assert restarted.state["outbox"]["reply-1"]["state"] == "delivered"
        assert not restarted.receive("principal", "direct", "request-1", 30)
        restarted.close()
    print("Offline replay passed: one send, reconciled delivery, duplicate input suppressed.")


if __name__ == "__main__":
    main()
