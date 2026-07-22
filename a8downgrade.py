#!/usr/bin/env python3
"""
a8downgrade.py — OS-only iOS downgrade tool for A8 devices (iPhone 6 / 6 Plus)

Scope / important limitations:
  - This tool ONLY downgrades the AP (application processor) firmware + OS.
  - It does NOT downgrade SEP or baseband. Those stay on whatever version
    is currently signed by Apple on the device, because doing otherwise
    requires SHSH blobs with matching SEP/BB tickets captured at the time
    Apple was signing that version.
  - Practical effect: Touch ID / Secure Enclave-dependent features and
    cellular baseband functionality may be degraded or non-functional
    after downgrade, depending on how far apart the OS and SEP versions are.
  - This tool does not implement the checkm8 bootrom exploit itself.
    It orchestrates existing, widely-used open-source tools:
        - ipwndfu      (pwned DFU entry via checkm8, A8-compatible)
        - idevicerestore (drives the actual restore against an IPSW)
        - libimobiledevice CLI tools (device state detection)
    Install these separately; see README.md.

Usage:
    python3 a8downgrade.py --ipsw path/to/target.ipsw [--dry-run]
"""

import argparse
import shutil
import subprocess
import sys
import time

REQUIRED_TOOLS = ["idevice_id", "ideviceinfo", "idevicerestore", "ipwndfu"]


def check_dependencies():
    """Verify required external tools are on PATH before doing anything else."""
    missing = [t for t in REQUIRED_TOOLS if shutil.which(t) is None]
    if missing:
        print("Missing required tools on PATH:", ", ".join(missing))
        print("See README.md for install instructions per platform.")
        sys.exit(1)


def run(cmd, **kwargs):
    """Thin wrapper so every external call is logged the same way."""
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=False, **kwargs)


def get_device_state():
    """
    Returns one of: 'normal', 'recovery', 'dfu', 'none'
    Uses idevice_id / ideviceinfo / irecovery (from libirecovery) to probe.
    """
    normal = run(["idevice_id", "-l"], capture_output=True, text=True)
    if normal.stdout.strip():
        return "normal"

    # irecovery -q reports mode when device is in Recovery or DFU
    irec = run(["irecovery", "-q"], capture_output=True, text=True)
    out = irec.stdout.lower()
    if "dfu" in out:
        return "dfu"
    if "recovery" in out:
        return "recovery"

    return "none"


def enter_pwned_dfu():
    """
    Drives ipwndfu to put an A8 device into pwned DFU mode using checkm8.
    Assumes the device is ALREADY in plain DFU mode (user's responsibility:
    hold power+home, follow the standard DFU button timing).
    """
    print("\n[Step] Entering pwned DFU via checkm8 (ipwndfu)...")
    result = run(["ipwndfu", "--pwn"])
    if result.returncode != 0:
        print("Failed to enter pwned DFU. Make sure the device is in plain "
              "DFU mode and is an A8 device (iPhone 6 / 6 Plus).")
        sys.exit(1)
    print("Device is now in pwned DFU mode.")


def restore_os_only(ipsw_path, dry_run=False):
    """
    Drives idevicerestore against the target IPSW, OS-only (no baseband/SEP
    matching attempted). idevicerestore will use the pwned DFU state to
    bypass Apple's normal signature-server check for the AP firmware.
    """
    cmd = ["idevicerestore", "-d", "--no-input", ipsw_path]
    # -d = debug output, useful for diagnosing partial-restore failures
    print("\n[Step] Starting OS-only restore...")
    print("NOTE: SEP and baseband will remain on the currently signed "
          "version. Touch ID and cellular functionality may be degraded.")

    if dry_run:
        print("[Dry run] Would execute:", " ".join(cmd))
        return

    result = run(cmd)
    if result.returncode != 0:
        print("\nRestore failed. Common causes:")
        print("  - Device dropped out of pwned DFU mid-restore (retry)")
        print("  - IPSW doesn't match device model/board")
        print("  - idevicerestore version too old for this iOS target")
        sys.exit(1)

    print("\nRestore completed. Device should boot into the older iOS "
          "version with current SEP/baseband still active.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ipsw", required=True, help="Path to the target (older) IPSW file")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print the steps/commands without executing the restore")
    args = parser.parse_args()

    check_dependencies()

    print("=== A8 OS-only Downgrade Tool ===")
    print("Scope: AP/OS downgrade only. SEP + baseband are NOT downgraded.\n")

    state = get_device_state()
    print(f"Detected device state: {state}")

    if state == "none":
        print("No device detected. Connect the iPhone 6/6 Plus and put it "
              "into DFU mode (or Normal mode if you want state re-checked).")
        sys.exit(1)

    if state != "dfu":
        print("Device must be in DFU mode before continuing.")
        print("DFU entry (A8 / iPhone 6 & 6 Plus):")
        print("  1. Connect device, hold Power + Home for 8 seconds")
        print("  2. Release Power, keep holding Home for 5 more seconds")
        print("  3. Screen should stay black (no Apple logo / iTunes logo)")
        sys.exit(1)

    enter_pwned_dfu()
    restore_os_only(args.ipsw, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
