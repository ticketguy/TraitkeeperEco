/**
 * Debug Logger - Production-Safe Console Wrapper
 *
 * This module provides a production-safe wrapper around console methods.
 * In production (when DEBUG_MODE is false), console statements are suppressed.
 * In development, they work normally.
 *
 * Usage:
 *   // In your base template:
 *   <script>window.DEBUG_MODE = {{ DEBUG|lower }};</script>
 *   <script src="{% static 'js/debug-logger.js' %}"></script>
 *
 *   // In your code (replace // console.log with debugLog):
 *   debugLog('User clicked button', buttonData);
 *   debugWarn('API rate limit approaching');
 *   debugError('Failed to load collection', error);
 */

(function(window) {
    'use strict';

    // Check if DEBUG_MODE is set, default to false for safety
    const isDebugMode = window.DEBUG_MODE === true;

    /**
     * Debug log - only logs in development
     */
    window.debugLog = function(...args) {
        if (isDebugMode && console && // console.log) {
            // console.log(...args);
        }
    };

    /**
     * Debug warn - only logs in development
     */
    window.debugWarn = function(...args) {
        if (isDebugMode && console && console.warn) {
            console.warn(...args);
        }
    };

    /**
     * Debug error - only logs in development
     */
    window.debugError = function(...args) {
        if (isDebugMode && console && console.error) {
            console.error(...args);
        }
    };

    /**
     * Debug info - only logs in development
     */
    window.debugInfo = function(...args) {
        if (isDebugMode && console && console.info) {
            console.info(...args);
        }
    };

    /**
     * Debug table - only logs in development
     */
    window.debugTable = function(...args) {
        if (isDebugMode && console && console.table) {
            console.table(...args);
        }
    };

    /**
     * Debug group - only logs in development
     */
    window.debugGroup = function(...args) {
        if (isDebugMode && console && console.group) {
            console.group(...args);
        }
    };

    /**
     * Debug group end - only logs in development
     */
    window.debugGroupEnd = function() {
        if (isDebugMode && console && console.groupEnd) {
            console.groupEnd();
        }
    };

    /**
     * Production-safe error logger
     * This ALWAYS logs errors, even in production, but sanitized
     */
    window.logError = function(message, error, context = {}) {
        if (console && console.error) {
            if (isDebugMode) {
                // In development, log everything
                console.error('[Error]', message, error, context);
            } else {
                // In production, log only the message (no sensitive details)
                console.error('[Error]', message);

                // Optionally send to error tracking service (Sentry, etc.)
                if (window.Sentry && typeof window.Sentry.captureException === 'function') {
                    window.Sentry.captureException(error, {
                        tags: { context: 'frontend' },
                        extra: context
                    });
                }
            }
        }
    };

    /**
     * Performance logger - only in development
     */
    window.debugPerf = {
        start: function(label) {
            if (isDebugMode && console && console.time) {
                console.time(label);
            }
        },
        end: function(label) {
            if (isDebugMode && console && console.timeEnd) {
                console.timeEnd(label);
            }
        }
    };

    // Log initialization status
    if (isDebugMode) {
        // console.log('%c🔍 Debug Mode Enabled', 'color: #4CAF50; font-weight: bold; font-size: 14px;');
        // console.log('Debug logging is active. Use debugLog(), debugWarn(), debugError() for logging.');
    } else {
        // Optionally override console methods in production to prevent accidental logging
        if (window.STRICT_PRODUCTION_MODE === true) {
            const noop = function() {};
            // console.log = noop;
            console.warn = noop;
            console.info = noop;
            console.debug = noop;
            // Keep console.error for critical issues
        }
    }

    // Export debug status
    window.isDebugMode = isDebugMode;

})(window);
