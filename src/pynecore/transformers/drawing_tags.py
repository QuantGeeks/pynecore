"""Stamp every drawing-creation call site with a stable numeric tag.

The engine tags each drawing (line, label, box, polyline, linefill, table,
table cell) with the call site that created it, so a host can restyle drawings
per viewer (a member's chosen color replaces the script's default for a given
call site) without putting color/style inputs in the computation key. The tag
is metadata only: the creation functions store it and no computed value reads
it.

This lowering step injects ``tag=<n>`` into the calls that create drawings,
numbered per module in traversal order. The numbers are pure functions of the
transformed tree, so they are stable across runs of the same script version
and change only when the script's source does.

Two call shapes create drawings:

- the normalized namespace calls ``lib.<family>.<method>(...)`` — every
  creation method of every family;
- the builtin-method dispatch ``method_call('<method>', obj, ...)``, which
  forwards its keywords to the lib function — for the methods whose names
  exist only on drawing namespaces. ``copy`` is stamped there too (both
  syntaxes of a copy are the copy site, so both carry its tag); the dispatch
  drops the keyword for receivers that are not drawings, because
  ``array.copy`` / ``matrix.copy`` / ``map.copy`` share the name and a tag
  they cannot accept would turn those calls into TypeErrors.

Each module numbers its sites from :func:`tag_base` of its module name, so
the tags of a script and of the libraries it import never collide however
each counts its own call sites; a rename is a script-version change.

Stability caveat: the numbers are assigned in pre-order over the tree AFTER
CallInline, so moving a creation call into or out of a wrapper that gets
inlined — or adding a creation call above another site — renumbers every
later site of that module. Tags are comparable only within one script
version.
"""
import ast
import hashlib

from . import ast_walk

#: Sites each module's tag range holds before it spills into a neighbor's
_TAG_SPACING = 1 << 20


def tag_base(module_name: str) -> int:
    """The base of a module's tag range: a stable function of the module's
    name, so a script and the libraries it imports never share tag numbers
    however each counts its own call sites. A name change is a script-version
    change: the tags of that module move with it."""
    if not module_name:
        return 0
    digest = hashlib.blake2b(module_name.encode(), digest_size=8).digest()
    return int.from_bytes(digest) % (1 << 42) * _TAG_SPACING

#: The ``lib.<namespace>.<method>`` creation calls that stamp a tag
_DRAWING_CALLS = frozenset(
    f'lib.{namespace}.{method}'
    for namespace, methods in (
        ('label', ('new', 'copy')), ('line', ('new', 'copy')), ('box', ('new', 'copy')),
        ('table', ('new', 'cell', 'cell_set_bgcolor', 'cell_set_height', 'cell_set_text',
                   'cell_set_text_color', 'cell_set_text_font_family', 'cell_set_text_formatting',
                   'cell_set_text_halign', 'cell_set_text_size', 'cell_set_text_valign',
                   'cell_set_tooltip', 'cell_set_width')),
        ('polyline', ('new',)), ('linefill', ('new',)),
    )
    for method in methods
)

#: Method names for the ``method_call`` dispatch form: the drawing methods
#: whose names only drawing namespaces define, plus ``copy`` (both syntaxes of
#: a copy are the copy site; the dispatch drops the tag for non-drawings)
_DRAWING_METHODS = frozenset(
    name.rpartition('.')[2]
    for name in _DRAWING_CALLS
) | {'copy'}


class DrawingTagsTransformer(ast.NodeTransformer):
    """Inject the call-site ``tag`` keyword into drawing-creation calls."""

    def __init__(self, module_name: str = '') -> None:
        self._base = tag_base(module_name)
        self._next_tag = 0

    def visit_Module(self, node: ast.Module) -> ast.Module:
        # A module without one of the creation names stands no chance of a
        # match; skip the walk entirely (most modules).
        names = {sub.attr for sub in ast_walk.walk(node) if isinstance(sub, ast.Attribute)}
        names.update(sub.id for sub in ast_walk.walk(node) if isinstance(sub, ast.Name))
        if not (names & ({name.rpartition('.')[2] for name in _DRAWING_CALLS} | {'method_call'})):
            return node
        self.generic_visit(node)
        return node

    def visit_Call(self, node: ast.Call) -> ast.Call:
        if self._tagged_call_site(node):
            if not any(keyword.arg == 'tag' for keyword in node.keywords):
                assert self._next_tag < _TAG_SPACING, \
                    "a module's drawing call sites must stay under tag spacing"
                node.keywords.append(
                    ast.keyword(arg='tag', value=ast.Constant(value=self._base + self._next_tag)))
                self._next_tag += 1
        self.generic_visit(node)
        return node

    def _tagged_call_site(self, node: ast.Call) -> bool:
        """Whether this call is a drawing-creation site that takes a tag."""
        func = node.func
        # lib.<namespace>.<method>(...): the shape import normalization leaves
        if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name) and func.value.value.id == 'lib'
                and f'lib.{func.value.attr}.{func.attr}' in _DRAWING_CALLS):
            return True
        # method_call('<method>', obj, ...): the builtin-method dispatch, whose
        # keywords reach the lib function it selects
        return (isinstance(func, ast.Name) and func.id == 'method_call'
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value in _DRAWING_METHODS)
