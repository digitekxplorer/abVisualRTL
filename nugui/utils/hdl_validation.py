"""Shared HDL identifier validation (review findings 2.3 / 2.4).

State names, port names, and the module name are emitted verbatim into
both SystemVerilog and VHDL, so a legal name must satisfy the identifier
rules and avoid the reserved words of BOTH languages.
"""
import re

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

SV_KEYWORDS = frozenset("""
alias always always_comb always_ff always_latch and assert assign automatic
begin bit break buf byte case casex casez cell class clocking config const
continue cover default defparam design disable do edge else end endcase
endclass endclocking endconfig endfunction endgenerate endinterface endmodule
endpackage endprimitive endprogram endproperty endspecify endsequence endtable
endtask enum event expect export extends extern final for force foreach forever
fork forkjoin function generate genvar if iff import initial inout input inside
instance int integer interface join local localparam logic longint module nand
negedge new nor not null or output package parameter posedge primitive priority
program property protected pure rand randc real realtime ref reg release repeat
return sequence shortint shortreal signed specify static string struct super
supply0 supply1 table task this time timeprecision timeunit tri tri0 tri1
type typedef union unique unsigned var virtual void wait wand weak while wire
wor xnor xor
""".split())

VHDL_KEYWORDS = frozenset("""
abs access after alias all and architecture array assert attribute begin block
body buffer bus case component configuration constant disconnect downto else
elsif end entity exit file for function generate generic group guarded if
impure in inertial inout is label library linkage literal loop map mod nand
new next nor not null of on open or others out package port postponed
procedure process pure range record register reject rem report return rol ror
select severity shared signal sla sll sra srl subtype then to transport type
unaffected units until use variable wait when while with xnor xor
""".split())


def validate_identifier(name: str, what: str = "Name") -> str:
    """Returns an error message, or '' if the name is a legal identifier
    in both SystemVerilog and VHDL."""
    name = (name or "").strip()
    if not name:
        return f"{what} cannot be empty."
    if not IDENT_RE.match(name):
        return (f"{what} '{name}' is not a valid HDL identifier "
                "(letters, digits, underscore; must start with a letter).")
    low = name.lower()
    if low in SV_KEYWORDS:
        return f"{what} '{name}' is a SystemVerilog reserved word."
    if low in VHDL_KEYWORDS:
        return f"{what} '{name}' is a VHDL reserved word."
    return ""


def validate_project(settings, nodes) -> list:
    """Full pre-generation check. Returns a list of error strings
    (empty when the project is clean). VHDL is case-insensitive, so all
    duplicate checks fold case."""
    errors = []

    err = validate_identifier(settings.project_name, "Module name")
    if err: errors.append(err)
    err = validate_identifier(settings.clock_name, "Clock name")
    if err: errors.append(err)
    err = validate_identifier(settings.reset_name, "Reset name")
    if err: errors.append(err)

    # Signal namespace: clock + reset + user ports must all be distinct.
    seen = {}
    for label, name in [("clock", settings.clock_name), ("reset", settings.reset_name)]:
        seen[name.strip().lower()] = label
    for port in settings.ports:
        err = validate_identifier(port.name, "Port name")
        if err: errors.append(err)
        low = port.name.strip().lower()
        if low in seen:
            errors.append(f"Port '{port.name}' collides with {seen[low]} name.")
        else:
            seen[low] = f"port '{port.name}'"

    # State names: valid, and unique among themselves AND against signals
    # (VHDL enum literals share the declarative namespace with signals).
    state_seen = set()
    for node in nodes.values():
        err = validate_identifier(node.name, "State name")
        if err: errors.append(err)
        low = node.name.strip().lower()
        if low in state_seen:
            errors.append(f"Duplicate state name '{node.name}'.")
        state_seen.add(low)
        if low in seen:
            errors.append(f"State '{node.name}' collides with {seen[low]}.")

    return errors
