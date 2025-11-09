#!/bin/bash
# ==================================================
# Console.log Cleanup Script for TraitKeeper
# ==================================================
# This script helps clean up console.log statements for production
# Run this before deploying to production
# ==================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "=================================================="
echo "TraitKeeper Console.log Cleanup Script"
echo "=================================================="
echo ""

# Function to count console statements
count_console_statements() {
    local pattern=$1
    local path=$2
    grep -r "$pattern" "$path" 2>/dev/null | wc -l || echo "0"
}

# Count current console statements
CONSOLE_LOG_HTML=$(count_console_statements "console\.log" "templates/")
CONSOLE_ALL_JS=$(count_console_statements "console\." "static/js/")
TOTAL=$((CONSOLE_LOG_HTML + CONSOLE_ALL_JS))

echo -e "${YELLOW}Current Console Statement Count:${NC}"
echo "  - HTML templates: $CONSOLE_LOG_HTML console.log statements"
echo "  - JavaScript files: $CONSOLE_ALL_JS console.* statements"
echo "  - Total: $TOTAL statements"
echo ""

echo "=================================================="
echo "Cleanup Options:"
echo "=================================================="
echo ""
echo "1. DRY RUN - Show what would be changed (recommended first)"
echo "2. REPLACE - Replace console.log with debugLog (safe for gradual migration)"
echo "3. COMMENT OUT - Comment out all console.log statements"
echo "4. REMOVE - Remove all console.log lines (aggressive)"
echo "5. EXIT - Exit without changes"
echo ""
read -p "Select option (1-5): " option

