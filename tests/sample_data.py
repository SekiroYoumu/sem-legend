"""Original research fixtures are optional in the public source distribution."""
import pytest
from semlegend.samples import ORIGINAL_EXAMPLES


def sample_path(name):
    path = ORIGINAL_EXAMPLES / name
    if not path.is_file():
        matches = list(ORIGINAL_EXAMPLES.rglob(name))
        if matches:
            return matches[0]
        pytest.skip(f'Optional local research fixture is unavailable: {name}')
    return path
