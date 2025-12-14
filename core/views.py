from django.http import JsonResponse, FileResponse
from django.views import View
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import FileSystemStorage
from django.db.models import Avg, Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from .models import Course, UserStats, RetentionMetric, StudentProfile, ChatMessage, UploadedFile, CourseProgress, FileProgress, GeneratedQuiz, QuizAttempt
from .services import GeminiService
import json
import os
import datetime
from django.conf import settings
from django.core.files.storage import default_storage

# Helper functions
def success(data):
    return JsonResponse({'status': 'success', 'data': data})

def error(msg, code=400):
    return JsonResponse({'status': 'error', 'message': msg}, status=code)

# ============ AUTHENTICATION VIEWS ============

def register_login_page(request):
    """Render register/login page with tabs"""
    if request.user.is_authenticated:
        return redirect('/')
    return render(request, 'register.html')

class RegisterView(View):
    """Handle user registration"""
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['first_name', 'last_name', 'email', 'password', 'password_confirm']
            for field in required_fields:
                if not data.get(field):
                    return error(f"{field.replace('_', ' ')} is required", 400)
            
            # Validate password match
            if data['password'] != data['password_confirm']:
                return error("Passwords do not match", 400)
            
            # Validate password length
            if len(data['password']) < 8:
                return error("Password must be at least 8 characters", 400)
            
            # Check if email already exists
            if User.objects.filter(email=data['email']).exists():
                return error("Email already registered", 400)
            
            if User.objects.filter(username=data['email']).exists():
                return error("Email already registered", 400)
            
            # Create user
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                password=data['password']
            )
            
            # Create student profile
            display_name = f"{data['first_name']}"
            student_profile = StudentProfile.objects.create(
                user=user,
                display_name=display_name,
                university=data.get('university', '')
            )
            
            # Create user stats
            UserStats.objects.create(user=user)
            
            # Log the user in
            login(request, user)
            
            return success({
                'message': 'Account created successfully',
                'user_id': user.id,
                'redirect': ''
            })
            
        except json.JSONDecodeError:
            return error("Invalid JSON", 400)
        except Exception as e:
            print(f"Registration error: {str(e)}")
            return error(str(e), 500)

class LoginView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)

            if not data.get('email'):
                return error("Email is required", 400)
            if not data.get('password'):
                return error("Password is required", 400)

            identifier = data['email']
            password = data['password']

            # Try to find user by email OR username
            try:
                user_obj = User.objects.get(
                    Q(email__iexact=identifier) | Q(username__iexact=identifier)
                )
                username_for_auth = user_obj.username
            except User.DoesNotExist:
                username_for_auth = identifier  # fall back (for users with username=email)

            user = authenticate(request, username=username_for_auth, password=password)

            if user is None:
                return error("Invalid email or password", 401)

            login(request, user)

            return success({
                'message': 'Logged in successfully',
                'user_id': user.id,
                'redirect': '/'
            })
        except json.JSONDecodeError:
            return error("Invalid JSON", 400)
        except Exception as e:
            print(f"Login error: {str(e)}")
            return error(str(e), 500)

class LogoutView(View):
    def post(self, request):
        try:
            logout(request)
            return success({'message': 'Logged out successfully'})
        except Exception as e:
            return error(str(e), 500)

# ============ MAIN APP VIEWS (Require Authentication) ============

def index(request):
    """Main dashboard - requires authentication"""
    if not request.user.is_authenticated:
        return redirect('register/')
    return render(request, 'index.html')

@method_decorator(csrf_exempt, name='dispatch')
class CourseDetailView(View):
    """
    PATCH /api/courses/<id>/  -> rename, toggle completed/status
    DELETE /api/courses/<id>/ -> delete
    """
    def patch(self, request, course_id):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            course = Course.objects.get(id=course_id, user=user)
            data = json.loads(request.body)

            new_name = data.get("name")
            if new_name:
                course.name = new_name

            if "is_completed" in data:
                course.is_completed = bool(data["is_completed"])

            if "status" in data:
                course.status = data["status"]

            course.save()
            return success({"id": course.id, "name": course.name, "status": course.status, "is_completed": course.is_completed})
        except Course.DoesNotExist:
            return error("Course not found", 404)
        except Exception as e:
            return error(str(e), 500)

    def delete(self, request, course_id):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            course = Course.objects.get(id=course_id, user=user)
            course.delete()
            return success({"deleted": True})
        except Course.DoesNotExist:
            return error("Course not found", 404)
        except Exception as e:
            return error(str(e), 500)

