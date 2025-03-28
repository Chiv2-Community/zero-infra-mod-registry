"""
Pytest configuration file to help with module importing.
This makes the 'zero_infra_mod_registry' package importable in tests.
"""
import os
import sys

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
