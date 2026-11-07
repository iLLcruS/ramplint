from rest_framework import routers

from .viewsets import OrderViewSet, ProductViewSet

router = routers.DefaultRouter()
router.register(r"products", ProductViewSet, basename="product")
router.register("orders", OrderViewSet)

urlpatterns = router.urls
