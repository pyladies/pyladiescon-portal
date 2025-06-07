from django.contrib import admin

class AdminExtension(admin.AdminSite):
    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        app_list += [
            {
                "name": "Events/Speaker Management",
                "app_label": "prtlx_mgmt",
                "models": [
                    {
                        "name": "event",
                        "object_name": "event",
                        "admin_url": "/admin/event",
                        "view_only": True
                    },
                    {
                        "name": "speaker",
                        "object_name": "speaker",
                        "admin_url": "/admin/speaker",
                        "view_only": True
                    }
                ]
            }
        ]

        return app_list
