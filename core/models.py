from django.db import models
from django.contrib.auth.models import User
from PIL import Image, ImageDraw, ImageFont
import io
from django.core.files.base import ContentFile
from django.utils import timezone

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='studentprofile')
    display_name = models.CharField(max_length=100)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    university = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"
    
    def __str__(self):
        return self.display_name
    
    def save(self, *args, **kwargs):
        """Auto-generate avatar with initials if not provided"""
        if not self.avatar:
            # Generate avatar with initials
            initials = self.get_initials()
            avatar_image = self.generate_avatar_with_initials(initials)
            
            # Save to avatar field
            avatar_io = io.BytesIO()
            avatar_image.save(avatar_io, format='PNG')
            avatar_io.seek(0)
            
            filename = f"{self.user.username}_avatar.png"
            self.avatar.save(filename, ContentFile(avatar_io.getvalue()), save=False)
        
        super().save(*args, **kwargs)
    
    def get_initials(self):
        """Extract initials from display name"""
        parts = self.display_name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        elif len(parts) == 1:
            return parts[0][0].upper()
        return "?"
    
    @staticmethod
    def generate_avatar_with_initials(initials, size=200):
        """Generate a colorful avatar with initials"""
        # Color palette (same as StudyFlow gradient colors)
        colors = [
            (14, 165, 233),   # Cyan
            (34, 211, 238),   # Light cyan
            (2, 132, 199),    # Dark cyan
            (3, 105, 161),    # Darker cyan
            (12, 74, 110),    # Very dark cyan
        ]
        
        # Select color based on initials hash
        color = colors[hash(initials) % len(colors)]
        
        # Create image
        img = Image.new('RGB', (size, size), color=color)
        draw = ImageDraw.Draw(img)
        
        # Try to use a nice font, fall back to default
        try:
            font_size = int(size * 0.5)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # Calculate text position (centered)
        bbox = draw.textbbox((0, 0), initials, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2
        
        # Draw text
        draw.text((x, y), initials, fill=(255, 255, 255), font=font)
        
        return img


class UserStats(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    current_streak = models.IntegerField(default=0)
    documents_processed = models.IntegerField(default=0)
    last_activity_date = models.DateField(auto_now=True)
    
    def __str__(self):
        return f"Stats for {self.user.username}"


class Course(models.Model):
    STATUS_CHOICES = [
        ('Just Started', 'Just Started'),
        ('On Track', 'On Track'),
        ('Review Needed', 'Review Needed'),
    ]
    
    BRANCH_CHOICES = [
        ('CSE', 'Computer Science'),
        ('ECE', 'Electronics'),
        ('ME', 'Mechanical'),
        ('CE', 'Civil'),
        ('IT', 'Information Technology'),
        ('OTHER', 'Other'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses')
    name = models.CharField(max_length=200)
    branch = models.CharField(max_length=10, choices=BRANCH_CHOICES, default='CSE')
    semester = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Just Started')
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.status})"


class RetentionMetric(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    score = models.IntegerField()  # 0-100 scale
    
    class Meta:
        unique_together = ('user', 'date')
        ordering = ['date']
    
    def __str__(self):
        return f"{self.user.username} - {self.date}: {self.score}"
    

class ChatMessage(models.Model):
    """Store chat messages for a course with full conversation context"""
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='chat_messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        indexes = [
            models.Index(fields=['user', 'course', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.role}: {self.message[:50]}"
    

class UploadedFile(models.Model):
    """
    Track uploaded files and their Gemini resource names.
    Allows users to delete files and remove context.
    """
    USER_CHOICES = [
        ('pdf', 'PDF'),
        ('txt', 'Text'),
        ('doc', 'Document'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='uploaded_files')
    
    # File info
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=USER_CHOICES, default='pdf')
    file_size = models.BigIntegerField(default=0)  # in bytes
    file_path = models.CharField(max_length=500, blank=True, null=True)
    
    # Gemini API info
    gemini_resource_name = models.CharField(max_length=255, unique=True)
    gemini_uri = models.URLField(null=True, blank=True)
    gemini_state = models.CharField(max_length=20, default='ACTIVE')  # ACTIVE, PROCESSING, FAILED
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Uploaded File'
        verbose_name_plural = 'Uploaded Files'
    
    def __str__(self):
        return f"{self.user.username} - {self.filename}"


class CourseProgress(models.Model):
    """
    Track course progress for each user.
    Updates as user completes files/tasks.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='user_progress')
    
    # Progress tracking
    total_files = models.IntegerField(default=0)  # Total files in course
    completed_files = models.IntegerField(default=0)  # Files user completed
    progress_percentage = models.IntegerField(default=0)  # 0-100%
    
    # Time tracking
    created_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    time_spent_minutes = models.IntegerField(default=0)  # Total minutes spent
    
    # Status
    status_choices = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('paused', 'Paused'),
    ]
    status = models.CharField(max_length=20, choices=status_choices, default='not_started')
    
    class Meta:
        unique_together = ('user', 'course')
        verbose_name = 'Course Progress'
        verbose_name_plural = 'Course Progress'
    
    def __str__(self):
        return f"{self.user.username} - {self.course.name} ({self.progress_percentage}%)"
    
    def update_progress(self):
        """Recalculate progress percentage"""
        if self.total_files > 0:
            self.progress_percentage = int((self.completed_files / self.total_files) * 100)
        else:
            self.progress_percentage = 0
        
        # Update status based on progress
        if self.progress_percentage == 0:
            self.status = 'not_started'
        elif self.progress_percentage == 100:
            self.status = 'completed'
        else:
            self.status = 'in_progress'
        
        self.save()


class FileProgress(models.Model):
    """
    Track individual file progress.
    Updates when user reads/completes a file.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_progress')
    uploaded_file = models.ForeignKey(UploadedFile, on_delete=models.CASCADE, related_name='progress')
    
    # Progress
    pages_read = models.IntegerField(default=0)
    total_pages = models.IntegerField(default=1)
    read_percentage = models.IntegerField(default=0)  # 0-100%
    
    # Status
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Time
    started_at = models.DateTimeField(auto_now_add=True)
    last_read = models.DateTimeField(auto_now=True)
    total_read_time_minutes = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('user', 'uploaded_file')
        verbose_name = 'File Progress'
        verbose_name_plural = 'File Progress'
    
    def __str__(self):
        return f"{self.user.username} - {self.uploaded_file.filename} ({self.read_percentage}%)"
    
    def mark_completed(self):
        """Mark file as completed"""
        self.is_completed = True
        self.completed_at = timezone.now()
        self.read_percentage = 100
        self.save()
        
        # Update course progress
        course_progress = CourseProgress.objects.get(
            user=self.user,
            course=self.uploaded_file.course
        )
        course_progress.completed_files += 1
        course_progress.update_progress()


class GeneratedQuiz(models.Model):
    """
    Store generated quizzes with their questions.
    Links to file or course.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_quizzes')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='quizzes')
    uploaded_file = models.ForeignKey(
        UploadedFile, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='quizzes'
    )
    
    # Quiz info
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    num_questions = models.IntegerField(default=5)
    questions = models.JSONField(default=list)  # Stores quiz questions as JSON
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    generated_from_text = models.BooleanField(default=True)  # True if from text/file, False if general
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Generated Quiz'
        verbose_name_plural = 'Generated Quizzes'
    
    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.num_questions} Q)"


class QuizAttempt(models.Model):
    """
    Track quiz attempts and scores.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(GeneratedQuiz, on_delete=models.CASCADE, related_name='attempts')
    
    # Attempt data
    answers = models.JSONField(default=dict)  # {question_index: selected_answer_index}
    score = models.IntegerField(default=0)  # Number of correct answers
    percentage = models.IntegerField(default=0)  # Score percentage (0-100)
    
    # Time
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(auto_now=True)
    time_spent_seconds = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-completed_at']
        verbose_name = 'Quiz Attempt'
        verbose_name_plural = 'Quiz Attempts'
    
    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} ({self.percentage}%)"
    
    def calculate_score(self):
        """Calculate score based on answers and correct options"""
        if not self.quiz.questions:
            return 0
        
        correct_count = 0
        for idx, question in enumerate(self.quiz.questions):
            selected = self.answers.get(str(idx))
            correct = question.get('correct')
            
            if selected is not None and selected == correct:
                correct_count += 1
        
        self.score = correct_count
        self.percentage = int((correct_count / len(self.quiz.questions)) * 100)
        self.save()
        
        return self.percentage