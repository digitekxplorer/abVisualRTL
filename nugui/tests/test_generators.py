"""Generator unit tests (review finding 5.4).

Run from the project root:  python -m pytest tests/ -v
The generators are pure functions of (settings, nodes, lines), so no GUI
is needed. These tests cover review findings 1.2, 1.3, 2.1-2.6.
"""
import pytest

from nugui.models.project import ProjectSettings
from nugui.models.ports import Port, PortDirection
from nugui.models.elements import StateNode, TransitionLine
from nugui.generators.system_verilog import SystemVerilogGenerator
from nugui.generators.vhdl import VHDLGenerator


# ---------- Builders ----------

def make_settings(ports=None, **kw):
    s = ProjectSettings(project_name="fsm_test", **kw)
    s.ports = ports or []
    return s


def node(nid, name, reset=False, actions=None):
    return StateNode(id=nid, name=name, x=0, y=0,
                     is_reset_state=reset, actions=actions or [])


def trans(tid, src, dst, cond="1", prio=1, action=""):
    return TransitionLine(id=tid, start_state_id=src, end_state_id=dst,
                          condition=cond, priority=prio, action=action)


def toggle_fsm():
    """2-state toggle: IDLE -(go)-> RUN, RUN -> IDLE (unconditional)."""
    nodes = {0: node(0, "IDLE", reset=True), 1: node(1, "RUN")}
    lines = [trans(0, 0, 1, cond="go"), trans(1, 1, 0)]
    return nodes, lines


def gen_sv(settings, nodes, lines):
    return SystemVerilogGenerator(settings, nodes, lines).generate()


def gen_vhdl(settings, nodes, lines):
    return VHDLGenerator(settings, nodes, lines).generate()


# ---------- 1.2: VHDL sensitivity list ----------

class TestSensitivityList:
    def test_no_input_ports_no_trailing_comma(self):
        nodes, lines = toggle_fsm()
        code = gen_vhdl(make_settings(), nodes, lines)
        assert "process(state_reg)" in code
        assert "state_reg, )" not in code

    def test_input_ports_listed(self):
        ports = [Port("go", PortDirection.IN, 1),
                 Port("led", PortDirection.OUT, 1)]
        nodes, lines = toggle_fsm()
        code = gen_vhdl(make_settings(ports=ports), nodes, lines)
        assert "process(state_reg, go)" in code
        assert "led" not in code.split("-- Next State Logic")[1].splitlines()[1]


# ---------- 1.3: VHDL if/else structure ----------

class TestVhdlIfElse:
    def test_balanced_if_endif(self):
        nodes, lines = toggle_fsm()
        code = gen_vhdl(make_settings(), nodes, lines)
        body = code.split("-- Next State Logic")[1]
        opens = len([l for l in body.splitlines() if l.strip().startswith("if ")])
        closes = body.count("end if;")
        assert opens == closes

    def test_unconditional_first_branch_no_dangling_else(self):
        # First (and only) transition unconditional: no if/else at all
        nodes = {0: node(0, "A", reset=True), 1: node(1, "B")}
        lines = [trans(0, 0, 1, cond="1")]
        code = gen_vhdl(make_settings(), nodes, lines)
        body = code.split("-- Next State Logic")[1]
        assert "else" not in body
        assert "end if;" not in body

    def test_conditional_then_else_fallback(self):
        nodes = {0: node(0, "A", reset=True), 1: node(1, "B"), 2: node(2, "C")}
        lines = [trans(0, 0, 1, cond="x = '1'", prio=1),
                 trans(1, 0, 2, cond="1", prio=2)]
        code = gen_vhdl(make_settings(), nodes, lines)
        body = code.split("-- Next State Logic")[1]
        assert "if x = '1' then" in body
        assert "else" in body
        assert body.count("end if;") == 1


# ---------- 2.1: latch prevention ----------

class TestLatchPrevention:
    PORTS = [Port("led", PortDirection.OUT, 1, "0"),
             Port("data", PortDirection.OUT, 8, "0"),
             Port("go", PortDirection.IN, 1)]

    def test_sv_default_outputs(self):
        nodes, lines = toggle_fsm()
        code = gen_sv(make_settings(ports=self.PORTS), nodes, lines)
        comb = code.split("always_comb")[1]
        assert "led = 1'b0;" in comb
        assert "data = 8'd0;" in comb
        # Inputs must NOT be assigned
        assert "go =" not in comb

    def test_vhdl_default_outputs(self):
        nodes, lines = toggle_fsm()
        code = gen_vhdl(make_settings(ports=self.PORTS), nodes, lines)
        comb = code.split("-- Next State Logic")[1]
        assert "led <= '0';" in comb
        assert "data <= (others => '0');" in comb