case $option in
    1)
        echo ""
        echo -e "${BLUE}DRY RUN MODE${NC}"
        echo "Files that would be modified:"
        echo ""
        echo "HTML Templates with console.log:"
        grep -rl "console\.log" templates/ 2>/dev/null | head -20 || echo "None found"
        echo ""
        echo "JavaScript files with console statements:"
        grep -rl "console\." static/js/ 2>/dev/null | head -20 || echo "None found"
        echo ""
        echo -e "${GREEN}✓ Dry run complete${NC}"
        ;;

    2)
        echo ""
        echo -e "${YELLOW}REPLACE MODE - Converting console.log to debugLog${NC}"
        echo ""

        # Backup files first
        echo "Creating backup..."
        BACKUP_DIR="backup_console_cleanup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        cp -r templates "$BACKUP_DIR/" 2>/dev/null || true
        cp -r static/js "$BACKUP_DIR/" 2>/dev/null || true
        echo -e "${GREEN}✓ Backup created in: $BACKUP_DIR${NC}"
        echo ""

        # Replace in HTML templates
        echo "Replacing in HTML templates..."
        find templates/ -type f -name "*.html" -exec sed -i 's/console\.log/debugLog/g' {} + 2>/dev/null || true

        # Replace in JavaScript files
        echo "Replacing in JavaScript files..."
        find static/js/ -type f -name "*.js" ! -name "debug-logger.js" -exec sed -i 's/console\.log/debugLog/g' {} + 2>/dev/null || true
        find static/js/ -type f -name "*.js" ! -name "debug-logger.js" -exec sed -i 's/console\.warn/debugWarn/g' {} + 2>/dev/null || true
        find static/js/ -type f -name "*.js" ! -name "debug-logger.js" -exec sed -i 's/console\.error/debugError/g' {} + 2>/dev/null || true
        find static/js/ -type f -name "*.js" ! -name "debug-logger.js" -exec sed -i 's/console\.info/debugInfo/g' {} + 2>/dev/null || true

        echo ""
        echo -e "${GREEN}✓ Replacement complete!${NC}"
        echo ""
        echo -e "${YELLOW}IMPORTANT NEXT STEPS:${NC}"
        echo "1. Add debug-logger.js to your base template:"
        echo "   <script>window.DEBUG_MODE = {{ DEBUG|lower }};</script>"
        echo "   <script src=\"{% static 'js/debug-logger.js' %}\"></script>"
        echo ""
        echo "2. Test your application thoroughly"
        echo ""
        echo "3. If issues occur, restore from backup:"
        echo "   cp -r $BACKUP_DIR/templates/* templates/"
        echo "   cp -r $BACKUP_DIR/static/js/* static/js/"
        ;;

    3)
        echo ""
        echo -e "${YELLOW}COMMENT OUT MODE${NC}"
        echo ""

        # Backup files first
        echo "Creating backup..."
        BACKUP_DIR="backup_console_cleanup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        cp -r templates "$BACKUP_DIR/" 2>/dev/null || true
        cp -r static/js "$BACKUP_DIR/" 2>/dev/null || true
        echo -e "${GREEN}✓ Backup created in: $BACKUP_DIR${NC}"
        echo ""

        # Comment out in HTML templates
        echo "Commenting out in HTML templates..."
        find templates/ -type f -name "*.html" -exec sed -i 's/\([[:space:]]*\)console\.log/\1\/\/ console.log/g' {} + 2>/dev/null || true

        # Comment out in JavaScript files
        echo "Commenting out in JavaScript files..."
        find static/js/ -type f -name "*.js" -exec sed -i 's/\([[:space:]]*\)console\.log/\1\/\/ console.log/g' {} + 2>/dev/null || true

        echo ""
        echo -e "${GREEN}✓ Console statements commented out${NC}"
        echo "Backup location: $BACKUP_DIR"
        ;;

    4)
        echo ""
        echo -e "${RED}REMOVE MODE - This will delete console.log lines${NC}"
        read -p "Are you sure? This is irreversible! (yes/no): " confirm

        if [ "$confirm" = "yes" ]; then
            # Backup files first
            echo "Creating backup..."
            BACKUP_DIR="backup_console_cleanup_$(date +%Y%m%d_%H%M%S)"
            mkdir -p "$BACKUP_DIR"
            cp -r templates "$BACKUP_DIR/" 2>/dev/null || true
            cp -r static/js "$BACKUP_DIR/" 2>/dev/null || true
            echo -e "${GREEN}✓ Backup created in: $BACKUP_DIR${NC}"
            echo ""

            # Remove from templates
            echo "Removing from HTML templates..."
            find templates/ -type f -name "*.html" -exec sed -i '/console\.log/d' {} + 2>/dev/null || true

            # Remove from JavaScript
            echo "Removing from JavaScript files..."
            find static/js/ -type f -name "*.js" -exec sed -i '/console\.log/d' {} + 2>/dev/null || true

            echo ""
            echo -e "${GREEN}✓ Console.log statements removed${NC}"
            echo "Backup location: $BACKUP_DIR"
        else
            echo "Cancelled."
        fi
        ;;

    5)
        echo "Exiting without changes."
        exit 0
        ;;

    *)
        echo -e "${RED}Invalid option${NC}"
        exit 1
        ;;
esac

# Recount after changes
if [ "$option" != "1" ] && [ "$option" != "5" ]; then
    echo ""
    echo "=================================================="
    echo "Verification:"
    echo "=================================================="
    CONSOLE_LOG_HTML_AFTER=$(count_console_statements "console\.log" "templates/")
    CONSOLE_ALL_JS_AFTER=$(count_console_statements "console\." "static/js/")
    TOTAL_AFTER=$((CONSOLE_LOG_HTML_AFTER + CONSOLE_ALL_JS_AFTER))

    echo "  - HTML templates: $CONSOLE_LOG_HTML → $CONSOLE_LOG_HTML_AFTER"
    echo "  - JavaScript files: $CONSOLE_ALL_JS → $CONSOLE_ALL_JS_AFTER"
    echo "  - Total: $TOTAL → $TOTAL_AFTER"
    echo ""

    if [ $TOTAL_AFTER -lt $TOTAL ]; then
        echo -e "${GREEN}✓ Successfully reduced console statements!${NC}"
    fi
fi

echo ""
echo "=================================================="
echo "✓ Cleanup script complete"
echo "=================================================="
