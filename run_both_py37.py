# -*- coding: utf-8 -*-
"""
run_both.py
===========

Master launcher to execute Dance_Nao.py (motion) and Eye_LED_Nao.py (light show)
simultaneously in parallel from a single terminal.

Usage:
    python run_both.py --ip 172.20.10.8:9559,172.20.10.5:9561
    python run_both.py --dry-run
"""

from __future__ import print_function

import os
import subprocess
import sys
import time

def main():
    args = sys.argv[1:]
    if not any(arg.startswith("--ip") for arg in args):
        args = ["--ip", "172.20.10.8:9559,172.20.10.5:9561"] + args

    script_dir = os.path.dirname(os.path.realpath(__file__))
    dance_script = os.path.join(script_dir, "Dance_Nao_py37.py")
    eyes_script = os.path.join(script_dir, "Eye_LED_Nao_py37.py")

    print("=" * 60)
    print("Launching Dance and Eye LED shows simultaneously...")
    print("=" * 60)

    # Launch both scripts in parallel subprocesses
    p_dance = subprocess.Popen([sys.executable, dance_script] + args)
    p_eyes = subprocess.Popen([sys.executable, eyes_script] + args)

    try:
        # Wait for both processes to complete
        p_dance.wait()
        p_eyes.wait()
        if p_dance.returncode == 0 and p_eyes.returncode == 0:
            print("\nBoth shows completed successfully.")
        else:
            print("\nShow failed: dance exit=%s, eyes exit=%s" % (p_dance.returncode, p_eyes.returncode))
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nTerminating both shows...")
        try: p_dance.terminate()
        except: pass
        try: p_eyes.terminate()
        except: pass
        p_dance.wait()
        p_eyes.wait()

if __name__ == "__main__":
    main()
