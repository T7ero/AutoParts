from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PartViewSet, CrossReferenceViewSet, ParsingTaskViewSet, AutopiterParseView
from rest_framework.authtoken.views import obtain_auth_token

router = DefaultRouter()
router.register(r'parts', PartViewSet)
router.register(r'cross-references', CrossReferenceViewSet)
router.register(r'parsing-tasks', ParsingTaskViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/token/', obtain_auth_token, name='api_token_auth'),
    path('autopiter/parse/', AutopiterParseView.as_view(), name='autopiter_parse'),
    # path('auth/register/', ...),  # Удалено/закомментировано для безопасности
] 