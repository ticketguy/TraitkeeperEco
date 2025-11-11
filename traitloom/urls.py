from django.urls import path
from . import views

app_name = 'traitloom'

urlpatterns = [
    path('', views.traitloom_home, name='home'),
]
