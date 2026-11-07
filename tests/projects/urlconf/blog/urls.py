from django.urls import path, re_path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:id>/", views.post, name="post"),
    re_path(r"^archive/$", views.archive, name="archive"),
]
