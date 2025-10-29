from django.db import models
from django.urls import reverse
from django.db.models.signals import post_delete
from django.dispatch import receiver


class Course(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    intro = models.TextField(blank=True, null=True)
    featured = models.BooleanField(default=False)
    difficulty = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    def get_lesson_count(self):
        return self.lessons.count()

    def get_absolute_url(self):
        return reverse('course_detail', args=[str(self.slug)])
    
    def reorder_lessons(self):
        lessons = self.lessons.all().order_by('order')
        for index, lesson in enumerate(lessons, start=1):
            if lesson.order != index:
                lesson.order = index
                lesson.save()
    


class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    content = models.TextField()
    order = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    class Meta:
        ordering = ['order']


@receiver(post_delete, sender=Lesson)
def reorder_lessons(sender, instance, **kwargs):
    lessons = Lesson.objects.filter(course=instance.course).order_by('order')
    for index, lesson in enumerate(lessons, start=1):
        if lesson.order != index:
            lesson.order = index
            lesson.save()