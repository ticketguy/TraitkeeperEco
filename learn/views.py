from django.shortcuts import render
from django.views.generic import DetailView
from .models import Course

# Create your views here.
def academy(request):
    #get featured courses
    featured_courses = Course.objects.filter(featured=True).order_by('-created_at')[:3]
    #get other courses
    other_courses = Course.objects.filter(featured=False).order_by('-created_at')

    context = {
        'featured_courses': featured_courses,
        'other_courses': other_courses,
    }
    return render (request, 'learn/academy.html', context)


class CourseDetailView(DetailView):
    model = Course
    template_name = 'learn/course_detail.html'
    context_object_name = 'course'
