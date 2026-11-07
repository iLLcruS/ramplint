"""Pages of the demo shop. The products are made up; there is no database."""

from dataclasses import dataclass

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse


@dataclass(frozen=True)
class Product:
    pk: int
    name: str
    price: str

    def get_absolute_url(self) -> str:
        return reverse("catalog:detail", args=[self.pk])


PRODUCTS = [
    Product(1, "Linen shirt", "39.00"),
    Product(2, "Wool scarf", "24.00"),
    Product(3, "Canvas bag", "18.50"),
]


def product_list(request):
    query = request.GET.get("q", "").lower()
    products = [p for p in PRODUCTS if query in p.name.lower()]
    return render(request, "catalog/product_list.html", {"products": products})


def product_detail(request, pk):
    product = next((p for p in PRODUCTS if p.pk == pk), None)
    if product is None:
        raise Http404("No such product")
    return render(request, "catalog/product_detail.html", {"product": product})


def product_api(request):
    return JsonResponse({"products": [{"id": p.pk, "name": p.name} for p in PRODUCTS]})
