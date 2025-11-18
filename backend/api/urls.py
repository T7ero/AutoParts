from django.urls import path
from . import views
from . import price_list_views

urlpatterns = [
    path('parsing-tasks/', views.parsing_tasks, name='parsing_tasks'),
    path('parsing-tasks/create/', views.create_parsing_task, name='create_parsing_task'),
    path('parsing-tasks/<int:task_id>/', views.task_status, name='task_status'),
    path('parsing-tasks/<int:task_id>/logs/', views.task_logs, name='task_logs'),
    path('parsing-tasks/<int:task_id>/download/', views.download_result, name='download_result'),
    path('parsing-tasks/<int:task_id>/download-site/<str:site>/', views.download_site_result, name='download_site_result'),
    path('parsing-tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('parsing-tasks/clear/', views.clear_all_tasks, name='clear_all_tasks'),
    path('proxies/upload/', views.upload_proxies, name='upload_proxies'),
    path('proxies/status/', views.proxy_status, name='proxy_status'),
    path('proxies/reset/', views.reset_proxy_index, name='reset_proxy_index'),
    path('auth/token/', views.auth_token, name='auth_token'),
    
    # Price List Analysis URLs
    path('price-list-tasks/', price_list_views.get_price_list_tasks, name='get_price_list_tasks'),
    path('price-list-tasks/create/', price_list_views.create_price_list_task, name='create_price_list_task'),
    path('price-list-tasks/<int:task_id>/', price_list_views.get_price_list_task_details, name='get_price_list_task_details'),
    path('price-list-tasks/<int:task_id>/items/', price_list_views.get_price_list_items, name='get_price_list_items'),
    path('price-list-tasks/<int:task_id>/logs/', price_list_views.get_price_list_task_logs, name='get_price_list_task_logs'),
    path('price-list-tasks/<int:task_id>/download/', price_list_views.download_price_list_result, name='download_price_list_result'),
    path('price-list-tasks/<int:task_id>/delete/', price_list_views.delete_price_list_task, name='delete_price_list_task'),
] 