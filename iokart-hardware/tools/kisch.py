"""Minimal KiCad 7 schematic writer: places library symbols and connects pins by net name.

Every pin gets a short wire stub ending in a net label (or a power symbol), so the
drawing is "label style". Connectivity is recorded so it can be compared with the
netlist KiCad itself exports.
"""
import math
import os
import uuid

SYMDIR = "/usr/share/kicad/symbols"
NS = uuid.UUID("6f1d3a52-0000-4000-8000-000000000000")
G = 1.27


class Str(str):
    """A quoted s-expression string (bare atoms stay plain str)."""


def parse(text):
    stack, cur, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            stack.append(cur)
            cur = []
            i += 1
        elif c == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            cur.append(Str("".join(buf)))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()":
                j += 1
            cur.append(text[i:j])
            i = j
    return cur[0]


def dump(node, depth=0):
    if isinstance(node, Str):
        return '"%s"' % node
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float)):
        return fmt(node)
    inner = [dump(c, depth + 1) for c in node]
    flat = "(" + " ".join(inner) + ")"
    if len(flat) < 110 or depth > 6:
        return flat
    pad = "\n" + "  " * (depth + 1)
    return "(" + inner[0] + pad + pad.join(inner[1:]) + "\n" + "  " * depth + ")"


def fmt(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(str(p) for p in parts)))


_libcache = {}


def _lib(libname):
    if libname not in _libcache:
        path = os.path.join(SYMDIR, libname + ".kicad_sym")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(__file__), "..", "lib", libname + ".kicad_sym")
        with open(path) as f:
            tree = parse(f.read())
        _libcache[libname] = {c[1]: c for c in tree if isinstance(c, list) and c and c[0] == "symbol"}
    return _libcache[libname]


class Pin:
    def __init__(self, number, name, etype, x, y, angle, unit):
        self.number, self.name, self.etype = number, name, etype
        self.x, self.y, self.angle, self.unit = x, y, angle, unit


class LibSym:
    """A library symbol flattened (inheritance resolved) for embedding in a sheet."""

    def __init__(self, lib_id):
        self.lib_id = lib_id
        libname, name = lib_id.split(":")
        node = _lib(libname)[name]
        ext = [c for c in node if isinstance(c, list) and c[0] == "extends"]
        if ext:
            parent = _lib(libname)[ext[0][1]]
            props = {c[1]: c for c in parent if isinstance(c, list) and c[0] == "property"}
            for c in node:
                if isinstance(c, list) and c[0] == "property":
                    props[c[1]] = c
            body = [c for c in parent if isinstance(c, list) and c[0] not in ("property", "symbol")]
            units = []
            for c in parent:
                if isinstance(c, list) and c[0] == "symbol":
                    suffix = c[1][len(parent[1]):]
                    units.append(["symbol", Str(name + suffix)] + c[2:])
            node = ["symbol", Str(name)] + body + list(props.values()) + units
        self.name = name
        self.node = ["symbol", Str(lib_id)] + node[2:]
        self.props = {c[1]: c[2] for c in node if isinstance(c, list) and c[0] == "property"}
        self.pins = []
        self.units = set()
        for c in node:
            if isinstance(c, list) and c[0] == "symbol":
                unit = int(c[1][len(name):].split("_")[1])
                if unit:
                    self.units.add(unit)
                for p in c:
                    if isinstance(p, list) and p[0] == "pin":
                        at = [q for q in p if isinstance(q, list) and q[0] == "at"][0]
                        nm = [q for q in p if isinstance(q, list) and q[0] == "name"][0][1]
                        num = [q for q in p if isinstance(q, list) and q[0] == "number"][0][1]
                        ang = float(at[3]) if len(at) > 3 else 0.0
                        self.pins.append(Pin(str(num), str(nm), p[1], float(at[1]), float(at[2]), ang, unit))
        if not self.units:
            self.units = {1}
        self.is_power = any(isinstance(c, list) and c[0] == "power" for c in node)

    def unit_pins(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]


