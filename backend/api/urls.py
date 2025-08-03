from django.urls import path
from . import views

urlpatterns = [
    path('parsing-tasks/', views.parsing_tasks, name='parsing_tasks'),
    path('parsing-tasks/create/', views.create_parsing_task, name='create_parsing_task'),
    path('parsing-tasks/<int:task_id>/', views.task_status, name='task_status'),
    path('parsing-tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('proxies/upload/', views.upload_proxies, name='upload_proxies'),
    path('proxies/status/', views.proxy_status, name='proxy_status'),
    path('proxies/reset/', views.reset_proxy_index, name='reset_proxy_index'),
    path('auth/token/', views.auth_token, name='auth_token'),
] 