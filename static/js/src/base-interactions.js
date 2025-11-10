// Base template interactive functionality
// Extracted from inline script for better performance

document.addEventListener('DOMContentLoaded', function() {

// ==================================================
// RESPONSIVE OPTIMIZATION: Resize Handler
// ==================================================
let resizeTimer;
window.addEventListener('resize', function() {
    // Add resizing class to disable transitions during resize
    document.body.classList.add('resizing');

    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
        document.body.classList.remove('resizing');
    }, 250);
});

// Prevent horizontal scroll on specific elements
function preventHorizontalScroll() {
    const elements = document.querySelectorAll('body, html, .site-container, main');
    elements.forEach(el => {
        if (el.scrollWidth > el.clientWidth) {
            console.warn('Horizontal scroll detected on:', el);
        }
    });
}

// Check on load and resize
preventHorizontalScroll();
window.addEventListener('resize', preventHorizontalScroll);

// Header Scroll Effects
    const header = document.getElementById('main-header');
if (header) {
    const scrollThreshold = 10; // Pixels to scroll before changing header style
    let ticking = false;

    function updateHeaderStyle() {
        const currentScrollY = window.scrollY;
        // Add 'scrolled' class only to the desktop header container
        if (currentScrollY > scrollThreshold) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
        ticking = false;
    }

    window.addEventListener('scroll', function() {
        if (!ticking) {
            window.requestAnimationFrame(updateHeaderStyle);
            ticking = true;
        }
    });

    // Initial check in case page loads already scrolled
    updateHeaderStyle();
} else {
    console.warn("Main header element (#main-header) not found for scroll effects.");
}

        console.log('Base.html script started loading'); // Debug log to confirm script execution

        // Service Worker for PWA
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/static/service-worker.js')
                    .then(registration => console.log('Service Worker registered:', registration))
                    .catch(error => console.error('Service Worker registration failed:', error));
            });
        }

        // PWA Install Prompt
        let deferredPrompt;
        const installPrompt = document.getElementById('pwa-install-prompt');
        const installBtn = document.getElementById('pwa-install-btn');
        const dismissBtn = document.getElementById('pwa-dismiss-btn');
        const closeBtn = document.getElementById('pwa-close-btn');

        window.addEventListener('beforeinstallprompt', (e) => {
            // Prevent the mini-infobar from appearing on mobile
            e.preventDefault();
            // Stash the event so it can be triggered later
            deferredPrompt = e;

            // Check if user has dismissed before
            const dismissed = localStorage.getItem('pwa-install-dismissed');
            const installedBefore = localStorage.getItem('pwa-installed');

            // Show install prompt if not dismissed and not installed before
            if (!dismissed && !installedBefore && installPrompt) {
                setTimeout(() => {
                    installPrompt.classList.remove('hidden');
                }, 3000); // Show after 3 seconds
            }
        });

        if (installBtn) {
            installBtn.addEventListener('click', async () => {
                if (!deferredPrompt) {
                    return;
                }

                // Show the install prompt
                deferredPrompt.prompt();

                // Wait for the user to respond to the prompt
                const { outcome } = await deferredPrompt.userChoice;

                if (outcome === 'accepted') {
                    console.log('User accepted the install prompt');
                    localStorage.setItem('pwa-installed', 'true');
                    if (window.showToast) {
                        window.showToast('App installed successfully! Check your home screen.', 'success');
                    }
                } else {
                    console.log('User dismissed the install prompt');
                }

                // Hide the prompt
                if (installPrompt) {
                    installPrompt.classList.add('hidden');
                }

                // Clear the deferredPrompt
                deferredPrompt = null;
            });
        }

        if (dismissBtn) {
            dismissBtn.addEventListener('click', () => {
                if (installPrompt) {
                    installPrompt.classList.add('hidden');
                }
                // Remember dismissal for 7 days
                const dismissedUntil = Date.now() + (7 * 24 * 60 * 60 * 1000);
                localStorage.setItem('pwa-install-dismissed', dismissedUntil.toString());
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                if (installPrompt) {
                    installPrompt.classList.add('hidden');
                }
            });
        }

        // Check if app is already installed
        window.addEventListener('appinstalled', () => {
            console.log('PWA was installed');
            localStorage.setItem('pwa-installed', 'true');
            if (installPrompt) {
                installPrompt.classList.add('hidden');
            }
            if (window.showToast) {
                window.showToast('TraitKeeper installed successfully!', 'success');
            }
        });

        // Clear dismissal if time has passed
        const dismissedUntil = localStorage.getItem('pwa-install-dismissed');
        if (dismissedUntil && Date.now() > parseInt(dismissedUntil)) {
            localStorage.removeItem('pwa-install-dismissed');
        }


        // Main script execution
            console.log('DOMContentLoaded fired for base.html script'); // Debug log

                // Mobile Menu Toggle (New Spherical Buttons)
                const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
                const mobileMenuButtons = document.getElementById('mobile-menu-buttons');
                const mobileMenuBackdrop = document.getElementById('mobile-menu-backdrop');

                console.log('Mobile menu elements:', {
                    mobileMenuToggle: !!mobileMenuToggle,
                    mobileMenuButtons: !!mobileMenuButtons,
                    mobileMenuBackdrop: !!mobileMenuBackdrop
                });

                function openMobileMenu() {
                    console.log('Opening mobile menu buttons');
                    if (mobileMenuButtons) {
                        mobileMenuButtons.classList.remove('hidden');
                        mobileMenuButtons.classList.add('flex');
                        console.log('Mobile menu visibility:', !mobileMenuButtons.classList.contains('hidden')); // Debug log
                    } else {
                        console.error('mobileMenuButtons element not found during openMobileMenu');
                    }
                    if (mobileMenuBackdrop) {
                        mobileMenuBackdrop.classList.remove('hidden');
                        mobileMenuBackdrop.classList.remove('opacity-0');
                        mobileMenuBackdrop.classList.add('opacity-100');
                        console.log('Backdrop visibility:', !mobileMenuBackdrop.classList.contains('hidden')); // Debug log
                    } else {
                        console.error('mobileMenuBackdrop element not found during openMobileMenu');
                    }

                    // Close notification dropdowns when mobile nav menu opens
                    const notificationDropdown = document.getElementById('notification-dropdown');
                    const notificationDropdownMobile = document.getElementById('notification-dropdown-mobile');
                    if (notificationDropdown) notificationDropdown.classList.add('hidden');
                    if (notificationDropdownMobile) notificationDropdownMobile.classList.add('hidden');
                }

                function closeMobileMenu() {
                    console.log('Closing mobile menu buttons');
                    if (mobileMenuButtons) {
                        mobileMenuButtons.classList.remove('flex');
                        mobileMenuButtons.classList.add('hidden');
                    } else {
                        console.error('mobileMenuButtons element not found during closeMobileMenu');
                    }
                    if (mobileMenuBackdrop) {
                        mobileMenuBackdrop.classList.remove('opacity-100');
                        mobileMenuBackdrop.classList.add('opacity-0');
                        setTimeout(() => mobileMenuBackdrop.classList.add('hidden'), 500); // Match duration-500
                    } else {
                        console.error('mobileMenuBackdrop element not found during closeMobileMenu');
                    }
                }

                if (mobileMenuToggle) {
                    console.log('Attaching click event listener to mobile menu toggle');
                    mobileMenuToggle.addEventListener('click', function (e) {
                        e.stopPropagation();
                        e.stopImmediatePropagation();
                        e.preventDefault();
                        console.log('Mobile menu toggle clicked');
                        if (mobileMenuButtons.classList.contains('hidden')) {
                            openMobileMenu();
                        } else {
                            closeMobileMenu();
                        }
                    });
                } else {
                    console.error('Mobile menu toggle not found in the DOM');
                }

                if (mobileMenuBackdrop) {
                    mobileMenuBackdrop.addEventListener('click', function (e) {
                        e.stopPropagation();
                        e.stopImmediatePropagation();
                        console.log('Backdrop clicked, closing mobile menu');
                        closeMobileMenu();
                    });
                }

                document.addEventListener('click', function (e) {
                    const walletModal = document.getElementById('wallet-modal');
                    const walletBackdrop = document.getElementById('wallet-backdrop');
                    const walletDropdownToggles = document.querySelectorAll('#wallet-dropdown-toggle, #wallet-dropdown-toggle-mobile');
                    const clickedInsideWalletToggle = Array.from(walletDropdownToggles).some(toggle => toggle.contains(e.target));

                    // Exclude theme toggle buttons from this click handler
                    const themeToggleButtons = document.querySelectorAll('#theme-toggle, #theme-toggle-mobile');
                    const clickedThemeToggle = Array.from(themeToggleButtons).some(btn => btn && btn.contains(e.target));

                    // Exclude footer elements from closing mobile menu
                    const footer = document.querySelector('footer.bottom-bar');
                    const clickedFooter = footer && footer.contains(e.target);

                    if (mobileMenuButtons && mobileMenuToggle && !mobileMenuButtons.contains(e.target) && !mobileMenuToggle.contains(e.target) && !clickedInsideWalletToggle && !clickedThemeToggle && !clickedFooter && (!walletModal || !walletModal.contains(e.target)) && (!walletBackdrop || !walletBackdrop.contains(e.target))) {
                        // Only proceed if the mobile menu is visible (not hidden)
                        if (!mobileMenuButtons.classList.contains('hidden')) {
                            console.log('Clicked outside mobile menu, closing');
                            closeMobileMenu();
                        }
                    }
                });

                if (mobileMenuButtons) {
                    mobileMenuButtons.addEventListener('click', function (e) {
                        // Allow theme toggle clicks to propagate
                        const themeToggleMobile = document.getElementById('theme-toggle-mobile');
                        if (themeToggleMobile && themeToggleMobile.contains(e.target)) {
                            console.log('Theme toggle clicked, allowing propagation');
                            return; // Let the theme toggle handler process this
                        }

                        e.stopPropagation();
                        e.stopImmediatePropagation();
                        console.log('Clicked inside mobile menu buttons, preventing close');
                    });
                }

                // Wallet Modal Tab Switching
                const walletTab = document.getElementById('wallet-tab');
                const loginTab = document.getElementById('login-tab');
                const walletTabContent = document.getElementById('wallet-tab-content');
                const loginTabContent = document.getElementById('login-tab-content');
                const tabIndicator = document.getElementById('tab-indicator');

                console.log('=== WALLET MODAL TAB INITIALIZATION ===');
                console.log('Wallet tab element:', walletTab, '| Found:', !!walletTab);
                console.log('Login tab element:', loginTab, '| Found:', !!loginTab);
                console.log('Wallet tab content:', walletTabContent, '| Found:', !!walletTabContent);
                console.log('Login tab content:', loginTabContent, '| Found:', !!loginTabContent);
                console.log('Tab indicator:', tabIndicator, '| Found:', !!tabIndicator);

                if (walletTabContent) {
                    console.log('Wallet tab content initial classes:', walletTabContent.className);
                }
                if (loginTabContent) {
                    console.log('Login tab content initial classes:', loginTabContent.className);
                }
                console.log('=== END INITIALIZATION ===');

                function activateTab(tabButton, tabContent, isWalletTab) {
                    console.log('\n=== ACTIVATE TAB CALLED ===');
                    console.log('Tab button:', tabButton);
                    console.log('Tab content:', tabContent);
                    console.log('Is wallet tab:', isWalletTab);
                    console.log('Tab content ID:', tabContent?.id);

                    // Remove active state from all tabs
                    const allTabButtons = document.querySelectorAll('.tab-button');
                    console.log('Found', allTabButtons.length, 'tab buttons');
                    allTabButtons.forEach((btn, index) => {
                        console.log(`Deactivating tab button ${index}:`, btn.id);
                        btn.classList.remove('active-tab', 'text-primary');
                        btn.classList.add('text-gray-600', 'dark:text-gray-400');
                    });

                    // Hide all tab content
                    const allTabContent = document.querySelectorAll('.tab-content');
                    console.log('Found', allTabContent.length, 'tab content elements');
                    allTabContent.forEach((content, index) => {
                        console.log(`Hiding tab content ${index}:`, content.id, '| Before classes:', content.className);
                        content.classList.add('hidden', 'opacity-0');
                        content.classList.remove('opacity-100');
                        console.log(`After hiding:`, content.className);
                    });

                    // Activate the clicked tab with enhanced styling
                    console.log('Activating tab button:', tabButton.id, '| Before classes:', tabButton.className);
                    tabButton.classList.add('active-tab', 'text-primary');
                    tabButton.classList.remove('text-gray-600', 'dark:text-gray-400');
                    console.log('After activation:', tabButton.className);

                    // Animate tab indicator
                    if (tabIndicator) {
                        const newLeft = isWalletTab ? '4px' : 'calc(50% + 0px)';
                        console.log('Moving tab indicator to:', newLeft);
                        tabIndicator.style.left = newLeft;
                        console.log('Tab indicator left value now:', tabIndicator.style.left);
                    } else {
                        console.warn('Tab indicator not found!');
                    }

                    // Show the corresponding tab content with animation
                    if (tabContent) {
                        console.log('Showing tab content:', tabContent.id, '| Before classes:', tabContent.className);
                        tabContent.classList.remove('hidden');
                        console.log('Removed hidden class, classes now:', tabContent.className);

                        setTimeout(() => {
                            console.log('Applying opacity animation to:', tabContent.id);
                            tabContent.classList.remove('opacity-0');
                            tabContent.classList.add('opacity-100');
                            console.log('Final classes:', tabContent.className);
                        }, 50); // Smooth transition
                    } else {
                        console.error('Tab content is null!');
                    }
                    console.log('=== END ACTIVATE TAB ===\n');
                }

                if (walletTab && walletTabContent) {
                    console.log('Attaching click event to wallet tab');
                    walletTab.addEventListener('click', (e) => {
                        e.stopPropagation();
                        console.log('\n>>> WALLET TAB CLICKED <<<');
                        console.log('Event:', e);
                        console.log('Current target:', e.currentTarget);
                        console.log('Calling activateTab for WALLET tab...');
                        activateTab(walletTab, walletTabContent, true);
                    });
                    console.log('Wallet tab click listener attached successfully');
                } else {
                    console.error('ERROR: Wallet tab or content not found!', {
                        walletTab: !!walletTab,
                        walletTabContent: !!walletTabContent
                    });
                }

                if (loginTab && loginTabContent) {
                    console.log('Attaching click event to login tab');
                    loginTab.addEventListener('click', (e) => {
                        e.stopPropagation();
                        console.log('\n>>> LOGIN TAB CLICKED <<<');
                        console.log('Event:', e);
                        console.log('Current target:', e.currentTarget);
                        console.log('Calling activateTab for LOGIN tab...');
                        activateTab(loginTab, loginTabContent, false);
                    });
                    console.log('Login tab click listener attached successfully');
                } else {
                    console.error('ERROR: Login tab or content not found!', {
                        loginTab: !!loginTab,
                        loginTabContent: !!loginTabContent
                    });
                }

                // Notification Dropdown Toggle (Desktop and Mobile)
                const notificationToggle = document.getElementById('notification-toggle');
                const notificationDropdown = document.getElementById('notification-dropdown');
                const notificationToggleMobile = document.getElementById('notification-toggle-mobile');
                const notificationDropdownMobile = document.getElementById('notification-dropdown-mobile');
                const notificationSettingsToggle = document.getElementById('notification-settings-toggle');
                const notificationSettingsToggleMobile = document.getElementById('notification-settings-toggle-mobile');
                const notificationSettingsModal = document.getElementById('notification-settings-modal');
                const closeNotificationSettings = document.getElementById('close-notification-settings');
                const markAllRead = document.getElementById('mark-all-read');
                const markAllReadMobile = document.getElementById('mark-all-read-mobile');

                console.log('Notification elements:', {
                    notificationToggle: !!notificationToggle,
                    notificationDropdown: !!notificationDropdown,
                    notificationToggleMobile: !!notificationToggleMobile,
                    notificationDropdownMobile: !!notificationDropdownMobile,
                    notificationSettingsToggle: !!notificationSettingsToggle,
                    notificationSettingsToggleMobile: !!notificationSettingsToggleMobile,
                    notificationSettingsModal: !!notificationSettingsModal,
                    closeNotificationSettings: !!closeNotificationSettings,
                    markAllRead: !!markAllRead,
                    markAllReadMobile: !!markAllReadMobile
                });

                // Setup desktop notification dropdown
                if (notificationToggle && notificationDropdown) {
                    notificationToggle.addEventListener('click', function (e) {
                        e.stopPropagation();
                        e.preventDefault();
                        console.log('Desktop notification toggle clicked');
                        notificationDropdown.classList.toggle('hidden');
                        // Close mobile dropdown if open
                        if (notificationDropdownMobile) {
                            notificationDropdownMobile.classList.add('hidden');
                        }
                    });

                    // Prevent dropdown from closing when clicking inside
                    notificationDropdown.addEventListener('click', function(e) {
                        e.stopPropagation();
                    });
                }

                // Setup mobile notification dropdown
                if (notificationToggleMobile && notificationDropdownMobile) {
                    notificationToggleMobile.addEventListener('click', function (e) {
                        e.stopPropagation();
                        e.preventDefault();
                        console.log('Mobile notification toggle clicked');
                        notificationDropdownMobile.classList.toggle('hidden');
                        // Close desktop dropdown if open
                        if (notificationDropdown) {
                            notificationDropdown.classList.add('hidden');
                        }
                    });

                    // Prevent dropdown from closing when clicking inside
                    notificationDropdownMobile.addEventListener('click', function(e) {
                        e.stopPropagation();
                    });
                }

                // Single global click handler for closing both notification dropdowns
                document.addEventListener('click', (event) => {
                    const walletModal = document.getElementById('wallet-modal');
                    const walletBackdrop = document.getElementById('wallet-backdrop');

                    // Check if click is outside all notification elements
                    const clickedInsideNotification = (
                        (notificationToggle && notificationToggle.contains(event.target)) ||
                        (notificationDropdown && notificationDropdown.contains(event.target)) ||
                        (notificationToggleMobile && notificationToggleMobile.contains(event.target)) ||
                        (notificationDropdownMobile && notificationDropdownMobile.contains(event.target))
                    );

                    const clickedInsideModal = (
                        (walletModal && walletModal.contains(event.target)) ||
                        (walletBackdrop && walletBackdrop.contains(event.target))
                    );

                    if (!clickedInsideNotification && !clickedInsideModal) {
                        if (notificationDropdown) notificationDropdown.classList.add('hidden');
                        if (notificationDropdownMobile) notificationDropdownMobile.classList.add('hidden');
                    }
                });

                if (notificationSettingsToggle) {
                    notificationSettingsToggle.addEventListener('click', function (e) {
                        e.stopPropagation();
                        notificationSettingsModal.classList.remove('hidden');
                        notificationDropdown.classList.add('hidden');
                    });
                }

                if (notificationSettingsToggleMobile) {
                    notificationSettingsToggleMobile.addEventListener('click', function (e) {
                        e.stopPropagation();
                        notificationSettingsModal.classList.remove('hidden');
                        notificationDropdownMobile.classList.add('hidden');
                    });
                }

                if (closeNotificationSettings) {
                    closeNotificationSettings.addEventListener('click', function (e) {
                        e.stopPropagation();
                        notificationSettingsModal.classList.add('hidden');
                    });
                }

                if (notificationSettingsModal) {
                    notificationSettingsModal.addEventListener('click', (event) => {
                        if (event.target === notificationSettingsModal) {
                            notificationSettingsModal.classList.add('hidden');
                        }
                    });
                }

                // Mark All Notifications as Read
                function markAllNotificationsRead() {
                    fetch('/notifications/mark-all-read/', {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                            'Content-Type': 'application/json'
                        }
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // Update UI
                            document.querySelectorAll('.notification-item').forEach(item => {
                                item.classList.remove('bg-accent-light', 'dark:bg-gray-700');
                                item.dataset.isRead = 'true';
                                // Remove mark as read button
                                const markBtn = item.querySelector('.mark-read-btn');
                                if (markBtn) markBtn.remove();
                            });

                            // Update badge
                            const badge = document.getElementById('notification-badge');
                            if (badge) badge.remove();
                        }
                    })
                    .catch(error => console.error('Error marking all as read:', error));
                }

                if (markAllRead) {
                    markAllRead.addEventListener('click', markAllNotificationsRead);
                }
                if (markAllReadMobile) {
                    markAllReadMobile.addEventListener('click', markAllNotificationsRead);
                }

                // Mark Individual Notification as Read
                document.addEventListener('click', function(e) {
                    if (e.target.classList.contains('mark-read-btn')) {
                        const notificationId = e.target.dataset.notificationId;
                        const notificationItem = e.target.closest('.notification-item');

                        fetch('/notifications/mark-read/', {
                            method: 'POST',
                            headers: {
                                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value || '',
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({ notification_id: notificationId })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                // Update UI
                                notificationItem.classList.remove('bg-accent-light', 'dark:bg-gray-700');
                                notificationItem.dataset.isRead = 'true';
                                e.target.remove(); // Remove the button

                                // Update badge count
                                const badge = document.getElementById('notification-badge');
                                if (badge) {
                                    const currentCount = parseInt(badge.textContent);
                                    if (currentCount > 1) {
                                        badge.textContent = currentCount - 1;
                                    } else {
                                        badge.remove();
                                    }
                                }
                            }
                        })
                        .catch(error => console.error('Error marking as read:', error));
                    }
                });

                // User Profile Dropdown Toggle (Desktop and Mobile)
                const profileLinks = document.querySelectorAll('.profile-link');
                const desktopMenu = document.getElementById('user-profile-menu-desktop');
                const mobileMenu = document.getElementById('user-profile-menu-mobile');

                console.log('Profile dropdown setup:', {
                    profileLinksCount: profileLinks.length,
                    hasDesktopMenu: !!desktopMenu,
                    hasMobileMenu: !!mobileMenu
                });

                // Setup dropdown for both desktop and mobile
                if (profileLinks.length > 0) {
                    profileLinks.forEach((profileLink, index) => {
                        const menu = index === 0 ? desktopMenu : mobileMenu;
                        const menuType = index === 0 ? 'desktop' : 'mobile';

                        console.log(`Setting up ${menuType} profile dropdown`, {
                            hasProfileLink: !!profileLink,
                            hasMenu: !!menu
                        });

                        if (profileLink && menu) {
                            // Toggle dropdown on click
                            profileLink.addEventListener('click', function (e) {
                                console.log(`${menuType} profile link clicked`);
                                e.stopPropagation();
                                e.preventDefault();

                                const wasHidden = menu.classList.contains('hidden');
                                menu.classList.toggle('hidden');
                                console.log(`${menuType} menu toggled from ${wasHidden ? 'hidden' : 'visible'} to ${!wasHidden ? 'hidden' : 'visible'}`);

                                // Close the other menu
                                const otherMenu = index === 0 ? mobileMenu : desktopMenu;
                                if (otherMenu) otherMenu.classList.add('hidden');

                                // Close notification dropdowns when profile menu opens
                                if (notificationDropdown) notificationDropdown.classList.add('hidden');
                                if (notificationDropdownMobile) notificationDropdownMobile.classList.add('hidden');
                            });

                            // Prevent dropdown from closing when clicking inside it
                            menu.addEventListener('click', function(e) {
                                e.stopPropagation();
                            });
                        } else {
                            console.error(`Failed to setup ${menuType} profile dropdown:`, {
                                profileLink: !!profileLink,
                                menu: !!menu
                            });
                        }
                    });

                    // Close all dropdowns when clicking outside
                    document.addEventListener('click', (event) => {
                        const walletModal = document.getElementById('wallet-modal');
                        const walletBackdrop = document.getElementById('wallet-backdrop');

                        let clickedOutside = true;
                        profileLinks.forEach(link => {
                            if (link.contains(event.target)) clickedOutside = false;
                        });

                        if (clickedOutside &&
                            (!desktopMenu || !desktopMenu.contains(event.target)) &&
                            (!mobileMenu || !mobileMenu.contains(event.target)) &&
                            (!walletModal || !walletModal.contains(event.target)) &&
                            (!walletBackdrop || !walletBackdrop.contains(event.target))) {
                            if (desktopMenu) desktopMenu.classList.add('hidden');
                            if (mobileMenu) mobileMenu.classList.add('hidden');
                        }
                    });
                }
                // Profile links not found is expected when user is not authenticated

                const transactionCheckbox = document.querySelector('input[name="transaction"]');
                const transactionSettings = document.querySelector('.transaction-settings');
                if (transactionCheckbox && transactionSettings) {
                    transactionCheckbox.addEventListener('change', () => {
                        transactionSettings.classList.toggle('hidden', !transactionCheckbox.checked);
                    });
                }

                if (markAllRead) {
                    markAllRead.addEventListener('click', function (e) {
                        e.stopPropagation();
                        // This uses Django template tags and needs to stay in the template
                        // Will be handled in template
                    });
                }

                if (markAllReadMobile) {
                    markAllReadMobile.addEventListener('click', function (e) {
                        e.stopPropagation();
                        // This uses Django template tags and needs to stay in the template
                        // Will be handled in template
                    });
                }

        console.log('Base.html script finished loading');

        // Handle zoom for all site containers to stretch the entire site
            // Optimized to reduce forced reflows by batching DOM reads and writes
            function handleSiteZoom() {
                const siteContainers = document.querySelectorAll('.site-container');
                if (!siteContainers.length) return;

                // BATCH READS: Read viewport width once (avoid multiple reads)
                const viewportWidth = window.innerWidth;
                const defaultMaxWidth = 1792; // 1792px as per max-w-7xl

                // Calculate styles based on viewport (no DOM writes yet)
                let styles;
                if (viewportWidth >= 768) {
                    // Desktop view (md: breakpoint is 768px)
                    if (viewportWidth < defaultMaxWidth) {
                        styles = { maxWidth: '100%', marginLeft: '0', marginRight: '0' };
                    } else {
                        styles = { maxWidth: `${defaultMaxWidth}px`, marginLeft: 'auto', marginRight: 'auto' };
                    }
                } else {
                    // Mobile view: always stretch to full width
                    styles = { maxWidth: '100%', marginLeft: '0', marginRight: '0' };
                }

                // BATCH WRITES: Apply all style changes together using requestAnimationFrame
                requestAnimationFrame(() => {
                    siteContainers.forEach(container => {
                        container.style.maxWidth = styles.maxWidth;
                        container.style.marginLeft = styles.marginLeft;
                        container.style.marginRight = styles.marginRight;
                    });
                });
            }

            // Run on initial load
            handleSiteZoom();

            // Run on resize or zoom (debounced to avoid excessive calls)
            let resizeTimeout;
            window.addEventListener('resize', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(handleSiteZoom, 100);
            });

            // Detect zoom changes via orientation change or scroll (some browsers trigger this on zoom)
            window.addEventListener('orientationchange', handleSiteZoom);
            window.addEventListener('scroll', () => {
                clearTimeout(resizeTimeout);
                resizeTimeout = setTimeout(handleSiteZoom, 100);
            });

            // Real-time Collection Search
            const desktopInput = document.getElementById('desktop-search-input');
            const mobileInput = document.getElementById('mobile-search-input');
            const desktopResults = document.getElementById('desktop-search-results');
            const mobileResults = document.getElementById('mobile-search-results');

            console.log('Collection Search Initialized:', {
                desktopInput: !!desktopInput,
                mobileInput: !!mobileInput,
                desktopResults: !!desktopResults,
                mobileResults: !!mobileResults
            });

            let searchTimeout;
            const SEARCH_DELAY = 300; // milliseconds

            function performSearch(query, resultsContainer) {
                console.log('performSearch called:', { query, hasContainer: !!resultsContainer });

                if (query.length < 2) {
                    resultsContainer.classList.add('hidden');
                    console.log('Query too short, hiding results');
                    return;
                }

                // Show loading state
                console.log('Showing loading state');
                resultsContainer.innerHTML = '<div class="p-4 text-center"><div class="inline-block w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div><span class="ml-2 text-sm text-gray-500 dark:text-gray-400">Searching...</span></div>';
                resultsContainer.classList.remove('hidden');
                console.log('Results container visible:', !resultsContainer.classList.contains('hidden'));

                // Fetch search results
                const searchUrl = `/api/search-collections/?q=${encodeURIComponent(query)}`;
                console.log('Fetching from:', searchUrl);

                fetch(searchUrl)
                    .then(response => {
                        console.log('Search response status:', response.status);
                        return response.json();
                    })
                    .then(data => {
                        console.log('Search results:', data);
                        if (data.results && data.results.length > 0) {
                            const html = data.results.map(collection => `
                                <a href="${collection.url}"
                                   class="flex items-center gap-3 p-3 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-b-0">
                                    <img src="${collection.image_url || '/static/img/placeholder-nft.png'}"
                                         alt="${collection.name}"
                                         class="w-10 h-10 rounded-lg object-cover flex-shrink-0"
                                         onerror="this.src='/static/img/placeholder-nft.png'">
                                    <div class="flex-1 min-w-0">
                                        <div class="font-semibold text-sm text-gray-900 dark:text-white truncate">${collection.name}</div>
                                        <div class="text-xs text-gray-500 dark:text-gray-400 truncate">
                                            Collection
                                        </div>
                                    </div>
                                    <svg class="w-4 h-4 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
                                    </svg>
                                </a>
                            `).join('');
                            resultsContainer.innerHTML = html;
                            console.log('Results rendered:', data.results.length, 'collections');
                        } else {
                            resultsContainer.innerHTML = '<div class="p-4 text-center text-sm text-gray-500 dark:text-gray-400">No collections found</div>';
                            console.log('No results found');
                        }
                    })
                    .catch(error => {
                        console.error('Search error:', error);
                        resultsContainer.innerHTML = '<div class="p-4 text-center text-sm text-red-500">Search failed. Please try again.</div>';
                    });
            }

            function setupSearchInput(input, results) {
                if (!input || !results) {
                    console.warn('setupSearchInput called with missing elements:', { input: !!input, results: !!results });
                    return;
                }

                console.log('Setting up search input:', { inputId: input.id, resultsId: results.id });

                input.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    const query = e.target.value.trim();
                    console.log('Input event triggered:', query);

                    if (query.length < 2) {
                        results.classList.add('hidden');
                        return;
                    }

                    searchTimeout = setTimeout(() => {
                        performSearch(query, results);
                    }, SEARCH_DELAY);
                });

                input.addEventListener('focus', (e) => {
                    const query = e.target.value.trim();
                    console.log('Focus event triggered:', query);
                    if (query.length >= 2 && !results.classList.contains('hidden')) {
                        performSearch(query, results);
                    }
                });

                // Close results when clicking outside
                document.addEventListener('click', (e) => {
                    if (!input.contains(e.target) && !results.contains(e.target)) {
                        console.log('Click outside search, hiding results');
                        results.classList.add('hidden');
                    }
                });

                // Handle keyboard navigation
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') {
                        console.log('Escape key pressed, hiding results');
                        results.classList.add('hidden');
                        input.blur();
                    }
                });
            }

            console.log('Setting up desktop search...');
            setupSearchInput(desktopInput, desktopResults);
            console.log('Setting up mobile search...');
            setupSearchInput(mobileInput, mobileResults);
    });

    // === Toast Notification System ===
    window.showToast = function(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = 'toast-notification transform translate-x-full transition-all duration-300 ease-out';

        // Toast colors based on type
        const colors = {
            success: 'bg-green-500 dark:bg-green-600',
            error: 'bg-red-500 dark:bg-red-600',
            warning: 'bg-yellow-500 dark:bg-yellow-600',
            info: 'bg-blue-500 dark:bg-blue-600'
        };

        // Toast icons
        const icons = {
            success: '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>',
            error: '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
            warning: '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>',
            info: '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>'
        };

        toast.innerHTML = `
            <div class="${colors[type] || colors.info} text-white px-4 py-3 rounded-lg shadow-2xl flex items-center gap-3 min-w-[280px] max-w-sm">
                <div class="flex-shrink-0">
                    ${icons[type] || icons.info}
                </div>
                <div class="flex-1 text-sm font-medium">
                    ${message}
                </div>
                <button onclick="this.closest('.toast-notification').remove()" class="flex-shrink-0 ml-2 hover:opacity-80">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                    </svg>
                </button>
            </div>
        `;

        container.appendChild(toast);

        // Slide in
        setTimeout(() => {
            toast.classList.remove('translate-x-full');
            toast.classList.add('translate-x-0');
        }, 10);

        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.add('translate-x-full', 'opacity-0');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }

        return toast;
    };
