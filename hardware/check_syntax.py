#!/usr/bin/env python3
"""Elaborate RTL with slang (pyslang); does not simulate or synthesize hardware.

Optional dependency: python3 -m pip install pyslang==11.0.0
Run from anywhere: python3 -B hardware/check_syntax.py
"""
import os
from pathlib import Path
import sys

try:
    from pyslang.driver import Driver
except ImportError:
    sys.exit("Syntax checker unavailable: install pyslang==11.0.0 in a Python environment.")

root = Path(__file__).resolve().parents[1]
os.chdir(root)
driver = Driver()
driver.addStandardArgs()
if not driver.parseCommandLine("slang --top ray_sphere_accel -Wno-error=redefinition -f hardware/files.f"):
    sys.exit(1)
if not driver.processOptions() or not driver.parseAllSources():
    driver.reportDiagnostics(False)
    sys.exit(1)
compilation = driver.createCompilation()
driver.reportCompilation(compilation, False)
ok = driver.reportDiagnostics(False)
if not ok:
    sys.exit(1)
print("RTL syntax/elaboration: PASS (not behavioral verification or synthesis)")
