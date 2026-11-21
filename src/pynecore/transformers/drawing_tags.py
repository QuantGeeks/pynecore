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
  exist only on drawing namespaces. ``copy`` is deliberately excluded there:
  ``array.copy`` / ``matrix.copy`` / ``map.copy`` share the name, and a tag
  they cannot accept would turn those calls into TypeErrors.
"""
import ast

from . import ast_walk

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

#: Method names that only drawing namespaces define, for the ``method_call``
#: dispatch form (see the module docstring for why ``copy`` is absent)
_DRAWING_METHODS = frozenset(
    name.rpartition('.')[2]
    for name in _DRAWING_CALLS
    if name not in ('lib.label.copy', 'lib.line.copy', 'lib.box.copy')
)


class DrawingTagsTransformer(ast.NodeTransformer):
    """Inject the call-site ``tag`` keyword into drawing-creation calls."""

    def __init__(self) -> None:
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
                node.keywords.append(
                    ast.keyword(arg='tag', value=ast.Constant(value=self._next_tag)))
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
