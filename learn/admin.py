
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.urls import reverse, path
from django.contrib import messages
from .models import Course, Lesson
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from django_admin_listfilter_dropdown.filters import DropdownFilter

# Make sure this import is correct - adjust the path if needed
from traitkeeper.admin_site import admin_site  # Import the custom admin site

# Custom admin actions
def make_featured(modeladmin, request, queryset):
    queryset.update(featured=True)
    messages.success(request, f"{queryset.count()} course(s) marked as featured.")
make_featured.short_description = "Mark selected courses as featured"

class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ['title', 'order', 'content']
    ordering = ['order']
    show_change_link = True
    classes = ['collapse']
    autocomplete_fields = ['course']

class CourseResource(resources.ModelResource):
    class Meta:
        model = Course
        exclude = ('id',)
        import_id_fields = ('slug',)

class CourseAdmin(ImportExportModelAdmin):
    resource_class = CourseResource
    inlines = [LessonInline]
    list_display = ['title', 'difficulty', 'get_lesson_count', 'featured', 'created_at', 'updated_at', 'view_on_site']
    list_filter = (
        ('difficulty', DropdownFilter),
        'featured',
        ('created_at', admin.DateFieldListFilter),
    )
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    actions = [make_featured]
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Info', {'fields': ('title', 'slug', 'description')}),
        ('Course Details', {'fields': ('difficulty', 'featured')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    readonly_fields = ('created_at', 'updated_at')

    class Media:
        js = ('admin/js/inline_lesson_formset.js', 'admin/js/lesson_reorder.js',)
        css = {
            'all': ('admin/css/custom_admin.css',)
        }

    def get_lesson_count(self, obj):
        count = obj.get_lesson_count()
        url = reverse('admin:lesson_lesson_changelist') + f'?course__id__exact={obj.id}'
        return format_html('<a href="{}">{} lessons</a>', url, count)
    get_lesson_count.short_description = 'Number of Lessons'

    def view_on_site(self, obj):
        url = reverse('course_detail', kwargs={'slug': obj.slug})
        return format_html('<a href="{}" target="_blank">View on site</a>', url)
    view_on_site.short_description = 'View'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('reorder_lessons/<int:course_id>/', self.admin_site.admin_view(self.reorder_lessons_view),
                 name='reorder-lessons'),
        ]
        return custom_urls + urls

    def reorder_lessons_view(self, request, course_id):
        course = Course.objects.get(id=course_id)
        lessons = course.lessons.all().order_by('order')

        if request.method == 'POST':
            order_dict = {int(key.split('-')[1]): int(value) for key, value in request.POST.items() if key.startswith('lesson-')}
            for lesson in lessons:
                if lesson.id in order_dict:
                    lesson.order = order_dict[lesson.id]
                    lesson.save()
            course.reorder_lessons()
            self.message_user(request, "Lessons have been reordered.")
            return HttpResponseRedirect(reverse('admin:lesson_course_change', args=[course_id]))

        context = {
            'title': _('Reorder lessons'),
            'course': course,
            'lessons': lessons,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/reorder_lessons.html', context)

    def save_model(self, request, obj, form, change):
        try:
            super().save_model(request, obj, form, change)
            obj.reorder_lessons()
        except ValidationError as e:
            messages.error(request, str(e))

    def save_formset(self, request, form, formset, change):
        if formset.model == Lesson:
            instances = formset.save(commit=False)
            for obj in formset.deleted_objects:
                obj.delete()
            for instance in instances:
                if not instance.order:
                    max_order = Lesson.objects.filter(course=form.instance).aggregate(models.Max('order'))['order__max'] or 0
                    instance.order = max_order + 1
                instance.save()
            formset.save_m2m()
            form.instance.reorder_lessons()
        else:
            formset.save()

    def response_change(self, request, obj):
        if "_reorder-lessons" in request.POST:
            return HttpResponseRedirect(reverse('admin:reorder-lessons', args=[obj.id]))
        return super().response_change(request, obj)

class LessonResource(resources.ModelResource):
    class Meta:
        model = Lesson
        fields = ('id', 'title', 'course', 'order', 'content')
        export_order = ('id', 'course', 'order', 'title', 'content')

class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'created_at', 'updated_at']
    list_filter = ['course', 'created_at', 'updated_at']
    search_fields = ['title', 'content']
    ordering = ['course', 'order']
    date_hierarchy = 'created_at'
    
    fieldsets = [
        ('Basic Information', {
            'fields': ['course', 'title', 'order'],
            'classes': ['wide'],
        }),
        ('Content', {
            'fields': ['content'],
            'classes': ['wide'],
        }),
        ('Metadata', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]
    
    readonly_fields = ['created_at', 'updated_at']

    def course_link(self, obj):
        url = reverse("admin:lesson_course_change", args=[obj.course.id])
        return format_html('<a href="{}">{}</a>', url, obj.course.title)
    course_link.short_description = 'Course'

# Register models with the custom admin site
admin_site.register(Course, CourseAdmin)
admin_site.register(Lesson, LessonAdmin)