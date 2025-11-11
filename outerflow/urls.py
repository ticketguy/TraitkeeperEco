from django.urls import path
from . import views

app_name = 'outerflow'

urlpatterns = [
    path('', views.outerflow_home, name='home'),
]