class DashboardView(View):
    @method_decorator(csrf_exempt, name='dispatch')
    def get(self, request):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            # ✅ ALWAYS ensure StudentProfile exists
            profile, created = StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    'display_name': f"{user.first_name or user.username.split('@')[0]}",
                    'university': 'University'
                }
            )
            
            # ✅ Fix blank display_name
            if not profile.display_name.strip():
                profile.display_name = f"{user.first_name or user.username.split('@')[0]} Student"
                profile.save()

            # Get stats
            stats, _ = UserStats.objects.get_or_create(user=user)
            avg_score = RetentionMetric.objects.filter(user=user).aggregate(Avg('score'))['score__avg']
            mastery = round(avg_score, 1) if avg_score else 0.0
            streak = stats.current_streak or 0

            # Recent courses & retention
            recent_courses = Course.objects.filter(user=user).order_by('-created_at')[:2]
            retention_objs = RetentionMetric.objects.filter(user=user).order_by('-date')[:7]
            retention_data = [r.score for r in retention_objs]
            while len(retention_data) < 7:
                retention_data.insert(0, 0)

            data = {
                'username': profile.display_name,  # Always use display_name
                'firstname': (user.first_name or profile.display_name.split()[0].split(' ')[0]),  # Proper first name
                'useremail': user.email,
                'university': profile.university or 'University',
                'useravatar': profile.avatar.url if profile.avatar else None,
                'stats': {
                    'streak': streak,
                    'mastery': mastery,
                    'docs': stats.documents_processed or 0,
                },
                'recentcourses': list(recent_courses.values('id', 'name', 'branch', 'status', 'is_completed', 'semester')),
                'retentiondata': retention_data,
            }
            return success(data)
        except Exception as e:
            print(f"Dashboard error: {str(e)}")
            return error(str(e), 500)


# core/views.py

class CourseListView(View):
    """
    GET /api/courses   -> list all courses for user
    POST /api/courses  -> create course
    """
    def get(self, request):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            courses = Course.objects.filter(user=user).order_by('-created_at').values(
                "id", "name", "branch", "status", "is_completed", "semester"
            )
            return success(list(courses))
        except Exception as e:
            return error(str(e), 500)

    def post(self, request):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            data = json.loads(request.body)
            new_course = Course.objects.create(
                user=user,
                name=data["name"],
                branch=data["branch"],
                semester=data.get("semester", 1),
                status="Just Started",
            )
            return success({"id": new_course.id, "name": new_course.name})
        except Exception as e:
            return error(str(e), 500)


class ChatView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            user = request.user
            data = json.loads(request.body)
            message = data.get('message')
            course_id = data.get('course_id')

            if not message or not message.strip():
                return error("Message is required", 400)
            
            # Get course if provided
            course = None
            if course_id:
                try:
                    course = Course.objects.get(id=course_id, user=user)
                except Course.DoesNotExist:
                    return error("Course not found", 404)
            
            # Save user message to database
            if course:
                ChatMessage.objects.create(
                    user=user,
                    course=course,
                    role='user',
                    message=message
                )

            file_resources = []
            if course:
                db_files = UploadedFile.objects.filter(
                    user=user,
                    course=course,
                    is_deleted=False,
                    gemini_state='ACTIVE'
                ).values_list('gemini_resource_name', flat=True)

                file_resources = list(db_files)
            
            service = GeminiService()
            
            # Call service with file resources (can be empty list)
            response_text = service.chat(message, file_resources if file_resources else None)
            
            # Validate response
            if not response_text or not str(response_text).strip():
                return error("AI model did not return a response", 500)
            
            response_text = str(response_text).strip()
            
            # Save AI response to database
            if course:
                ChatMessage.objects.create(
                    user=user,
                    course=course,
                    role='assistant',
                    message=response_text
                )

            from .services import update_user_stats_on_chat, calculate_knowledge_mastery
            
            # Update streak, retention, and other stats
            update_user_stats_on_chat(user, course)
            
            # Calculate knowledge mastery
            mastery = calculate_knowledge_mastery(user, course)
            
            return success({
                'response': str(response_text).strip()  # ← Ensure it's a string
            })
        
        except json.JSONDecodeError:
            return error("Invalid JSON", 400)
        except Exception as e:
            print(f"Chat error: {str(e)}")
            return error(str(e), 500)


