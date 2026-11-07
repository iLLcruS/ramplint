"""Django integration of the browser scan: template source maps.

``SourceMapLoader`` wraps the template loaders of a development server so every
element of a rendered page says which template line produced it. Use it through
``ramplint --runserver`` (no change to your settings), or add it to the
development settings of a server you start yourself::

    TEMPLATES[0]["APP_DIRS"] = False
    TEMPLATES[0]["OPTIONS"]["loaders"] = [
        (
            "ramplint.django.SourceMapLoader",
            [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
        )
    ]

Importing this package needs Django; the rest of ramplint never imports it.
"""

from ramplint.django.loader import SourceMapLoader, wrap_template_loaders

__all__ = ["SourceMapLoader", "wrap_template_loaders"]
