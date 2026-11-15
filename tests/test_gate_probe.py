import unittest


class MergeGateProbe(unittest.TestCase):
    def test_required_checks_block_failing_pr(self):
        self.fail("intentional failure to verify required checks")
