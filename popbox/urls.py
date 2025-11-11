from django.urls import path
from . import views

app_name = 'popbox'

urlpatterns = [
    path('', views.popbox_home, name='home'),
]
