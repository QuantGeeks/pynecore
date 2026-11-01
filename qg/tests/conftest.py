"""No fork test leaves a runner state current: with a state installed the swap has REBOUND every tracked module
global, and upstream code that captured one by `from module import name` at import (test_013_config's `_ensured`)
reads a stale object. 2026-11-01: Task 7's first form of the test above left its fresh state current and qg-ci's
one-session `pytest tests qg/tests` failed upstream's `__test_user_values_preserved__` (`'' == 'my_key'`)."""
import pytest
from pynecore.core import runner_state as rs


@pytest.fixture(autouse=True)
def __no_state_left_current__():
    yield
    left = rs.active_state()
    if left is not None:
        rs.discard(left)
        pytest.fail("the test left a runner state current; discard() it before returning")
