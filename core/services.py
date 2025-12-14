import google.generativeai as genai
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json
import time
import re
import os

# Configure API Key from settings.py
genai.configure(api_key=settings.GOOGLE_API_KEY)

class GeminiService:
    def __init__(self):
        # Using Gemini 2.0 Flash (adjust based on availability, e.g., gemini-1.5-flash)
        self.model_name = "gemini-2.5-flash" 
        self.model = genai.GenerativeModel(self.model_name)

    def upload_file_stateless(self, filepath, mimetype='application/pdf'):
        """
        Uploads a file to Gemini File API with retry logic.
        Returns: {'resource_name': str, 'uri': str, 'file_path': str} or None on error
        """
        try:
            print(f"[DEBUG] Uploading file: {filepath}")
            
            # Verify file exists
            if not os.path.exists(filepath):
                print(f"[ERROR] File not found: {filepath}")
                return None
            
            # Get file size
            file_size = os.path.getsize(filepath)
            print(f"[DEBUG] File size: {file_size} bytes")
            
            file_ref = genai.upload_file(filepath, mime_type=mimetype)
            print(f"[DEBUG] File uploaded, resource name: {file_ref.name}")
            
            # Wait for processing with timeout
            max_wait = 60  # seconds
            waited = 0
            while file_ref.state.name == 'PROCESSING' and waited < max_wait:
                print(f"[DEBUG] Processing... state: {file_ref.state.name}")
                time.sleep(2)
                file_ref = genai.get_file(file_ref.name)
                waited += 2
            
            print(f"[DEBUG] Final state: {file_ref.state.name}")
            
            if file_ref.state.name == 'FAILED':
                print(f"[ERROR] Gemini processing failed")
                return None
            
            if file_ref.state.name != 'ACTIVE':
                print(f"[WARNING] File state is {file_ref.state.name}, not ACTIVE")
                return None
            
            result = {
                'resource_name': file_ref.name,
                'uri': file_ref.uri,
                'file_path': filepath,
                'filename': os.path.basename(filepath),
                'mime_type': mimetype
            }
            
            print(f"[SUCCESS] File ready: {result}")
            return result
        
        except Exception as e:
            print(f"[ERROR] Gemini Upload Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def delete_file(self, file_resource_name):
        """
        Delete a file from Gemini and local storage if needed.
        
        Args:
            file_resource_name (str): Resource name like "files/abc123xyz"
        
        Returns:
            bool: True if deleted, False otherwise
        """
        try:
            print(f"[DEBUG] Deleting file: {file_resource_name}")
            
            # Delete from Gemini API
            genai.delete_file(file_resource_name)
            print(f"[SUCCESS] File deleted from Gemini: {file_resource_name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to delete file {file_resource_name}: {str(e)}")
            return False

    def chat(self, message, file_resource_names=None):
        """
        Chat with optional file context from Gemini File API.
        
        Args:
            message (str): User question/message
            file_resource_names (list): List of Gemini file resource names (optional)
        
        Returns:
            str: Response text from the model
        """
        content_parts = []
        
        print(f"[DEBUG] Chat called with {len(file_resource_names or [])} files")
        
        # Add file references if provided
        if file_resource_names and len(file_resource_names) > 0:
            try:
                for name in file_resource_names:
                    try:
                        print(f"[DEBUG] Fetching file: {name}")
                        file_ref = genai.get_file(name)
                        
                        print(f"[DEBUG] File state: {file_ref.state.name}")
                        
                        # Check if file is actually active
                        if file_ref.state.name == 'ACTIVE':
                            content_parts.append(file_ref)
                            print(f"[SUCCESS] File added to context: {name}")
                        else:
                            print(f"[WARNING] File {name} is not active (state: {file_ref.state.name}), skipping")
                    except Exception as e:
                        print(f"[ERROR] Error retrieving file {name}: {str(e)}")
            except Exception as e:
                print(f"[ERROR] Context Error: {str(e)}")
        
        # Build prompt
        try:
            if content_parts:
                print(f"[DEBUG] Using RAG mode with {len(content_parts)} file(s)")
                
                system_msg = """You are a concise academic tutor. 
IMPORTANT RULES:
1. Answer ONLY what is asked - be specific and brief
2. Do NOT use markdown formatting (no **, #, bold, italics, lists)
3. Use plain text only - just regular paragraphs
4. Keep answers under 150 words unless more is needed
5. Base your answer primarily on the provided documents
6. If information is not in documents, you may use general knowledge"""
                
                content_parts.append(system_msg)
                content_parts.append(f"\nQuestion: {message}")
                response = self.model.generate_content(content_parts)
            else:
                print(f"[DEBUG] Using general mode (no files)")
                
                prompt = """You are a concise academic tutor. 
IMPORTANT RULES:
1. Answer ONLY what is asked - be specific and brief
2. Do NOT use markdown formatting (no **, #, bold, italics, lists)
3. Use plain text only - just regular paragraphs
4. Keep answers under 150 words unless more is needed

Question: """ + message
                response = self.model.generate_content(prompt)
            
            # Validate response
            if not response or not hasattr(response, 'text'):
                print(f"[ERROR] Invalid response object")
                return "Error: Invalid response from AI model"
            
            if not response.text or response.text.strip() == '':
                print(f"[WARNING] Empty response text")
                return "I couldn't generate a response. Please try rephrasing your question."
            
            response_text = response.text.strip()
            print(f"[DEBUG] Response length: {len(response_text)} chars")
            
            # Remove markdown formatting
            response_text = self._remove_markdown_formatting(response_text)
            
            return response_text
        
        except Exception as e:
            print(f"[ERROR] Gemini Chat Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"Error: {str(e)}"
        
    def _remove_markdown_formatting(self, text):
        """
        Remove markdown formatting from text.
        Converts markdown to plain text.
        """
        import re
        
        # Remove bold (**text** or __text__)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'__(.*?)__', r'\1', text)
        
        # Remove italic (*text* or _text_)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'_(.*?)_', r'\1', text)
        
        # Remove markdown headings (# ## ### etc)
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        
        # Remove inline code backticks (`code`)
        text = re.sub(r'`(.*?)`', r'\1', text)
        
        # Remove code blocks (```code```)
        text = re.sub(r'```(.*?)```', r'\1', text, flags=re.DOTALL)
        
        # Remove numbered lists
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Remove bullet points
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        
        # Remove link formatting [text](url)
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1', text)
        
        # Clean up excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        
        return text


    def generate_quiz(self, file_resource_names, num_questions=5,
                  course_name=None, semester=None, context_text=None):
        """
        Generate quiz questions from files or general knowledge.
        Robust JSON extraction handles markdown fences and extra text.
        """
        content_parts = []
        print(f"[DEBUG] Generate quiz with {len(file_resource_names or [])} files")

        # Add files if provided
        if file_resource_names:
            try:
                for name in file_resource_names:
                    file_ref = genai.get_file(name)
                    if file_ref.state.name == 'ACTIVE':
                        content_parts.append(file_ref)
                        print(f"[DEBUG] File added to quiz context: {name}")
            except Exception as e:
                print(f"[ERROR] Quiz file error: {str(e)}")

        # Build prompt based on whether we have files
        if content_parts:
            prompt = f"""
    Generate {num_questions} multiple choice questions strictly based on the provided documents.

    If you infer a topic, keep ALL questions focused only on that topic.

    Return ONLY raw JSON (no markdown).

    Format: [{{"q": "Question text", "options": ["A","B","C","D"], "correct": 0}}]

    "correct" is the index 0-3 of the options array.

    Make questions challenging and test conceptual understanding.
    """
        else:
            # Use course metadata + recent conversation as soft context
            cn = course_name or "this course"
            sem = semester or ""
            sem_str = f" (Semester {sem})" if sem else ""
            ctx = context_text or ""

            prompt = f"""
    You are generating an MCQ quiz for a university-level course {cn}{sem_str}.

    Student's recent messages (topic focus):

    \"\"\"{ctx}\"\"\"

    Generate {num_questions} multiple choice questions that stay ON TOPIC with the above context and typical syllabus of this course and semester.

    Return ONLY raw JSON (no markdown).

    Format: [{{"q": "Question text", "options": ["A","B","C","D"], "correct": 0}}]

    - "correct" is the index 0-3 of the correct option.
    - Randomize questions and correct options.
    - Do NOT mix in unrelated subjects.
    """

        content_parts.append(prompt)

        try:
            print(f"[DEBUG] Calling model for quiz generation")
            response = self.model.generate_content(content_parts)
            
            raw_response = response.text or ""
            print(f"[DEBUG] Raw response (first 300 chars): {raw_response[:300]}")
            
            # Remove markdown fences
            raw_response = raw_response.replace("```json", "").replace("```", "").strip()
            
            # Extract JSON array using regex
            # This pattern matches [...] with any content inside, including nested objects/arrays
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', raw_response)
            
            if not json_match:
                print(f"[ERROR] No JSON array found in response")
                print(f"[DEBUG] Full response after fence removal: {raw_response}")
                return None
            
            clean_text = json_match.group(0)
            print(f"[DEBUG] Extracted JSON (first 150 chars): {clean_text[:150]}")
            
            # Parse JSON
            quiz_data = json.loads(clean_text)
            
            # Validate structure
            if not isinstance(quiz_data, list) or len(quiz_data) == 0:
                print(f"[ERROR] Extracted JSON is not a non-empty list")
                return None
            
            print(f"[SUCCESS] Generated {len(quiz_data)} quiz questions")
            return quiz_data
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse error: {str(e)}")
            print(f"[DEBUG] Failed text: {clean_text[:500]}")
            return None
        except Exception as e:
            msg = str(e).lower()
            print(f"[ERROR] generate_quiz exception: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # SHORTEN QUOTA ERRORS
            if any(keyword in msg for keyword in ["quota", "429", "resource_exhausted"]):
                return {"_error": "quota_exceeded"}
            
            return None


        

def update_user_stats_on_chat(user, course):
    """
    Update user statistics when they chat with the AI.
    """
    try:
        from .models import UserStats, RetentionMetric
        
        # Get or create user stats
        user_stats, created = UserStats.objects.get_or_create(user=user)
        
        # Update last activity
        user_stats.last_activity_date = timezone.now()
        
        # Update streak
        today = timezone.now().date()
        last_activity = user_stats.last_activity_date.date() if user_stats.last_activity_date else None
        
        if last_activity == today:
            pass
        elif last_activity == today - timedelta(days=1):
            user_stats.current_streak += 1
        else:
            user_stats.current_streak = 1
        
        user_stats.save()
        print(f"[SUCCESS] Updated stats for {user.username}: Streak={user_stats.current_streak}")
        
        # Create retention metric
        today_metric = RetentionMetric.objects.filter(
            user=user,
            date=today
        ).first()
        
        if today_metric:
            today_metric.score = min(100, today_metric.score + 5)
            today_metric.save()
        else:
            RetentionMetric.objects.create(
                user=user,
                date=today,
                score=15
            )
        
    except Exception as e:
        print(f"[ERROR] Error updating user stats: {str(e)}")


def calculate_knowledge_mastery(user, course):
    """
    Calculate knowledge mastery percentage
    """
    try:
        from .models import ChatMessage, RetentionMetric
        
        chat_count = ChatMessage.objects.filter(
            user=user,
            course=course,
            role='user'
        ).count()
        
        chat_score = min(30, chat_count * 10)
        
        seven_days_ago = timezone.now().date() - timedelta(days=7)
        retention_records = RetentionMetric.objects.filter(
            user=user,
            date__gte=seven_days_ago
        )
        
        if retention_records.exists():
            avg_retention = retention_records.aggregate(
                avg_score=__import__('django.db.models', fromlist=['Avg']).Avg('score')
            )['avg_score'] or 0
            retention_score = min(30, int(avg_retention * 0.3))
        else:
            retention_score = 0
        
        quiz_score = 0
        total_mastery = chat_score + retention_score + quiz_score
        
        return min(100, int(total_mastery))
        
    except Exception as e:
        print(f"[ERROR] Error calculating mastery: {str(e)}")
        return 0