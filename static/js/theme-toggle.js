document.addEventListener("DOMContentLoaded", function () {
  const themeToggle = document.getElementById("theme-toggle");
  const htmlElement = document.documentElement;

  console.log("Theme toggle JS loaded, button found:", !!themeToggle);

  // Check if user has previously set a theme preference
  const savedTheme = localStorage.getItem("theme");
  if (savedTheme === "dark") {
    htmlElement.classList.add("dark");
    updateToggleIcon(true);
  } else if (savedTheme === "light") {
    htmlElement.classList.remove("dark");
    updateToggleIcon(false);
  } else {
    // No saved preference, check system preference
    const prefersDark = window.matchMedia(
      "(prefers-color-scheme: dark)"
    ).matches;
    if (prefersDark) {
      htmlElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
      updateToggleIcon(true);
    }
  }

  // Toggle theme when the button is clicked
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      console.log("Theme toggle clicked!");
      const isDarkMode = htmlElement.classList.contains("dark");

      if (isDarkMode) {
        htmlElement.classList.remove("dark");
        localStorage.setItem("theme", "light");
        updateToggleIcon(false);
        console.log("Switched to light mode");
      } else {
        htmlElement.classList.add("dark");
        localStorage.setItem("theme", "dark");
        updateToggleIcon(true);
        console.log("Switched to dark mode");
      }
    });
  } else {
    console.error("Theme toggle button not found!");
  }

  // Listen for system theme changes
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", (e) => {
      if (!localStorage.getItem("theme")) {
        if (e.matches) {
          htmlElement.classList.add("dark");
          updateToggleIcon(true);
        } else {
          htmlElement.classList.remove("dark");
          updateToggleIcon(false);
        }
      }
    });

  function updateToggleIcon(isDarkMode) {
    if (!themeToggle) return;

    // Update the icon based on the current theme
    if (isDarkMode) {
      // Sun icon for dark mode (clicking will switch to light)
      themeToggle.innerHTML = `
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                    <path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0s.39-1.03 0-1.41L5.99 4.58zm12.37 12.37c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0 .39-.39.39-1.03 0-1.41l-1.06-1.06zm1.06-10.96c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06zM7.05 18.36c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41s1.03.39 1.41 0l1.06-1.06z" />
                </svg>
            `;
    } else {
      // Moon icon for light mode (clicking will switch to dark)
      themeToggle.innerHTML = `
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                    <path d="M12 3c-4.97 0-9 4.03-9 9s4.03 9 9 9 9-4.03 9-9c0-.46-.04-.92-.1-1.36-.98 1.37-2.58 2.26-4.4 2.26-2.98 0-5.4-2.42-5.4-5.4 0-1.81.89-3.42 2.26-4.4-.44-.06-.9-.1-1.36-.1z" />
                </svg>
            `;
    }
  }
});