class ChatHistoryView(LoginRequiredMixin, View):
    """Retrieve chat history for a specific course"""
    
    def get(self, request, course_id):
        try:
            user = request.user
            
            # Get course
            try:
                course = Course.objects.get(id=course_id, user=user)
            except Course.DoesNotExist:
                return error("Course not found", 404)
            
            # Get chat messages for this course
            messages = ChatMessage.objects.filter(
                user=user,
                course=course
            ).values('id', 'role', 'message', 'created_at')
            
            return success({
                'course_id': course.id,
                'course_name': course.name,
                'messages': list(messages)
            })
        
        except Exception as e:
            print(f"Chat history error: {str(e)}")
            return error(str(e), 500)


class QuizGenerateView(View):
    def post(self, request):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)
            
            data = json.loads(request.body)
            file_resources = data.get('file_resources', [])
            
            if not file_resources:
                return error("Please upload notes before generating a quiz.")
            
            service = GeminiService()
            quiz_data = service.generate_quiz(file_resources)
            
            if quiz_data:
                return success({'quiz': quiz_data})
            else:
                return error("Could not generate quiz. Try different notes.")
        except Exception as e:
            return error(str(e), 500)

class UpdateProfileView(View):
    @method_decorator(csrf_exempt, name='dispatch')
    def post(self, request):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)
            
            data = json.loads(request.body)
            
            # Get or create StudentProfile
            profile, created = StudentProfile.objects.get_or_create(user=user)
            
            # Update fields
            if 'displayname' in data and data['displayname'].strip():
                profile.display_name = data['displayname'].strip()
            
            if 'university' in data:
                profile.university = data['university'].strip()
            
            profile.save()
            
            return success({
                'displayname': profile.display_name,
                'university': profile.university,
                'message': 'Profile updated successfully'
            })
        except Exception as e:
            return error(str(e), 500)


from .models import UploadedFile, Course

class UploadNotesView(View):
    def post(self, request, course_id):
        try:
            user = request.user
            if not user.is_authenticated:
                return error("User not authenticated", 401)

            if 'file' not in request.FILES:
                return error('No file provided')

            file_obj = request.FILES['file']

            # Save permanently under MEDIA_ROOT/uploads/
            rel_path = f"uploads/{file_obj.name}"
            saved_path = default_storage.save(rel_path, file_obj)
            full_path = default_storage.path(saved_path)

            service = GeminiService()
            result = service.upload_file_stateless(full_path)

            if not result:
                return error('Gemini API upload failed', 500)

            stats, _ = UserStats.objects.get_or_create(user=user)
            stats.documents_processed += 1
            stats.save()

            try:
                course = Course.objects.get(id=course_id, user=user)
            except Course.DoesNotExist:
                return error("Course not found", 404)

            uploaded = UploadedFile.objects.create(
                user=user,
                course=course,
                filename=os.path.basename(saved_path),
                file_type='pdf',
                file_size=file_obj.size,
                gemini_resource_name=result['resource_name'],
                gemini_uri=result.get('uri', ''),
                gemini_state='ACTIVE',
            )

            return success({
                'id': uploaded.id,
                'filename': uploaded.filename,
                'gemini_resource_name': uploaded.gemini_resource_name,
                'gemini_uri': uploaded.gemini_uri,
            })
        except Exception as e:
            return error(str(e), 500)

