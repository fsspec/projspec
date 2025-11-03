from projspec.proj import ProjectSpec


class Django(ProjectSpec):
    """A python web app using the django framework"""

    def match(self):
        return "manage.py" in self.proj.basenames


# artifacts: running (dev) webserver with `python manage.py runserver`
# global site config is in a subdirectory with a settings.py file (and wsgi, etc)
# specific "apps" are in subdirectories with admin.py, views.py etc
