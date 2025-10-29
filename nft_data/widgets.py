from django import forms
from django.utils.safestring import mark_safe

class TailwindSelectWidget(forms.Select):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        # Add default Tailwind classes to the widget
        default_attrs = {
            'class': 'w-full px-4 py-2 rounded-lg border border-accent focus:outline-none focus:ring-2 focus:ring-primary bg-white text-text',
        }
        if attrs:
            default_attrs.update(attrs)
        self.attrs = default_attrs

    def render(self, name, value, attrs=None, renderer=None):
        # Add dark mode classes dynamically
        attrs = self.build_attrs(attrs, {'class': self.attrs['class'] + ' dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200'})
        return super().render(name, value, attrs, renderer)

class TailwindTextInputWidget(forms.TextInput):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        # Add default Tailwind classes to the widget
        default_attrs = {
            'class': 'w-full px-4 py-2 rounded-lg border border-accent focus:outline-none focus:ring-2 focus:ring-primary bg-white text-text',
        }
        if attrs:
            default_attrs.update(attrs)
        self.attrs = default_attrs

    def render(self, name, value, attrs=None, renderer=None):
        # Add dark mode classes dynamically
        attrs = self.build_attrs(attrs, {'class': self.attrs['class'] + ' dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200'})
        return super().render(name, value, attrs, renderer)