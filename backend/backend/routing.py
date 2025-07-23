from django.urls import re_path
from api.consumers import TaskProgressConsumer
 
websocket_urlpatterns = [
    re_path(r'ws/tasks/(?P<task_id>\d+)/$', TaskProgressConsumer.as_asgi()),
] 