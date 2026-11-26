import threading
import unittest

from ghostclip.shredder import GhostTimer


class TestTimer(unittest.TestCase):
    def test_timer_arm_and_disarm(self):
        timer = GhostTimer()
        self.assertFalse(timer.is_armed())
        timer.arm(10)
        self.assertTrue(timer.is_armed())
        self.assertGreaterEqual(timer.remaining_seconds(), 9)
        timer.disarm()
        self.assertFalse(timer.is_armed())
        self.assertEqual(timer.remaining_seconds(), 0)

    def test_timer_callback_fires_on_expire(self):
        timer = GhostTimer()
        expired = threading.Event()
        timer.arm(0.05, on_expire=expired.set)
        self.assertTrue(expired.wait(timeout=1.0))
        self.assertFalse(timer.is_armed())

    def test_disarm_and_rearm_cancel_old_callback(self):
        timer = GhostTimer()
        first_called = threading.Event()
        second_called = threading.Event()

        timer.arm(0.05, on_expire=first_called.set)
        timer.arm(0.08, on_expire=second_called.set)

        self.assertTrue(second_called.wait(timeout=1.0))
        self.assertFalse(first_called.is_set())

        third_called = threading.Event()
        timer.arm(0.05, on_expire=third_called.set)
        timer.disarm()
        self.assertFalse(third_called.wait(timeout=0.12))


if __name__ == "__main__":
    unittest.main()
