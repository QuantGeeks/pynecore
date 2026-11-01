"""Run one script pristine, in its own process (QuantGeeks fork; spec 4.2).

Never imports ``pynecore.core.runner_state``: the reference a co-resident run is
compared against. argv: ``script events_pkl out_pkl live(0|1) sum_mode``.
"""
import os
import pickle
import sys
from pathlib import Path

os.environ["PYNE_SAVE_SCRIPT_TOML"] = "0"

from pynecore.core import rolling_sum
from pynecore.core.script_runner import ScriptRunner, LIVE_TRANSITION
from pynecore.lib import label, line, box


def _row(c, p):
    return (c.timestamp, tuple(sorted((k, repr(v)) for k, v in p.items())),
            (len(label.all()), len(line.all()), len(box.all())))


def main() -> int:
    script, events_pkl, out_pkl, live, sum_mode = sys.argv[1:6]
    rolling_sum.set_sum_mode(sum_mode)
    events, syminfo = pickle.loads(Path(events_pkl).read_bytes())
    # The pickled stream carries a field-equal copy of LIVE_TRANSITION; the runner
    # recognises the sentinel by identity, so put the module's own object back.
    events = [LIVE_TRANSITION if e == LIVE_TRANSITION else e for e in events]
    runner = ScriptRunner(script_path=Path(script), ohlcv_iter=events, syminfo=syminfo,
                          live=live == "1", lossless_prices=True, lossless_volume=True)
    rows = [_row(c, p) for c, p in runner.run_iter()]
    Path(out_pkl).write_bytes(pickle.dumps(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
