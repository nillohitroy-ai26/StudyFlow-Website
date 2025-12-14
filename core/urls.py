from django.urls import path
from .views import (
    register_login_page,
    RegisterView,
    LoginView,
    LogoutView,
    index,
    DashboardView,
    CourseListView,
    CourseDetailView,
    ChatView,
    QuizGenerateView,
    UploadNotesView,
    ChatHistoryView,
    UpdateProfileView,
    DeleteFileView,
    UpdateProgressView,
    GenerateQuizView,
    SubmitQuizView,
    CourseFilesView,
    GetProgressView,
    FileDetailView,
)

urlpatterns = [
    # ===== Authentication Routes =====
    # Login/Register page (combined with tabs)
    path('register/', register_login_page, name='register'),
    
    # Authentication API endpoints
    path('api/register/', RegisterView.as_view(), name='api-register'),
    path('api/login/', LoginView.as_view(), name='api-login'),
    path('api/logout/', LogoutView.as_view(), name='api-logout'),
    path('api/update-profile/', UpdateProfileView.as_view(), name='api-update-profile'),

    # In core/urls.py, add:
    path('api/files/delete/', DeleteFileView.as_view()),
    path('api/progress/update/', UpdateProgressView.as_view()),
    path('api/quiz/generate/', GenerateQuizView.as_view()),
    path('api/quiz/submit/', SubmitQuizView.as_view()),
    path('api/progress/<int:course_id>/', GetProgressView.as_view()),
    path('api/courses/<int:course_id>/files/', CourseFilesView.as_view(), name='api-course-files'),

    path('api/files/<int:file_id>/', FileDetailView.as_view(), name='file-detail'),


    
    # ===== Main App Routes =====
    # Index (requires authentication, redirects to register if not logged in)
    path('', index, name='index'),
    path('index/', index, name='index-alt'),
    
    # API Endpoints (all require authentication)
    path('api/dashboard/', DashboardView.as_view(), name='api-dashboard'),
    path('api/courses/', CourseListView.as_view(), name='api-course-list'),
    path('api/courses/<int:course_id>', CourseDetailView.as_view(), name='api-course-detail'),
    path('api/courses/<int:course_id>/upload/', UploadNotesView.as_view(), name='api-course-upload'),
    path('api/chat/', ChatView.as_view(), name='api-chat'),
    path('api/chat-history/<int:course_id>/', ChatHistoryView.as_view(), name='api-chat-history'),
    path('api/quiz/generate/', QuizGenerateView.as_view(), name='api-quiz-generate'),
]