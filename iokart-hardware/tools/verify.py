#!/usr/bin/env python3
"""Compares the netlist KiCad exported (out/iokart.net) with netlist_expected.txt."""
import os
import sys
import kisch

root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
exp = {}
for line in open(os.path.join(root, "netlist_expected.txt")):
    name, nodes = line.rstrip("\n").split(": ")
    exp[name] = frozenset(nodes.split())
tree = kisch.parse(open(os.path.join(root, "out", "iokart.net")).read())
nets = [c for c in tree if isinstance(c, list) and c[0] == "nets"][0]
got = {}
for net in nets[1:]:
    name = [c for c in net if c[0] == "name"][0][1]
    nodes = frozenset("%s.%s" % ([q for q in c if q[0] == "ref"][0][1], [q for q in c if q[0] == "pin"][0][1])
                      for c in net if c[0] == "node")
    got[name] = nodes
gotsets = {v: k for k, v in got.items()}
bad = 0
for name, nodes in sorted(exp.items()):
    if nodes not in gotsets:
        bad += 1
        near = [k for k, v in got.items() if v & nodes]
        print("MISMATCH %s: expected %d nodes; KiCad has them in %s" % (name, len(nodes), near[:6]))
allexp = set().union(*exp.values())
stray = [k for k, v in got.items() if not (v & allexp) and not k.startswith("unconnected-")]
print("expected nets: %d, matched: %d, mismatched: %d, unexpected KiCad nets: %s"
      % (len(exp), len(exp) - bad, bad, stray))
sys.exit(1 if bad or stray else 0)