class DeleteFileView(LoginRequiredMixin, View):
    """
    Delete a file from Gemini and database.
    Also removes it from user's context for chat.
    """
    
    def post(self, request):
        try:
            user = request.user
            data = json.loads(request.body)
            file_id = data.get('file_id')
            
            if not file_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'File ID required'
                }, status=400)
            
            # Get file
            try:
                uploaded_file = UploadedFile.objects.get(id=file_id, user=user)
            except UploadedFile.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'File not found'
                }, status=404)
            
            # Delete from Gemini API
            service = GeminiService()
            deleted = service.delete_file(uploaded_file.gemini_resource_name)

            filename = uploaded_file.filename  # keep for message
            uploaded_file.delete()
            
            if not deleted:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to delete from Gemini'
                }, status=500)
            
            print(f"[SUCCESS] File deleted: {filename}")
            
            return JsonResponse({
                'status': 'success',
                'message': f'File {filename} deleted successfully',
                'data': {
                    'file_id': file_id,
                    'filename': filename
                }
            })
        
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON'
            }, status=400)
        except Exception as e:
            print(f"[ERROR] Delete file error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
        

class UpdateProgressView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            user = request.user
            data = json.loads(request.body or '{}')
            print("[DEBUG] UpdateProgress payload:", data, "user:", user.id)

            fileid = data.get('fileid')
            courseid = data.get('courseid')
            pagesread = data.get('pagesread', 0)
            totalpages = data.get('totalpages', 1)
            iscompleted = data.get('iscompleted', False)
            timespent = data.get('timespentminutes', 0)

            if not fileid or not courseid:
                print("[DEBUG] Missing ids")
                return JsonResponse({'status': 'error',
                                     'message': 'File ID and Course ID required'}, status=400)

            try:
                uploadedfile = UploadedFile.objects.get(id=fileid, user=user)
                course = Course.objects.get(id=courseid, user=user)
            except (UploadedFile.DoesNotExist, Course.DoesNotExist):
                print("[DEBUG] File or course not found")
                return JsonResponse({'status': 'error',
                                     'message': 'File or course not found'}, status=404)

            fileprogress, created = FileProgress.objects.get_or_create(
                user=user,
                uploadedfile=uploadedfile,
            )
            fileprogress.totalpages = totalpages
            fileprogress.pagesread = pagesread
            fileprogress.readpercentage = int(pagesread / totalpages * 100) if totalpages else 0
            fileprogress.totalreadtimeminutes = timespent
            fileprogress.lastread = timezone.now()
            if iscompleted:
                fileprogress.markcompleted()
            else:
                fileprogress.save()

            courseprogress, _ = CourseProgress.objects.get_or_create(
                user=user,
                course=course,
            )
            courseprogress.totalfiles = UploadedFile.objects.filter(
                course=course, isdeleted=False
            ).count()
            courseprogress.timespentminutes += timespent
            courseprogress.completedfiles = FileProgress.objects.filter(
                user=user,
                uploadedfile__course=course,
                iscompleted=True,
            ).count()
            courseprogress.updateprogress()

            print("[DEBUG] Saved fileprogress:", fileprogress.id,
                  "read%", fileprogress.readpercentage,
                  "course%", courseprogress.progresspercentage)

            return JsonResponse({
                'status': 'success',
                'message': 'Progress updated',
                'data': {
                    'fileprogress': {
                        'readpercentage': fileprogress.readpercentage,
                        'pagesread': fileprogress.pagesread,
                        'totalpages': fileprogress.totalpages,
                        'iscompleted': fileprogress.iscompleted,
                    },
                    'courseprogress': {
                        'progresspercentage': courseprogress.progresspercentage,
                        'completedfiles': courseprogress.completedfiles,
                        'totalfiles': courseprogress.totalfiles,
                    },
                },
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class GenerateQuizView(LoginRequiredMixin, View):
    """
    Generate quiz from file or general knowledge.
    Uses Gemini to create dynamic questions.
    """
    
    def post(self, request):
        try:
            user = request.user
            data = json.loads(request.body)
            
            course_id = data.get('course_id')
            file_id = data.get('file_id')  # Optional
            num_questions = data.get('num_questions', 5)
            quiz_title = data.get('quiz_title', 'Generated Quiz')
            
            if not course_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Course ID required'
                }, status=400)
            
            # Get course
            try:
                course = Course.objects.get(id=course_id, user=user)
            except Course.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Course not found'
                }, status=404)
            
            # Get file if provided
            uploaded_file = None
            file_resources = []
            
            if file_id:
                try:
                    uploaded_file = UploadedFile.objects.get(id=file_id, user=user)
                    file_resources = [uploaded_file.gemini_resource_name]
                    generated_from_text = True
                except UploadedFile.DoesNotExist:
                    pass
            else:
                generated_from_text = False
            
            # Get last N user messages for this course as context
            recent_messages = ChatMessage.objects.filter(
                user=user,
                course=course
            ).order_by('-created_at').values_list('message', flat=True)[:5]
            context_text = "\n".join(list(reversed(recent_messages)))  # oldest -> newest

            service = GeminiService()
            questions = service.generate_quiz(
                file_resources if file_resources else None,
                num_questions,
                course_name=course.name,
                semester=course.semester,
                context_text=context_text)
            
            if isinstance(questions, dict) and questions.get("_error") == "quota_exceeded":
                return JsonResponse({
                    'status': 'error',
                    'message': 'Gemini quota exceeded (20 req/day). Wait or upgrade.'
                }, status=429)
            
            if not questions:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to generate quiz'
                }, status=500)
            
            # Save quiz to database
            quiz = GeneratedQuiz.objects.create(
                user=user,
                course=course,
                uploaded_file=uploaded_file,
                title=quiz_title,
                num_questions=len(questions),
                questions=questions,
                generated_from_text=generated_from_text
            )
            
            print(f"[SUCCESS] Quiz generated: {quiz.title} with {len(questions)} questions")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Quiz generated successfully',
                'data': {
                    'quiz_id': quiz.id,
                    'title': quiz.title,
                    'num_questions': quiz.num_questions,
                    'questions': quiz.questions
                }
            })
        
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON'
            }, status=400)
        except Exception as e:
            print(f"[CRITICAL] Quiz view unhandled exception: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # FORCE SHORT MESSAGE FOR ALL ERRORS
            error_msg = str(e)
            if "quota" in error_msg.lower() or "429" in error_msg:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Gemini quota exceeded (20 req/day). Wait or upgrade.'
                }, status=429)
                
            return JsonResponse({'status': 'error', 'message': 'Server error'}, status=500)

