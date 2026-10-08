"""Console-script aliases specified in EV-1.0."""
import sys
from .__main__ import main


def check():
    sys.argv.insert(1, 'check')
    return main()


def batch():
    sys.argv.insert(1, 'batch')
    return main()
