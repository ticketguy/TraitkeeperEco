(function ($) {
    $(document).ready(function () {
        $('.inline-group').on('click', '.inline-deletelink', function () {
            setTimeout(function () {
                $('.dynamic-lessons').each(function (index) {
                    $(this).find('input[id$="-order"]').val(index + 1);
                });
            }, 100);
        });
    });
})(django.jQuery);