class SubmitQuizView(LoginRequiredMixin, View):
    """
    Submit quiz answers and calculate score.
    Uses Gemini to verify answers if needed.
    """
    
    def post(self, request):
        try:
            user = request.user
            data = json.loads(request.body)
            
            quiz_id = data.get('quiz_id')
            answers = data.get('answers', {})  # {question_index: selected_answer}
            time_spent = data.get('time_spent_seconds', 0)
            
            if not quiz_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Quiz ID required'
                }, status=400)
            
            # Get quiz
            try:
                quiz = GeneratedQuiz.objects.get(id=quiz_id, user=user)
            except GeneratedQuiz.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Quiz not found'
                }, status=404)
            
            # Create attempt
            attempt = QuizAttempt.objects.create(
                user=user,
                quiz=quiz,
                answers=answers,
                time_spent_seconds=time_spent
            )
            
            # Calculate score
            percentage = attempt.calculate_score()
            
            # Update user stats
            from .services import update_user_stats_on_chat
            update_user_stats_on_chat(user, quiz.course)
            
            print(f"[SUCCESS] Quiz submitted: {quiz.title} - Score: {percentage}%")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Quiz submitted successfully',
                'data': {
                    'attempt_id': attempt.id,
                    'score': attempt.score,
                    'percentage': attempt.percentage,
                    'correct_answers': [q.get('correct') for q in quiz.questions]
                }
            })
        
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON'
            }, status=400)
        except Exception as e:
            print(f"[ERROR] Submit quiz error: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
        

class FileDetailView(LoginRequiredMixin, View):
    def get(self, request, file_id):
        try:
            user = request.user
            uploaded = UploadedFile.objects.get(id=file_id, user=user)
            
            # Use the serve endpoint instead of direct media path
            pdf_url = f"/media/uploads/{uploaded.filename}"
            
            return JsonResponse({
                'status': 'success',
                'data': {
                    'file_id': uploaded.id,
                    'course_id': uploaded.course.id,
                    'filename': uploaded.filename,
                    'pdf_url': pdf_url,  # <-- THIS IS THE KEY CHANGE
                },
            })
        except UploadedFile.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'File not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

        
class GetProgressView(LoginRequiredMixin, View):
    """
    Get progress data for a course.
    Includes file progress and overall course progress.
    """
    
    def get(self, request, course_id):
        try:
            user = request.user
            
            try:
                course = Course.objects.get(id=course_id, user=user)
            except Course.DoesNotExist:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Course not found'
                }, status=404)
            
            # Get course progress
            course_progress, _ = CourseProgress.objects.get_or_create(
                user=user,
                course=course
            )
            
            # Get file progress
            file_progress_list = FileProgress.objects.filter(
                user=user,
                uploaded_file__course=course
            ).values(
                'id',
                'uploaded_file__id',
                'uploaded_file__filename',
                'read_percentage',
                'is_completed',
                'total_read_time_minutes'
            )
            
            return JsonResponse({
                'status': 'success',
                'data': {
                    'course_progress': {
                        'progress_percentage': course_progress.progress_percentage,
                        'completed_files': course_progress.completed_files,
                        'total_files': course_progress.total_files,
                        'status': course_progress.status,
                        'time_spent_minutes': course_progress.time_spent_minutes
                    },
                    'file_progress': list(file_progress_list)
                }
            })
        
        except Exception as e:
            print(f"[ERROR] Get progress error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
        
class CourseFilesView(LoginRequiredMixin, View):
    def get(self, request, course_id):
        try:
            user = request.user
            course = Course.objects.get(id=course_id, user=user)
            from .models import UploadedFile

            files = UploadedFile.objects.filter(
                user=user,
                course=course,
                is_deleted=False
            ).values('id', 'filename', 'file_size', 'uploaded_at')

            return JsonResponse({
                'status': 'success',
                'data': list(files)
            })
        except Course.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Course not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
