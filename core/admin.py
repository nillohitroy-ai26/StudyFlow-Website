from django.contrib import admin
from .models import StudentProfile, UserStats, Course, RetentionMetric, ChatMessage, UploadedFile, CourseProgress, FileProgress

admin.site.register(CourseProgress)
admin.site.register(FileProgress)

# Register your models here.
@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'university')
    search_fields = ('user__username', 'user__email', 'display_name', 'university')

@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_streak', 'documents_processed', 'last_activity_date')
    search_fields = ('user__username', 'user__email')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'branch', 'semester', 'status', 'is_completed', 'created_at')
    list_filter = ('branch', 'semester', 'status', 'is_completed')
    search_fields = ('name', 'user__username', 'user__email')

@admin.register(RetentionMetric)
class RetentionMetricAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'score')
    list_filter = ('date',)
    search_fields = ('user__username', 'user__email')

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    Admin interface for ChatMessage model.
    Displays all messages with filtering and search capabilities.
    """
    list_display = ('id', 'user', 'course', 'role', 'message_preview', 'created_at')
    list_filter = ('role', 'created_at', 'course', 'user')
    search_fields = ('user__username', 'user__email', 'course__name', 'message')
    readonly_fields = ('created_at', 'message_display')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Message Info', {
            'fields': ('user', 'course', 'role')
        }),
        ('Content', {
            'fields': ('message_display',),
            'description': 'Full message content (read-only)'
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def message_preview(self, obj):
        """Display first 75 characters of message in list view"""
        return obj.message[:75] + '...' if len(obj.message) > 75 else obj.message
    message_preview.short_description = 'Message'
    
    def message_display(self, obj):
        """Display full message content in detail view"""
        return obj.message
    message_display.short_description = 'Full Message Content'
    
    def get_queryset(self, request):
        """
        Filter messages based on user permissions.
        Superusers see all messages.
        Regular staff only see messages from their own user.
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)
    
    # Make it read-only (messages shouldn't be edited)
    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete messages"""
        return request.user.is_superuser
    
    def has_add_permission(self, request):
        """Messages are created by the app, not admin"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Messages are read-only in admin"""
        return False
    
@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'user', 'gemini_state', 'uploaded_at')


# Custom admin site configuration
admin.site.site_header = "StudyFlow Admin"
admin.site.site_title = "StudyFlow Administration"
admin.site.index_title = "Welcome to StudyFlow Admin"