import unittest
from ghostclip.timer import GhostTimer


class TestTimer(unittest.TestCase):

    def test_timer_arm_and_disarm(self):
        timer = GhostTimer()
        self.assertFalse(timer.is_armed())
        timer.arm(10, "Test Secret")
        self.assertTrue(timer.is_armed())
        self.assertGreaterEqual(timer.remaining_seconds(), 9)
        timer.disarm()
        self.assertFalse(timer.is_armed())


if __name__ == "__main__":
    unittest.main()
