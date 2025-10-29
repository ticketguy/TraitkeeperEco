Admin Site README

This file explains the admin_site.py file in the traitkeeper app in a simple way. The admin_site.py file is part of the admin panel for TraitKeeper, a platform that helps manage NFT data. It creates a special admin area where admins can manage users, NFT collections, API tokens, and more.
What is admin_site.py?
The admin_site.py file sets up a custom admin panel for TraitKeeper. It’s built on top of Django’s admin system but adds extra features like generating API tokens, managing NFT collections, and viewing notifications. It’s like the control room for admins to manage the platform.
Key Features
Here’s what the admin panel does:

Manage NFT Collections: Admins can add new NFT collections or refresh existing ones.
Generate API Tokens: Admins can create tokens for external users to use the APIs.
View Notifications: Admins can see important updates, like when collections are added or refreshed.
Set RPC Providers: Admins can choose which service (like Helius or QuickNode) to use for fetching blockchain data.
Dashboard Stats: The main admin page shows stats like user counts, server usage, and recent actions.

Functions Explained
1. get_urls()

What it does: Adds special links (URLs) to the admin panel so admins can access custom pages.
Simple explanation: This function creates the web addresses for pages like “Generate Tokens” or “Refresh Collections.” It also makes sure only certain apps (like traitkeeper, wallet, etc.) can be managed in the admin panel.
How it’s used: When you visit /admin/, this function helps Django know which pages to show, like /admin/generate-tokens/.
Example: When you click “Generate Tokens” in the admin panel, this function makes sure the link works.

2. validate_websocket_url(url)

