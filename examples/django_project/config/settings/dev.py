from .base import *  # noqa: F403

DEBUG = True

try:
    import debug_toolbar  # noqa: F401
except ImportError:
    pass
else:
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
