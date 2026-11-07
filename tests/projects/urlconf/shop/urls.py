from django.urls import include, path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.ProductList.as_view(), name="list"),
    path("<slug:category>/<int:pk>/", views.ProductDetail.as_view(), name="detail"),
    path("api/", include("shop.api.urls")),
]
