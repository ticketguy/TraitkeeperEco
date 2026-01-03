"""
Core middleware for TraitKeeper.

This module contains custom middleware classes for security and functionality.
"""

import logging

logger = logging.getLogger(__name__)


class AdminNoIndexMiddleware:
    """
    Middleware to prevent search engine indexing of admin and sensitive pages.

    This middleware adds X-Robots-Tag headers to HTTP responses for admin pages,
    instructing search engines not to index or follow links on these pages.

    This is a CRITICAL SECURITY measure to prevent:
    - Exposure of admin URLs in search results
    - Information leakage about backend structure
    - Targeted attacks on known admin endpoints

    Usage:
        Add 'core.middleware.AdminNoIndexMiddleware' to MIDDLEWARE in settings.py
    """

    # List of URL patterns that should not be indexed
    PROTECTED_PATHS = [
        '/admin/',
        '/admin',
        '/admin_panel/',
        '/admin_panel',
        '/accounts/',
        '/api/internal/',
        '/settings/',
        '/dashboard/',
        '/_',
    ]

    def __init__(self, get_response):
        """
        Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response
        logger.info("✅ AdminNoIndexMiddleware initialized - protecting admin pages from indexing")

    def __call__(self, request):
        """
        Process the request and add X-Robots-Tag headers if needed.

        Args:
            request: The HTTP request object

        Returns:
            HTTP response with X-Robots-Tag header if path is protected
        """
        response = self.get_response(request)

        # Check if the current path should be protected
        path = request.path
        should_protect = any(path.startswith(protected) for protected in self.PROTECTED_PATHS)

        if should_protect:
            # Add X-Robots-Tag header to prevent indexing
            response['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'

            # Log for monitoring (only in debug mode to avoid log spam)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🔒 Added X-Robots-Tag to protected path: {path}")

        return response


class SecurityHeadersMiddleware:
    """
    Middleware to add additional security headers to all responses.

    This middleware adds various security headers to protect against common attacks
    and improve the overall security posture of the application.
    """

    def __init__(self, get_response):
        """
        Initialize the middleware.

        Args:
            get_response: The next middleware or view in the chain
        """
        self.get_response = get_response
        logger.info("✅ SecurityHeadersMiddleware initialized")

    def __call__(self, request):
        """
        Process the request and add security headers.

        Args:
            request: The HTTP request object

        Returns:
            HTTP response with additional security headers
        """
        response = self.get_response(request)

        # Add Content Security Policy header (adjust as needed for your app)
        # This helps prevent XSS attacks
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdn.tailwindcss.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https: blob:; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none';"
            )

        # Add Referrer-Policy header
        if 'Referrer-Policy' not in response:
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Add Permissions-Policy header (formerly Feature-Policy)
        if 'Permissions-Policy' not in response:
            response['Permissions-Policy'] = (
                'geolocation=(), '
                'microphone=(), '
                'camera=(), '
                'payment=()'
            )

        return response
