# Ray–sphere FP64 hardware design

`rtl/ray_sphere_accel.sv` implements a sequential, one-request-at-a-time
ray–sphere query with ready/valid interfaces. It contains real licensed FP64
arithmetic through Berkeley HardFloat, plus the project's FSM and registers.
It is not wired into the Python renderer and has not been simulated,
synthesized, or measured on hardware.

See [`../docs/HARDWARE_DESIGN.md`](../docs/HARDWARE_DESIGN.md) for the complete
contract, diagram, cycle/frequency assumptions and software boundary.

From the repository root:

```sh
# Optional syntax/elaboration checker; use a Python environment of your choice.
python3 -m pip install pyslang==11.0.0
python3 -B hardware/check_syntax.py

# Python packing and reference-expression checks, not HDL simulation.
python3 -B hardware/host/check_interface.py

# Explicitly hypothetical performance sensitivity.
python3 -B hardware/estimate.py
python3 -B hardware/estimate.py --root-fraction 0.5 --offloaded-fraction 0.7
```

No dependency installation is required to read or submit the RTL. The syntax
checker uses `files.f`, including all required HardFloat modules. It narrowly
downgrades one legacy HardFloat output/wire redeclaration diagnostic; source
files are kept unmodified. With Icarus Verilog available, an alternative compile-only command is:

```sh
iverilog -g2012 -s ray_sphere_accel -f hardware/files.f -o /tmp/ray_sphere_compile.vvp
```

Do not run the resulting object as evidence of behavioral validation because no
HDL testbench is included here.

- `rtl/`: the sequential controller and FP64 adapters.
- `vendor/HardFloat-1/`: selected unmodified official source, license, hashes.
- `host/interface.py`: request/response packing and scalar host reference;
  no working hardware driver or fake transport.
- `architecture.mmd`: editable diagram source.
- `estimate.py`: parameterized analytical model.
- `validation.json`: performed checks and material limitations.
- `report_summary.json`: facts suitable for the project report, explicitly
  distinguishing implementation, observed software evidence and assumptions.
