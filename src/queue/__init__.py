"""Background job queue.

This package intentionally keeps the user-requested `queue/` folder name. Because
that shadows Python's standard-library `queue` module when `src` is on
`PYTHONPATH`, expose the stdlib queue classes here so framework imports like
`from queue import Queue` continue to work.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from sysconfig import get_paths

_stdlib_queue_path = Path(get_paths()["stdlib"]) / "queue.py"
_stdlib_queue_spec = spec_from_file_location("_stdlib_queue", _stdlib_queue_path)

if _stdlib_queue_spec is None or _stdlib_queue_spec.loader is None:
    raise ImportError("could not load Python standard-library queue module")

_stdlib_queue = module_from_spec(_stdlib_queue_spec)
_stdlib_queue_spec.loader.exec_module(_stdlib_queue)

Queue = _stdlib_queue.Queue
PriorityQueue = _stdlib_queue.PriorityQueue
LifoQueue = _stdlib_queue.LifoQueue
SimpleQueue = _stdlib_queue.SimpleQueue
Empty = _stdlib_queue.Empty
Full = _stdlib_queue.Full
