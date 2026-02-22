import unittest
import os
import subprocess
import shutil
import tempfile
from pathlib import Path
import time

import re

def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class TestTuiIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_dir = self.test_dir / "repo"
        self.repo_dir.mkdir()
        
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=self.repo_dir, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "initial commit"], cwd=self.repo_dir, check=True)
        
        # Determine the root of the easy-worktree project (where wt is)
        # Assuming we are running from the easy-worktree-tui project root
        self.wt_cmd = ["uv", "run", "--project", "/home/igtm/tmp/easy-worktree", "wt"]
        self.wtt_cmd = ["uv", "run", "wtt"]
        
        # Initialize easy-worktree
        subprocess.run(self.wt_cmd + ["init"], cwd=self.repo_dir, check=True)

    def tearDown(self):
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def test_version(self):
        """Test wtt --version"""
        res = subprocess.run(
            self.wtt_cmd + ["--version"],
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            check=True
        )
        self.assertIn("easy-worktree-tui version", res.stdout)

    def test_list_parsing_in_tui_logic(self):
        """
        Verify that the parsing logic used in main.py works with actual 'wt list' output.
        We can't easily test the TUI UI, but we can test the data processing.
        """
        # Add a worktree
        subprocess.run(self.wt_cmd + ["add", "feat1"], cwd=self.repo_dir, check=True)
        
        # Run wt list to see the output format
        res = subprocess.run(self.wt_cmd + ["list"], cwd=self.repo_dir, capture_output=True, text=True, check=True)
        output = strip_ansi(res.stdout)
        
        # Verify the separator exists
        self.assertIn("---", output)
        
        # Test the parsing logic (copy-pasted from main.py for verification)
        lines = output.strip().splitlines()
        separator_index = -1
        for i, line in enumerate(lines):
            if line.startswith("---") or "---" in line:
                separator_index = i
                break
        
        self.assertNotEqual(separator_index, -1)
        
        worktrees = []
        for line in lines[separator_index + 1:]:
            parts = line.split()
            if not parts: continue
            name = parts[0].strip("()")
            branch = parts[1] if len(parts) > 1 else "unknown"
            
            # Check if wt co <name> works
            co_res = subprocess.run(self.wt_cmd + ["co", name], cwd=self.repo_dir, capture_output=True, text=True)
            raw_path = co_res.stdout.strip()
            path = Path(raw_path)
            if not path.is_absolute():
                path = self.repo_dir / path
            
            self.assertTrue(path.exists())
            
            worktrees.append((name, branch, path))

        worktrees.sort()
        self.assertEqual(len(worktrees), 2) # main and feat1
        self.assertEqual(worktrees[0][0], "feat1") # f comes before m
        self.assertEqual(worktrees[1][0], "main")

if __name__ == "__main__":
    unittest.main()
