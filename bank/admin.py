from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from bank import models

admin.site.register(models.User, UserAdmin)
admin.site.register(models.Account)
admin.site.register(models.Transaction)
admin.site.register(models.Corporation)
admin.site.register(models.Employee)
admin.site.register(models.EmployeeInvitation)
admin.site.register(models.FeaturedCorporation)
