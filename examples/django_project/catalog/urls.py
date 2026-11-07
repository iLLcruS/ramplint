from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("products/<int:pk>/", views.product_detail, name="detail"),
    path("api/products/", views.product_api, name="api-products"),
]