_symcache = {}


def libsym(lib_id):
    if lib_id not in _symcache:
        _symcache[lib_id] = LibSym(lib_id)
    return _symcache[lib_id]


ROT = {0: (1, 0, 0, -1), 90: (0, -1, -1, 0), 180: (-1, 0, 0, 1), 270: (0, 1, 1, 0)}


def xform(rot, x, y):
    a, b, c, d = ROT[rot]
    return a * x + b * y, c * x + d * y


GROUNDS = {"GND": "power:GND", "GNDA": "power:GNDA", "GNDPWR": "power:GNDPWR",
           "GND1": "power:GND1", "GND2": "power:GND2", "Earth": "power:Earth"}
RAILS = {"+3V3": "power:+3V3", "+5V": "power:+5V", "+5VA": "power:+5VA", "+15V": "power:+15V",
         "-5V": "power:-5V", "+24V": "power:+24V", "+3.3VA": "power:+3.3VA"}
POWER = dict(GROUNDS, **RAILS)
NC = "NC"


class Project:
    def __init__(self, name, title):
        self.name, self.title = name, title
        self.sheets = []
        self.refcount = {}
        self.root_uuid = uid(name, "root")
        self.nets = {}          # net -> set of (ref, pin number)
        self.net_sheets = {}    # net -> set of sheet names
        self.power_out = set()  # nets driven by a power output pin
        self.bom = []

    def ref(self, prefix):
        self.refcount[prefix] = self.refcount.get(prefix, 0) + 1
        return "%s%d" % (prefix, self.refcount[prefix])

    def sheet(self, name, title, paper="A3"):
        s = Sheet(self, name, title, paper, len(self.sheets) + 2)
        self.sheets.append(s)
        return s

    def write(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        for s in self.sheets:
            s.finish()
        for s in self.sheets:
            with open(os.path.join(outdir, s.filename), "w") as f:
                f.write(dump(s.tree()) + "\n")
        root = ["kicad_sch", ["version", "20230121"], ["generator", "iokart_gen"],
                ["uuid", self.root_uuid], ["paper", Str("A4")],
                ["title_block", ["title", Str(self.title)], ["rev", Str("0.1")]],
                ["lib_symbols"]]
        root.append(["text", Str(self.title), ["at", 25, 25, 0],
                     ["effects", ["font", ["size", 3, 3]], ["justify", "left", "bottom"]],
                     ["uuid", uid("roottext")]])
        for i, s in enumerate(self.sheets):
            x, y = 25 + (i % 3) * 85, 40 + (i // 3) * 45
            root.append(["sheet", ["at", x, y], ["size", 70, 30], ["fields_autoplaced"],
                         ["stroke", ["width", 0.1524], ["type", "solid"]],
                         ["fill", ["color", 0, 0, 0, 0.0]], ["uuid", s.uuid],
                         ["property", Str("Sheetname"), Str(s.title), ["at", x, y - 0.7, 0],
                          ["effects", ["font", ["size", 1.5, 1.5]], ["justify", "left", "bottom"]]],
                         ["property", Str("Sheetfile"), Str(s.filename), ["at", x, y + 30.6, 0],
                          ["effects", ["font", ["size", 1.27, 1.27]], ["justify", "left", "top"]]],
                         ["instances", ["project", Str(self.name),
                                        ["path", Str("/" + self.root_uuid), ["page", Str(str(s.page))]]]]])
        root.append(["sheet_instances", ["path", Str("/"), ["page", Str("1")]]])
        with open(os.path.join(outdir, self.name + ".kicad_sch"), "w") as f:
            f.write(dump(root) + "\n")
        pro = os.path.join(outdir, self.name + ".kicad_pro")
        if not os.path.exists(pro):
            with open(pro, "w") as f:
                f.write('{\n  "meta": {"filename": "%s.kicad_pro", "version": 1},\n'
                        '  "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},\n'
                        '  "sheets": [], "text_variables": {}\n}\n' % self.name)


class Sheet:
    def __init__(self, project, name, title, paper, page):
        self.p, self.name, self.title, self.paper, self.page = project, name, title, paper, page
        self.filename = name + ".kicad_sch"
        self.uuid = uid(project.name, "sheet", name)
        self.items, self.used, self.labels, self.pwr = [], {}, [], []
        self.seen = set()
        self.n = 0

    def _u(self, kind):
        self.n += 1
        return uid(self.name, kind, self.n)

    def _instances(self, ref, unit):
        return ["instances", ["project", Str(self.p.name),
                              ["path", Str("/%s/%s" % (self.p.root_uuid, self.uuid)),
                               ["reference", Str(ref)], ["unit", unit]]]]

    def _place(self, sym, ref, value, x, y, rot, unit, footprint="", hide_ref=False, refpos=None, valpos=None):
        self.used[sym.lib_id] = sym
        rx, ry = refpos if refpos else (x, y)
        vx, vy = valpos if valpos else (rx, ry + 2.2)
        fa = 90 if rot in (90, 270) else 0
        node = ["symbol", ["lib_id", Str(sym.lib_id)], ["at", x, y, rot], ["unit", unit],
                ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["uuid", self._u("sym")],
                ["property", Str("Reference"), Str(ref), ["at", rx, ry, fa],
                 ["effects", ["font", ["size", 1.27, 1.27]]] + ([ "hide"] if hide_ref else [])],
                ["property", Str("Value"), Str(value), ["at", vx, vy, fa],
                 ["effects", ["font", ["size", 1.27, 1.27]]] + (["hide"] if sym.is_power and False else [])],
                ["property", Str("Footprint"), Str(footprint), ["at", x, y, 0],
                 ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
                ["property", Str("Datasheet"), Str(sym.props.get("Datasheet", "")), ["at", x, y, 0],
                 ["effects", ["font", ["size", 1.27, 1.27]], "hide"]]]
        for p in sym.unit_pins(unit):
            node.append(["pin", Str(p.number), ["uuid", self._u("pin")]])
        node.append(self._instances(ref, unit))
        self.items.append(node)

    def _wire(self, x1, y1, x2, y2):
        self.items.append(["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]],
                           ["stroke", ["width", 0], ["type", "default"]], ["uuid", self._u("w")]])

    def text(self, s, x, y, size=2.0):
        self.items.append(["text", Str(s), ["at", x, y, 0],
                           ["effects", ["font", ["size", size, size]], ["justify", "left", "bottom"]],
                           ["uuid", self._u("t")]])

    def _connect(self, net, x, y, dx, dy, stub=2.54):
        """Attach `net` to the point (x, y); (dx, dy) is the outward direction on the sheet."""
        if net == NC:
            self.items.append(["no_connect", ["at", x, y], ["uuid", self._u("nc")]])
            return
        ex, ey = x + dx * stub, y + dy * stub
        key = (net, round(x, 3), round(y, 3), dx, dy)
        if key in self.seen:
            return
        self.seen.add(key)
        self._wire(x, y, ex, ey)
        self.p.net_sheets.setdefault(net, set()).add(self.name)
        if net in POWER:
            ground = net in GROUNDS
            if (dx, dy) == (0, -1):
                rot = 180 if ground else 0
            elif (dx, dy) == (0, 1):
                rot = 0 if ground else 180
            elif (dx, dy) == (-1, 0):
                rot = 270 if ground else 90
            else:
                rot = 90 if ground else 270
            self.pwr.append((net, ex, ey, rot, dx))
        else:
            ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
            self.labels.append((net, ex, ey, ang))

    def part(self, lib_id, prefix, value, x, y, nets, rot=0, unit=1, footprint="", ref=None, stub=2.54,
             refpos=None, valpos=None):
        """Place one unit of a symbol. `nets` maps pin number or pin name to a net name (or NC)."""
        sym = libsym(lib_id)
        ref = ref or self.p.ref(prefix)
        self._place(sym, ref, value, x, y, rot, unit, footprint, refpos=refpos, valpos=valpos)
        used = set()
        for p in sym.unit_pins(unit):
            if p.number in nets:
                key = p.number
            elif p.name in nets:
                key = p.name
            else:
                raise KeyError("%s (%s): pin %s '%s' has no net" % (ref, lib_id, p.number, p.name))
            used.add(key)
            net = nets[key]
            px, py = xform(rot, p.x, p.y)
            a = math.radians(p.angle)
            ox, oy = xform(rot, -round(math.cos(a)), -round(math.sin(a)))
            self._connect(net, x + px, y + py, int(ox), int(oy), stub)
            if net != NC:
                self.p.nets.setdefault(net, set()).add((ref, p.number))
                if p.etype == "power_out":
                    self.p.power_out.add(net)
        extra = set(nets) - used
        if extra:
            raise KeyError("%s (%s): unknown pins %s" % (ref, lib_id, sorted(extra)))
        if unit == 1:
            self.p.bom.append((ref, value, lib_id, footprint))
        return ref

    def two(self, lib_id, prefix, value, a, b, x, y, footprint="", horiz=None):
        """Two-pin part with pin 1 on net `a`, pin 2 on net `b`. Rails go up, grounds go down."""
        sym = libsym(lib_id)
        pins = {p.number: p for p in sym.unit_pins(1)}
        p1 = pins["1"]
        if horiz is None:
            horiz = not (a in POWER or b in POWER)
        first_low = a in GROUNDS or (b in RAILS and a not in RAILS)
        want = (1, 0) if horiz and first_low else (-1, 0) if horiz else (0, 1) if first_low else (0, -1)
        for rot in (0, 90, 180, 270):
            px, py = xform(rot, p1.x, p1.y)
            if (px > 0) - (px < 0) == want[0] and (py > 0) - (py < 0) == want[1]:
                break
        ref = self.p.ref(prefix)
        if horiz:
            refpos, valpos = (x, y - 5.2), (x, y - 3.2)
        else:
            refpos = (x + 2.6 + 0.6 * len(ref), y - 1.2)
            valpos = (x + 2.6 + 0.6 * len(value), y + 1.0)
        return self.part(lib_id, prefix, value, x, y, {"1": a, "2": b}, rot=rot, footprint=footprint,
                         ref=ref, refpos=refpos, valpos=valpos)

    def finish(self):
        for net, x, y, ang in self.labels:
            just = ["justify", "right", "bottom"] if ang in (180, 270) else ["justify", "left", "bottom"]
            if len(self.p.net_sheets[net]) > 1:
                gj = ["justify", "right"] if ang in (180, 270) else ["justify", "left"]
                self.items.append(["global_label", Str(net), ["shape", "passive"], ["at", x, y, ang],
                                   ["fields_autoplaced"],
                                   ["effects", ["font", ["size", 1.27, 1.27]], gj], ["uuid", self._u("gl")],
                                   ["property", Str("Intersheetrefs"), Str("${INTERSHEET_REFS}"),
                                    ["at", x, y, 0], ["effects", ["font", ["size", 1.27, 1.27]], "hide"]]])
            else:
                self.items.append(["label", Str(net), ["at", x, y, ang], ["fields_autoplaced"],
                                   ["effects", ["font", ["size", 1.27, 1.27]], just], ["uuid", self._u("l")]])
        for net, x, y, rot, dx in self.pwr:
            sym = libsym(POWER[net])
            ref = self.p.ref("#PWR")
            self.used[sym.lib_id] = sym
            up = rot in (0,) and net in RAILS or rot == 180 and net in GROUNDS
            vy = y - 3.6 if (net in RAILS and rot == 0) or (net in GROUNDS and rot == 180) else y + 3.9
            vx = x
            if rot in (90, 270):
                vx, vy = x + dx * (4.6 + 0.45 * len(net)), y
            self.items.append(
                ["symbol", ["lib_id", Str(sym.lib_id)], ["at", x, y, rot], ["unit", 1],
                 ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["uuid", self._u("pw")],
                 ["property", Str("Reference"), Str(ref), ["at", x, y, 0],
                  ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
                 ["property", Str("Value"), Str(net), ["at", vx, vy, 90 if rot in (90, 270) else 0],
                  ["effects", ["font", ["size", 1.0, 1.0]]]],
                 ["property", Str("Footprint"), Str(""), ["at", x, y, 0],
                  ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
                 ["property", Str("Datasheet"), Str(""), ["at", x, y, 0],
                  ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
                 ["pin", Str("1"), ["uuid", self._u("pin")]],
                 self._instances(ref, 1)])

    def flag(self, net, x, y):
        """PWR_FLAG on a power net that no power-output pin drives."""
        sym = libsym("power:PWR_FLAG")
        ref = self.p.ref("#FLG")
        self.used[sym.lib_id] = sym
        self.items.append(
            ["symbol", ["lib_id", Str(sym.lib_id)], ["at", x, y, 0], ["unit", 1],
             ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["uuid", self._u("fl")],
             ["property", Str("Reference"), Str(ref), ["at", x, y, 0],
              ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
             ["property", Str("Value"), Str("PWR_FLAG"), ["at", x, y - 4.5, 0],
              ["effects", ["font", ["size", 1.0, 1.0]]]],
             ["property", Str("Footprint"), Str(""), ["at", x, y, 0],
              ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
             ["property", Str("Datasheet"), Str(""), ["at", x, y, 0],
              ["effects", ["font", ["size", 1.27, 1.27]], "hide"]],
             ["pin", Str("1"), ["uuid", self._u("pin")]], self._instances(ref, 1)])
        self._connect(net, x, y, 0, 1)

    def tree(self):
        t = ["kicad_sch", ["version", "20230121"], ["generator", "iokart_gen"], ["uuid", self.uuid],
             ["paper", Str(self.paper)],
             ["title_block", ["title", Str(self.title)], ["rev", Str("0.1")],
              ["company", Str(self.p.title)]],
             ["lib_symbols"] + [s.node for s in self.used.values()]]
        return t + self.items


def make_symbol(libname, name, left, right, footprint="", datasheet="", width=25.4):
    """Register a rectangular symbol. left/right: lists of (number, pin name, type) or None for a gap."""
    rows = max(len(left), len(right))
    top = (rows - 1) * 2.54 / 2
    top = round(top / 2.54) * 2.54
    hw = width / 2
    f = ["effects", ["font", ["size", 1.27, 1.27]]]
    pins = []
    for side, x, ang in ((left, -hw - 2.54, 0), (right, hw + 2.54, 180)):
        for i, p in enumerate(side):
            if p:
                pins.append(["pin", p[2], "line", ["at", x, top - i * 2.54, ang], ["length", 2.54],
                             ["name", Str(p[1]), f], ["number", Str(p[0]), f]])
    node = ["symbol", Str(name), ["in_bom", "yes"], ["on_board", "yes"],
            ["property", Str("Reference"), Str("U"), ["at", -hw, top + 5.08, 0], f],
            ["property", Str("Value"), Str(name), ["at", hw, top + 5.08, 0], f],
            ["property", Str("Footprint"), Str(footprint), ["at", 0, 0, 0], f + ["hide"]],
            ["property", Str("Datasheet"), Str(datasheet), ["at", 0, 0, 0], f + ["hide"]],
            ["symbol", Str(name + "_0_1"),
             ["rectangle", ["start", -hw, top + 2.54], ["end", hw, top - (rows - 1) * 2.54 - 2.54],
              ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]]],
            ["symbol", Str(name + "_1_1")] + pins]
    _libcache.setdefault(libname, {})[name] = node
    return node


def write_lib(libname, path):
    tree = ["kicad_symbol_lib", ["version", "20220914"], ["generator", "iokart_gen"]] + \
        list(_libcache[libname].values())
    with open(path, "w") as f:
        f.write(dump(tree) + "\n")
