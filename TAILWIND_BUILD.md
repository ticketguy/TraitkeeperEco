# Tailwind CSS Build Guide

## Overview
This project now uses **compiled Tailwind CSS** instead of the CDN for significantly better performance:
- **~1.5 seconds** saved on main thread time
- **38KB smaller** transfer size (89KB vs 127KB)
- **Zero JavaScript overhead** (no runtime compilation)

## Setup

### Install Dependencies
```bash
npm install
```

This installs:
- `tailwindcss` - The CSS framework
- `postcss` - CSS processor
- `autoprefixer` - Browser compatibility

## Build Commands

### Production Build (Minified)
```bash
npm run build:css
```
Builds minified CSS to `static/css/tailwind-compiled.css`

### Development Watch Mode
```bash
npm run watch:css
```
Watches for changes and auto-rebuilds CSS

### Quick Development
```bash
npm run dev
```
Alias for watch mode

## Configuration Files

### `tailwind.config.js`
Contains all Tailwind configuration:
- Custom colors (purple branding)
- Custom breakpoints (xs, sm, md, lg, xl, 2xl)
- Custom animations (fade-in, slide-up, etc.)
- Dark mode settings

### `static/css/tailwind-input.css`
Input file with Tailwind directives and custom CSS variables

### `static/css/tailwind-compiled.css`
**Generated file** - Do not edit manually!

## Workflow

### When Making UI Changes

1. **If you add new Tailwind classes in templates:**
   ```bash
   npm run build:css
   ```
   Then run:
   ```bash
   python manage.py collectstatic --noinput
   ```

2. **During active development:**
   Run watch mode in a separate terminal:
   ```bash
   npm run watch:css
   ```

3. **Before committing:**
   Always rebuild production CSS:
   ```bash
   npm run build:css
   ```

## Template Integration

The compiled CSS is loaded in `templates/index page/base.html`:
```html
<link rel="stylesheet" href="{% static 'css/tailwind-compiled.css' %}" type="text/css">
```

## Performance Impact

**Before (CDN):**
- 127KB transferred
- 1,464ms main thread time
- JavaScript runtime compilation

**After (Compiled):**
- 89KB transferred (30% reduction)
- ~0ms main thread time (CSS only)
- Instant parse & render

## Troubleshooting

### CSS not updating?
1. Run `npm run build:css`
2. Run `python manage.py collectstatic --noinput`
3. Hard refresh browser (Ctrl+Shift+R)

### Missing styles?
Check that your HTML classes are in the content paths in `tailwind.config.js`:
```javascript
content: [
  "./templates/**/*.html",
  "./static/js/**/*.js",
  "./*/templates/**/*.html",
]
```

### Build errors?
Update dependencies:
```bash
npm update
npx update-browserslist-db@latest
```

## Production Deployment

For Docker deployments, ensure the `static/css/tailwind-compiled.css` file is:
1. Built before building the Docker image
2. Included in the staticfiles collection
3. Served correctly by your web server (nginx/whitenoise)

## Development Notes

- The CDN version has been completely removed
- All Tailwind config moved from inline `<script>` to `tailwind.config.js`
- Custom animations and utilities preserved
- Dark mode support maintained
- All responsive breakpoints working
