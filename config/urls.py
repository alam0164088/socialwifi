from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf.urls.static import static
from django.conf import settings   # ✅ add this import


urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.users.urls')),  # keep users auth endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('subscriptions/', include('apps.subscriptions.urls')),
    path('navigation/', include('apps.navigation.urls')),
]


# ✅ Development এ Static এবং Media Files Serve করুন
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
