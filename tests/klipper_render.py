"""Offline Klipper gcode_macro render harness (no printer, never executes G-code).

This harness is intentionally small and self-contained. It:

  * parses the relevant .cfg files (a mix of the edited worktree configs and the
    READ-ONLY dereferenced evidence under sexpistols-review/config, so we never
    follow the live symlinks),
  * emulates Klipper's same-section-key MERGE across included files (later file
    wins per option), matching how duplicate [gcode_macro NAME] / [section]
    blocks combine at load time,
  * renders a macro's ``gcode:`` body with Klipper's SINGLE-brace Jinja
    delimiters and a mock ``printer`` status object,
  * returns the emitted command lines for assertions.

Rendered G-code is a plain string here; it is NEVER sent to a printer.
"""

import os
import re
import jinja2

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.dirname(HERE)                                   # worktree root
REVIEW = "/home/clawstache/printer-backups/sexpistols-review/config"  # read-only evidence


# --------------------------------------------------------------------------- #
# Mock status objects
# --------------------------------------------------------------------------- #
class MacroError(Exception):
    """Raised by the template global action_raise_error()."""


class Coord(list):
    """List that also exposes .x/.y/.z/.e, like Klipper coordinate status."""

    @property
    def x(self):
        return self[0]

    @property
    def y(self):
        return self[1]

    @property
    def z(self):
        return self[2]

    @property
    def e(self):
        return self[3]


class Status(dict):
    """Dict that supports attribute access and RAISES on a missing key.

    Klipper's ``printer`` wrapper raises when you access an undefined object
    (e.g. ``printer[None]`` for a null tool). Emulating that lets the tests
    prove the old null-tool render failed while the new one does not.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __getitem__(self, key):
        if key not in self:
            raise KeyError("no status object %r" % (key,))
        return dict.__getitem__(self, key)


def status(**kw):
    return Status(kw)


# --------------------------------------------------------------------------- #
# Minimal Klipper-style config parser + include merge
# --------------------------------------------------------------------------- #
_OPT_RE = re.compile(r"^(\s*)([A-Za-z0-9_.]+)\s*:(.*)$")


def parse_cfg(path):
    """Return {section_name: {option: raw_value_string}} for one file."""
    sections = {}
    cur = None
    cur_opt = None
    opt_indent = 0
    with open(path) as fh:
        for raw in fh:
            # Klipper strips '#' comments (to end of line) at config parse time,
            # BEFORE the gcode template is compiled - which is why the upstream
            # Mainsail macros can put '# ...' inline inside {% set %} statements.
            # ';' is NOT a config comment (it is a gcode comment, passed through).
            line = raw.rstrip("\n").split("#", 1)[0]
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                cur = stripped[1:-1].strip()
                sections.setdefault(cur, {})
                cur_opt = None
                continue
            if cur is None:
                continue
            if not stripped:
                if cur_opt is not None:
                    sections[cur][cur_opt].append("")
                continue
            m = _OPT_RE.match(line)
            indent = len(line) - len(line.lstrip())
            if m and (cur_opt is None or len(m.group(1)) <= opt_indent):
                cur_opt = m.group(2)
                opt_indent = len(m.group(1))
                rest = m.group(3)
                sections[cur][cur_opt] = [rest.strip()] if rest.strip() else []
            elif cur_opt is not None:
                # continuation line of the current option (keep body indentation
                # beyond the option indent so nested {% %} stays aligned enough)
                body = line[opt_indent:] if len(line) >= opt_indent else stripped
                sections[cur][cur_opt].append(body)
    return {
        sec: {o: "\n".join(v).strip("\n") for o, v in opts.items()}
        for sec, opts in sections.items()
    }


def merge_cfgs(paths):
    """Merge parsed configs in include order (later file wins per option)."""
    merged = {}
    for p in paths:
        for sec, opts in parse_cfg(p).items():
            merged.setdefault(sec, {})
            merged[sec].update(opts)
    return merged


# Effective include order for the macros under test. Upstream bodies come from
# the READ-ONLY dereferenced evidence; the fixes come from the worktree files,
# with user-overrides.cfg LAST so it wins the merge (exactly like printer.cfg).
EFFECTIVE_INCLUDES = [
    os.path.join(REVIEW, "mainsail.cfg"),                                  # PAUSE/RESUME base
    os.path.join(FIX, "macros.cfg"),                                       # our root macros
    os.path.join(FIX, "homing.cfg"),                                       # our homing edits
    os.path.join(REVIEW, "toolchanger/readonly-configs/toolchanger.cfg"),  # RESUME/after_change/TOOL_ALIGN base
    os.path.join(REVIEW, "toolchanger/readonly-configs/calibrate-offsets.cfg"),  # calibrate base
    os.path.join(FIX, "front-brush.cfg"),                                  # manual brush; auto helper has no pickup caller
    os.path.join(FIX, "user-overrides.cfg"),                               # our late overrides (LAST)
]


def effective_config():
    return merge_cfgs(EFFECTIVE_INCLUDES)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def make_env():
    env = jinja2.Environment(
        block_start_string="{%",
        block_end_string="%}",
        variable_start_string="{",
        variable_end_string="}",
        comment_start_string="{#",
        comment_end_string="#}",
        undefined=jinja2.Undefined,
        extensions=["jinja2.ext.do"],
    )

    def action_raise_error(msg="error"):
        raise MacroError(str(msg))

    def action_respond_info(msg=""):
        return ""

    env.globals["action_raise_error"] = action_raise_error
    env.globals["action_respond_info"] = action_respond_info
    env.globals["printer"] = None  # replaced per-render via context
    return env


def render_body(gcode_body, printer, params=None, rawparams="", **extra):
    """Render a macro ``gcode:`` body; return list of non-empty emitted lines.

    ``extra`` supplies macro-local variables (Klipper injects a macro's
    ``variable_*`` declarations into the template namespace).
    """
    env = make_env()
    tmpl = env.from_string(gcode_body)
    ctx = dict(printer=printer, params=params or {}, rawparams=rawparams)
    ctx.update(extra)
    out = tmpl.render(**ctx)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def render_macro(cfg, macro_name, printer, params=None, rawparams="", **extra):
    sec = "gcode_macro " + macro_name
    if sec not in cfg or "gcode" not in cfg[sec]:
        raise KeyError("macro %r not found or has no gcode" % (macro_name,))
    return render_body(cfg[sec]["gcode"], printer, params, rawparams, **extra)


def render_option(cfg, section, option, printer, params=None, rawparams="", **extra):
    return render_body(cfg[section][option], printer, params, rawparams, **extra)


def commands(lines):
    """Drop comment-only lines (Klipper treats leading # / ; as comments)."""
    return [ln for ln in lines if not ln.lstrip().startswith(("#", ";"))]
