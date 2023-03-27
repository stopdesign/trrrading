import os
from importlib import import_module
from inspect import isclass
from pkgutil import iter_modules

from .base import BaseStrategy

all_strategies = {}

base_path = os.path.dirname(__file__)

# Из всех дочерних модулей взять все классы,
# которые наследуются от BaseStrategy.
for _, module_name, _ in iter_modules([base_path]):
    module = import_module(f"{__name__}.{module_name}")

    for name, o in vars(module).items():
        if isclass(o) and issubclass(o, BaseStrategy) and o != BaseStrategy:
            all_strategies[name] = o

__all__ = ["BaseStrategy", "all_strategies"]