What it does: Checks if a WebSocket URL (used for real-time data) is correct.
Simple explanation: Some blockchain services use WebSocket URLs (starting with ws:// or wss://) to send live updates. This function makes sure the URL is in the right format.
How it’s used: When an admin adds a new blockchain provider (like QuickNode), this function checks if the WebSocket URL is valid.
Example: If an admin enters wss://example.com, this function says “Yes, that’s a good URL.” If they enter http://example.com, it says “No, that’s not a WebSocket URL.”

3. set_primary_provider_view(request)

What it does: Lets admins choose the main blockchain service (called an RPC provider) to fetch NFT data.
Simple explanation: TraitKeeper needs to talk to blockchain services to get NFT data. This function lets admins pick which service to use (like Helius or QuickNode) or add a new one.
How it’s used: Admins go to /admin/set-primary-provider/, pick a service from a list, or add a new one by entering its details (like its URL).
Example: An admin can choose “Helius” as the main service or add a new service like “QuickNode” by giving its URL.

4. refresh_collections_view(request)

What it does: Updates the data for existing NFT collections.
Simple explanation: Sometimes NFT data changes (like new NFTs being added). This function lets admins refresh all collections to get the latest info.
How it’s used: Admins visit /admin/refresh-collections/ and click a button to start the refresh. They’ll see how many collections were updated successfully.
Example: If a collection has new NFTs, an admin can refresh it to update the data in TraitKeeper.

5. populate_collections_view(request)

What it does: Adds new NFT collections to TraitKeeper by entering their addresses.
Simple explanation: Admins can type in the addresses of new NFT collections, and this function fetches their data and saves it to the platform.
How it’s used: Admins go to /admin/populate-collections/, enter a list of collection addresses, and submit the form. They’ll see which ones were added successfully.
Example: An admin enters the address of a new NFT collection, and TraitKeeper fetches its details and adds it to the system.

6. notifications_view(request)

What it does: Shows admins their notifications and lets them mark them as read or unread.
Simple explanation: This page displays messages for admins, like “A new collection was added!” Admins can mark these messages as read to keep track of what they’ve seen.
How it’s used: Admins visit /admin/notifications/ to see their messages. They can select messages and mark them as read or unread.
Example: An admin sees a message saying “Collections refreshed,” marks it as read, and it no longer shows as new.

7. mark_notification_read(request, notification_id)

What it does: Marks a single notification as read.
Simple explanation: When an admin clicks “Mark as read” on a notification, this function updates it so it’s no longer marked as new.
How it’s used: This happens when an admin clicks a link like /admin/notifications/mark-read/123/.
Example: An admin clicks “Mark as read” on a notification, and it stops showing as unread.

8. mark_notification_unread(request, notification_id)

What it does: Marks a single notification as unread.
Simple explanation: If an admin wants to mark a notification as new again, this function does that.
How it’s used: This happens when an admin clicks a link like /admin/notifications/mark-unread/123/.
Example: An admin marks a notification as unread to remind themselves to check it later.

9. login(request, extra_context=None)

What it does: Handles logging into the admin panel.
Simple explanation: When an admin tries to log in, this function sends them to the custom login page. If they’re already logged in, it takes them to the admin homepage.
How it’s used: This runs when someone visits /admin/ and isn’t logged in yet.
Example: An admin goes to /admin/, gets sent to the login page, enters their username and password, and then sees the admin dashboard.

10. get_login_url()

What it does: Tells Django where the login page is.
Simple explanation: This function gives the address of the login page for the admin panel.
How it’s used: Django uses this when it needs to redirect someone to the login page.
Example: If an admin tries to access a protected page without logging in, they’re sent to the login page at /admin-panel/login/.

11. template_response(request, template, context=None)

What it does: Shows a webpage with extra admin info added.
Simple explanation: This function makes sure all admin pages have the same look, like the header and sidebar, by adding extra info to them.
How it’s used: Other functions use this to display their pages, like the “Generate Tokens” page.
Example: When an admin visits the “Generate Tokens” page, this function adds the admin header and sidebar to the page.

12. log_action(user, content_type, object_id, object_repr, action_flag, change_message='')

What it does: Keeps a record of actions admins do, like adding or changing things.
Simple explanation: When an admin does something (like generating a token), this function writes it down in a log so other admins can see what happened.
How it’s used: This runs automatically when an admin does something important, like adding a new provider.
Example: When an admin generates a token, this function logs “Admin John generated a token for email@example.com.”

13. index(request, extra_context=None)

What it does: Shows the main admin dashboard page.
Simple explanation: This is the homepage of the admin panel. It shows stats like how many users are on the platform, server usage, recent actions, and pending NFT collections.
How it’s used: Admins see this page when they visit /admin/.
Example: An admin logs in and sees a dashboard with user counts, a graph of logins, and a list of recent actions like “Added a new provider.”

14. app_index(request, app_label, extra_context=None)

What it does: Shows a page for managing a specific app, like traitkeeper or wallet.
Simple explanation: This page shows all the things admins can manage for one app, like a list of tokens in the traitkeeper app, along with recent actions for that app.
How it’s used: Admins visit a page like /admin/traitkeeper/ to manage tokens or other items in that app.
Example: An admin goes to /admin/traitkeeper/ and sees a list of API tokens they can manage.

15. token_list_view(request)

What it does: Shows a list of all API tokens that have been created.
Simple explanation: This page lists all the API tokens, showing who they belong to, when they were created, and when they expire.
How it’s used: Admins visit /admin/tokens/ to see all tokens.
Example: An admin checks /admin/tokens/ and sees a list of tokens with emails like “user@example.com.”

16. generate_tokens_view(request)

What it does: Lets admins create new API tokens for external users.
Simple explanation: Admins can use this page to make a new token for someone to use the APIs. They enter the user’s email and can set an expiry date.
How it’s used: Admins go to /admin/generate-tokens/, fill out a form with an email, and get a new token.
Example: An admin enters “user@example.com” and gets a token that user can use to access the APIs.

How to Use the Admin Panel

Log In: Go to /admin/ and log in with your admin username and password.
Dashboard: You’ll see the main dashboard with stats and links to manage apps like traitkeeper or wallet.
Generate Tokens: Click “Generate Tokens” to create a new API token for an external user.
Manage Collections: Use “Populate Collections” to add new NFT collections or “Refresh Collections” to update existing ones.
Check Notifications: Go to “Notifications” to see important updates and mark them as read.

Things to Know

Only Admins Can Use This: You need to be an admin user with special permissions to access these pages.
Apps You Can Manage: The admin panel only lets you manage certain apps (like traitkeeper, wallet, etc.). If you add a new app, you’ll need to update the get_urls() function to include it.
Logs Keep Track of Actions: Every time you do something (like generating a token), it’s recorded in the “Recent Actions” section so other admins can see what happened.

This README should help you understand what each part of admin_site.py does and how to use the admin panel! If you have questions, ask a developer on your team.
