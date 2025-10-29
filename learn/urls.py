from django.urls import path
from . import views
from .views import academy, CourseDetailView



urlpatterns = [
    path('', academy, name='learn'),
    path('course/<slug:slug>/', CourseDetailView.as_view(), name='course_detail'),

]