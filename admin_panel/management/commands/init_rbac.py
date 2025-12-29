from django.core.management.base import BaseCommand
from admin_panel.models import AdminRole, AdminPermission


class Command(BaseCommand):
    help = "Initialize RBAC system with default roles and permissions"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Initializing RBAC system..."))
        
        # Default permissions
        permissions = [
            ("can_view_dashboard", "Can View Dashboard", "Access dashboard", "dashboard"),
            ("can_view_users", "Can View Users", "View users list", "users"),
            ("can_create_users", "Can Create Users", "Create new users", "users"),
            ("can_edit_users", "Can Edit Users", "Edit users", "users"),
            ("can_delete_users", "Can Delete Users", "Delete users", "users"),
            ("can_view_nft_data", "Can View NFT Data", "View NFT data", "nft"),
            ("can_manage_nft_data", "Can Manage NFT Data", "Manage NFT data", "nft"),
            ("can_populate_collections", "Can Populate Collections", "Populate collections", "nft"),
            ("can_refresh_collections", "Can Refresh Collections", "Refresh collections", "nft"),
            ("can_view_providers", "Can View Providers", "View providers", "providers"),
            ("can_manage_providers", "Can Manage Providers", "Manage providers", "providers"),
            ("can_set_primary_provider", "Can Set Primary Provider", "Set primary provider", "providers"),
            ("can_view_tasks", "Can View Tasks", "View tasks", "tasks"),
            ("can_manage_tasks", "Can Manage Tasks", "Manage tasks", "tasks"),
            ("can_view_logs", "Can View Logs", "View logs", "logs"),
            ("can_view_login_attempts", "Can View Login Attempts", "View login attempts", "logs"),
            ("can_view_settings", "Can View Settings", "View settings", "settings"),
            ("can_manage_settings", "Can Manage Settings", "Manage settings", "settings"),
            ("can_manage_api_tokens", "Can Manage API Tokens", "Manage API tokens", "settings"),
            ("can_view_roles", "Can View Roles", "View roles", "roles"),
            ("can_manage_roles", "Can Manage Roles", "Manage roles", "roles"),
            ("can_assign_roles", "Can Assign Roles", "Assign roles", "roles"),
        ]
        
        created_perms = 0
        for codename, name, desc, cat in permissions:
            perm, created = AdminPermission.objects.get_or_create(
                codename=codename,
                defaults={"name": name, "description": desc, "category": cat, "is_system_permission": True}
            )
            if created:
                created_perms += 1
                self.stdout.write(f"  Created: {name}")
        
        self.stdout.write(self.style.SUCCESS(f"Created {created_perms} permissions"))
        
        # Default roles
        all_perms = [p[0] for p in permissions]
        roles = [
            ("Master Admin", "Full access", all_perms),
            ("System Administrator", "Manage system", ["can_view_dashboard", "can_view_users", "can_view_nft_data", "can_manage_nft_data", "can_populate_collections", "can_refresh_collections", "can_view_providers", "can_manage_providers", "can_set_primary_provider", "can_view_tasks", "can_manage_tasks", "can_view_logs", "can_view_settings", "can_manage_settings", "can_manage_api_tokens"]),
            ("Content Manager", "Manage NFT data", ["can_view_dashboard", "can_view_nft_data", "can_manage_nft_data", "can_populate_collections", "can_refresh_collections", "can_view_tasks"]),
            ("Viewer", "Read-only", ["can_view_dashboard", "can_view_users", "can_view_nft_data", "can_view_providers", "can_view_tasks", "can_view_logs", "can_view_settings"]),
            ("Support Staff", "View logs", ["can_view_dashboard", "can_view_logs", "can_view_login_attempts", "can_view_tasks", "can_view_settings"]),
        ]
        
        created_roles = 0
        for name, desc, perm_codes in roles:
            role, created = AdminRole.objects.get_or_create(
                name=name,
                defaults={"description": desc, "is_system_role": True}
            )
            if created:
                created_roles += 1
                self.stdout.write(f"  Created role: {name}")
            
            perms = AdminPermission.objects.filter(codename__in=perm_codes)
            role.permissions.set(perms)
            self.stdout.write(f"    Assigned {perms.count()} permissions")
        
        self.stdout.write(self.style.SUCCESS(f"Created {created_roles} roles"))
        self.stdout.write(self.style.SUCCESS("RBAC initialization complete!"))
