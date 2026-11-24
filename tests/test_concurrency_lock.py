#!/usr/bin/env python3
"""
Unit tests for POSIX fcntl.flock advisory locking behavior.
"""

import unittest
import tempfile
import shutil
import os
import fcntl

class TestConcurrencyLock(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_exclusive_nonblocking_lock(self):
        lock_path = os.path.join(self.test_dir, "test_job.lock")
        
        # Process 1 acquires lock
        fd1 = open(lock_path, "w")
        fcntl.flock(fd1, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # Process 2 attempts to acquire same lock
        fd2 = open(lock_path, "w")
        with self.assertRaises(BlockingIOError):
            fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
        # Process 1 releases lock
        fcntl.flock(fd1, fcntl.LOCK_UN)
        fd1.close()
        
        # Process 2 can now acquire lock
        fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd2, fcntl.LOCK_UN)
        fd2.close()

if __name__ == "__main__":
    unittest.main()
