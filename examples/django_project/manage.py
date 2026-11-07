#!/usr/bin/env python
"""Demo Django project for ramplint.

ramplint reads it without Django. To run it (and scan it in a browser):
pip install django jinja2 && python manage.py runserver
"""

import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
