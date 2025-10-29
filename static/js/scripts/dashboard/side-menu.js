document.addEventListener('DOMContentLoaded', function () {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('#dashboard-main-content');
    let timeoutId;

    function collapseSidebar() {
        sidebar.style.width = 'var(--sidebar-collapsed-width)';
        mainContent.style.marginLeft = 'var(--sidebar-collapsed-width)';
        mainContent.style.width = 'calc(100% - var(--sidebar-collapsed-width))';
    }

    function expandSidebar() {
        sidebar.style.width = 'var(--sidebar-width)';
        mainContent.style.marginLeft = 'var(--sidebar-width)';
        mainContent.style.width = 'calc(100% - var(--sidebar-width))';
    }

    sidebar.addEventListener('mouseenter', function () {
        clearTimeout(timeoutId);
        expandSidebar();
    });

    sidebar.addEventListener('mouseleave', function () {
        timeoutId = setTimeout(collapseSidebar, 100);
    });

    // Initially collapse the sidebar
    collapseSidebar();
});