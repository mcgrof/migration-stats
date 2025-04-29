#!/usr/bin/env python3

import os

os.system("rm -f *.stats.txt")

with open("guests.txt") as f:
    for line in f:
        guest, dut = line.strip().split()
        os.system(f"ssh {guest} sudo cp /root/stats /home/kdevops/")
        os.system(f"ssh {guest} sudo chown kdevops /home/kdevops/stats")
        os.system(f"scp {guest}:/home/kdevops/stats {dut}.stats.txt")
        print(f"Guest: {guest}\tDUT: {dut}")
