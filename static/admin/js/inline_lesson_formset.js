(function ($) {
    $(document).ready(function () {
        var lessonsFormset = $('.inline-group');
        lessonsFormset.formset({
            prefix: 'lessons',
            addText: 'Add another lesson',
            deleteText: 'Remove this lesson'
        });
    });
})(django.jQuery);