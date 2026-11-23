from django.contrib import admin

# Content is managed in the custom /staff/ workspace.
# Django admin remains available for account administration.
admin.site.site_header = "Ministry account administration"
admin.site.site_title = "Ministry accounts"