# ---------- 2.2: blocking assignments in SV always_comb ----------

class TestBlockingAssignment:
    def test_moore_action_normalized(self):
        nodes = {0: node(0, "A", reset=True, actions=["led <= 1"]),
                 1: node(1, "B")}
        lines = [trans(0, 0, 1)]
        code = gen_sv(make_settings(), nodes, lines)
        comb = code.split("always_comb")[1]
        assert "led = 1;" in comb
        assert "led <= 1" not in comb

    def test_comparison_not_rewritten(self):
        nodes, lines = toggle_fsm()
        lines[0].condition = "cnt <= 5"
        code = gen_sv(make_settings(), nodes, lines)
        assert "if (cnt <= 5)" in code


# ---------- 2.3 / 2.4: identifier validation ----------

class TestValidation:
    def test_reserved_word_state_name_rejected(self):
        nodes = {0: node(0, "begin", reset=True)}
        with pytest.raises(ValueError, match="reserved word"):
            gen_sv(make_settings(), nodes, [])

    def test_duplicate_state_names_rejected(self):
        nodes = {0: node(0, "IDLE", reset=True), 1: node(1, "idle")}
        with pytest.raises(ValueError, match="Duplicate state name"):
            gen_vhdl(make_settings(), nodes, [])

    def test_invalid_module_name_rejected(self):
        nodes, lines = toggle_fsm()
        s = make_settings()
        s.project_name = "my fsm"
        with pytest.raises(ValueError, match="not a valid HDL identifier"):
            gen_sv(s, nodes, lines)

    def test_port_state_collision_rejected(self):
        nodes = {0: node(0, "led", reset=True)}
        s = make_settings(ports=[Port("led", PortDirection.OUT, 1)])
        with pytest.raises(ValueError, match="collides"):
            gen_vhdl(s, nodes, [])


# ---------- 2.5: state vector width ----------

class TestBitWidth:
    @pytest.mark.parametrize("n,expected", [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (8, 3), (9, 4)])
    def test_enum_width(self, n, expected):
        nodes = {i: node(i, f"S{i}", reset=(i == 0)) for i in range(n)}
        code = gen_sv(make_settings(), nodes, [])
        assert f"typedef enum logic [{expected - 1}:0]" in code


# ---------- 2.6: priority ties ----------

class TestPriorityTies:
    def test_duplicate_priority_rejected(self):
        nodes = {0: node(0, "A", reset=True), 1: node(1, "B"), 2: node(2, "C")}
        lines = [trans(0, 0, 1, cond="x", prio=1),
                 trans(1, 0, 2, cond="y", prio=1)]
        with pytest.raises(ValueError, match="share priority"):
            gen_sv(make_settings(), nodes, lines)

    def test_priority_order_respected(self):
        nodes = {0: node(0, "A", reset=True), 1: node(1, "B"), 2: node(2, "C")}
        # Inserted low-priority first; generator must sort
        lines = [trans(0, 0, 2, cond="y", prio=2),
                 trans(1, 0, 1, cond="x", prio=1)]
        code = gen_sv(make_settings(), nodes, lines)
        assert code.index("if (x)") < code.index("else if (y)")


# ---------- General sanity ----------

class TestGeneralOutput:
    def test_reset_state_used(self):
        nodes = {0: node(0, "A"), 1: node(1, "B", reset=True)}
        lines = [trans(0, 0, 1)]
        sv = gen_sv(make_settings(), nodes, lines)
        vhdl = gen_vhdl(make_settings(), nodes, lines)
        assert "state_reg <= B;" in sv
        assert "state_reg <= B;" in vhdl

    def test_sync_vs_async_reset_sv(self):
        nodes, lines = toggle_fsm()
        async_code = gen_sv(make_settings(is_synchronous_reset=False), nodes, lines)
        sync_code = gen_sv(make_settings(is_synchronous_reset=True), nodes, lines)
        assert "or negedge rst_n" in async_code
        assert "or negedge" not in sync_code

    def test_action_semicolon_appended(self):
        nodes = {0: node(0, "A", reset=True, actions=["led = 1"]), 1: node(1, "B")}
        lines = [trans(0, 0, 1)]
        assert "led = 1;" in gen_sv(make_settings(), nodes, lines)
