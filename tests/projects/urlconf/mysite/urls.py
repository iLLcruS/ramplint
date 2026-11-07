from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from blog import urls as blog_urls
from shop import views as shop_views

from .helpers import make_patterns

legal = [
    path("terms/", shop_views.terms, name="terms"),
]

urlpatterns = [
    path("", shop_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("blog/", include(blog_urls)),
    path("accounts/", include("django.contrib.auth.urls")),
    path("social/", include("allauth.urls")),
    re_path(r"^legacy/(?P<year>[0-9]{4})/$", shop_views.legacy, name="legacy"),
]

urlpatterns += i18n_patterns(
    path("shop/", include(("shop.urls", "shop"), namespace="store")),
    path("legal/", include(legal)),
)
urlpatterns.append(path("health/", shop_views.health))
urlpatterns.extend(make_patterns())
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
