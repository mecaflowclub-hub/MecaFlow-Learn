from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Body, File, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from schemas import (
    UpdateProfileRequest, UpdateProfileResponse, RegisterWithCodeRequest,
    UserCreate, UserLogin, ExerciseCreate, CourseCreate, Token, TokenRefreshRequest,
    UserResponse, AdminRegisterRequest, BulkRegisterRequest
)
from auth import (
    authenticate_user, create_access_token, get_current_user, require_teacher_or_admin,
    require_admin, get_password_hash, create_refresh_token, verify_refresh_token,
    verify_password, pwd_context
)
from database import init_db, users_collection, exercises_collection, submissions_collection, courses_collection
from services.occComparison import compare_models
from utils.email_utils import send_verification_code
import random
import os
import shutil
import uuid
import json
import tempfile
import logging
from enum import Enum

# =============================================================================
# INITIALISATION
# =============================================================================
app = FastAPI(
    title="CAD Platform API",
    description="API pour la plateforme d'exercices CAD",
    version="1.0.0"
)

class PathNormalizationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Normalize path by removing double slashes and ensuring single leading slash
            path = scope["path"]
            normalized_path = "/" + "/".join(filter(None, path.split("/")))
            scope["path"] = normalized_path
        await self.app(scope, receive, send)

app.add_middleware(PathNormalizationMiddleware)

@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    for attempt in range(3):
        try:
            await init_db()
            logging.info("Database initialized successfully")
            return
        except Exception as e:
            if attempt == 2:  # Last attempt
                logging.error(f"Failed to initialize database: {str(e)}")
                raise RuntimeError(f"Could not initialize database: {str(e)}")
            else:
                logging.warning(f"Database initialization attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(5)

@app.get("/api/health")
async def health_check():
    if users_collection is None:
        return {"status": "starting", "reason": "database initializing"}
    try:
        await users_collection.find_one({})
        return {"status": "healthy"}
    except Exception as e:
        logging.error(f"Health check failed: {str(e)}")
        return {"status": "unhealthy", "reason": str(e)}

# Middleware CORS
origins = os.getenv("CORS_ORIGINS", "*").split(",")
if "*" not in origins:
    # Add common development and production URLs if not using wildcard
    origins.extend([
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://mecaflow-backend.onrender.com"
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Setup CORS and security
security = HTTPBearer()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("cad-platform")

security = HTTPBearer()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("cad-platform")

# =============================================================================
# HELPERS
# =============================================================================
def to_objectid(val: Any) -> Optional[ObjectId]:
    """Try to convert a value to ObjectId, else return None."""
    if not val:
        return None
    try:
        if isinstance(val, ObjectId):
            return val
        if isinstance(val, dict):
            val = val.get('$oid', val)
        if isinstance(val, str):
            return ObjectId(val)
        return ObjectId(str(val))
    except Exception as e:
        logger.error(f"Failed to convert to ObjectId: {val} (type: {type(val)})")
        logger.error(f"Error: {str(e)}")
        return None

def serialize_doc(doc: Any) -> Any:
    """Convert ObjectId recursively to str. If doc is None, return None."""
    if doc is None:
        return None

    def convert(value):
        if isinstance(value, ObjectId):
            return str(value)
        elif isinstance(value, list):
            return [convert(v) for v in value]
        elif isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        else:
            return value
    return convert(doc)

# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

@app.post("/api/auth/admin-register")
async def admin_register(user: AdminRegisterRequest, current_user: dict = Depends(require_teacher_or_admin)):
    """Allow teachers and admins to register new users directly without email verification."""
    logger.info(f"Admin registration by {current_user.get('email')} for new user: {user.email}")

    # Check if user already exists
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user and existing_user.get("is_verified"):
        raise HTTPException(status_code=400, detail="User already exists")

    # Create new user document
    user_dict = user.dict(exclude_unset=True)
    user_dict["password"] = get_password_hash(user.password)
    user_dict["is_verified"] = True  # Auto-verify since admin is creating
    user_dict["progress"] = {}
    user_dict["completedExercises"] = []
    user_dict["scores"] = []
    user_dict["createdAt"] = datetime.utcnow()
    user_dict["updatedAt"] = datetime.utcnow()
    user_dict["__v"] = 0

    # Set default role if not provided
    if "role" not in user_dict or not user_dict["role"]:
        user_dict["role"] = "student"

    # Insert new user
    result = await users_collection.insert_one(user_dict)
    user_dict["_id"] = str(result.inserted_id)

    logger.info(f"User {user.email} registered successfully by admin {current_user.get('email')}")
    return {
        "success": True,
        "message": f"User {user.email} registered successfully",
        "user": serialize_doc(user_dict)
    }

@app.post("/api/auth/admin-register-bulk")
async def admin_register_bulk(request: BulkRegisterRequest, current_user: dict = Depends(require_teacher_or_admin)):
    """Allow teachers and admins to register multiple users at once."""
    logger.info(f"Bulk registration by {current_user.get('email')} for {len(request.users)} users")
    
    results = []
    errors = []
    
    for user in request.users:
        try:
            # Check if user exists
            existing_user = await users_collection.find_one({"email": user.email})
            if existing_user and existing_user.get("is_verified"):
                errors.append({"email": user.email, "error": "User already exists"})
                continue

            # Create user document
            user_dict = user.dict(exclude_unset=False)  # Include all fields, even if not set
            user_dict["password"] = get_password_hash(user.password)
            user_dict["is_verified"] = True
            user_dict["progress"] = {}
            user_dict["completedExercises"] = []
            user_dict["scores"] = []
            user_dict["createdAt"] = datetime.utcnow()
            user_dict["updatedAt"] = datetime.utcnow()
            user_dict["__v"] = 0
            # Role will already be set to "student" by default through the schema

            # Insert user
            result = await users_collection.insert_one(user_dict)
            user_dict["_id"] = str(result.inserted_id)
            results.append(serialize_doc(user_dict))
            
        except Exception as e:
            errors.append({"email": user.email, "error": str(e)})

    return {
        "success": True,
        "registered_users": results,
        "errors": errors,
        "total_success": len(results),
        "total_errors": len(errors)
    }

# =============================================================================
# TEST ENDPOINTS
# =============================================================================

@app.post("/api/auth/test-password")
async def test_password_hash(password: str = Body(...)):
    """Test endpoint to verify password hashing"""
    hashed = pwd_context.hash(password)
    verify_result = pwd_context.verify(password, hashed)
    # Also hash a second time to show how bcrypt creates different hashes
    second_hash = pwd_context.hash(password)
    second_verify = pwd_context.verify(password, second_hash)
    
    logger.info("Password hash test:")
    logger.info(f"Original password: {password}")
    logger.info(f"First hash: {hashed}")
    logger.info(f"Second hash: {second_hash}")
    logger.info(f"First hash verification: {verify_result}")
    logger.info(f"Second hash verification: {second_verify}")
    logger.info(f"Cross verification (first hash with second verify): {pwd_context.verify(password, hashed)}")
    
    return {
        "original": password,
        "first_hash": hashed,
        "second_hash": second_hash,
        "first_verify": verify_result,
        "second_verify": second_verify,
        "hashes_are_different": hashed != second_hash,
        "both_verify": verify_result and second_verify
    }

# =============================================================================
# UPDATE PROFILE ENDPOINT
# =============================================================================

@app.patch("/api/auth/update-profile", response_model=UpdateProfileResponse)
async def update_profile(payload: UpdateProfileRequest = Body(...), current_user: dict = Depends(get_current_user)):
    # -- Basic auth / id extraction --
    user_id = current_user.get("_id") or current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    uid_obj = to_objectid(user_id)
    if not uid_obj:
        raise HTTPException(status_code=400, detail="Invalid user id")
    logger.info(f"Update profile - User ID type={type(user_id)}, value={repr(user_id)}, ObjectId={uid_obj}")

    # Load current user from DB (fresh)
    db_user = await users_collection.find_one({"_id": uid_obj})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info(f"Found user in DB: id={db_user.get('_id')}")

    update_fields = {}
    if payload.name:
        update_fields["name"] = payload.name
    update_fields["updatedAt"] = datetime.utcnow()

    # Handle password change if requested
    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="Current password required to change password")
        
        stored_password = db_user.get("password", "")
        logger.info(f"Password update requested - Current hash in DB: {stored_password}")
        
        # verify current password
        if not pwd_context.verify(payload.current_password, stored_password):
            logger.warning("Password update failed - Current password verification failed")
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        logger.info("Current password verified successfully")
        
        # ensure new != current
        if pwd_context.verify(payload.new_password, stored_password):
            logger.warning("Password update failed - New password same as current")
            raise HTTPException(status_code=400, detail="New password must be different from current password")
            
        # hash and set new password
        new_hashed = pwd_context.hash(payload.new_password)
        update_fields["password"] = new_hashed
        logger.info(f"Generated new password hash: {new_hashed}")
        
        # Verify the new hash works before saving
        verify_test = pwd_context.verify(payload.new_password, new_hashed)
        if not verify_test:
            logger.error("Password update failed - New hash verification failed")
            raise HTTPException(status_code=500, detail="Generated password hash verification failed")
        logger.info("New password hash verified successfully")

    # Perform update
    if update_fields:
        logger.info(f"Updating user {uid_obj} with fields: {list(update_fields.keys())}")
        result = await users_collection.update_one(
            {"_id": uid_obj},
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            logger.error(f"Update failed - No user matched ID {uid_obj}")
            raise HTTPException(status_code=404, detail="User not found")
            
        if result.modified_count == 0:
            logger.warning("Update returned 0 modified documents")
            # Don't raise error here - it could mean no changes were needed
    
    # Get updated user document
    updated_user = await users_collection.find_one({"_id": uid_obj})
    if not updated_user:
        logger.error("Failed to fetch user after update")
        raise HTTPException(status_code=500, detail="Failed to verify update")
    
    # Verify password change if requested
    if payload.new_password:
        new_stored_hash = updated_user.get("password", "")
        logger.info(f"Verifying password update - New hash in DB: {new_stored_hash}")
        if new_stored_hash != new_hashed:
            logger.error("Password update verification failed - Hash mismatch")
            logger.error(f"Expected: {new_hashed}")
            logger.error(f"Found in DB: {new_stored_hash}")
            raise HTTPException(status_code=500, detail="Password update verification failed")
        
        verify_final = pwd_context.verify(payload.new_password, new_stored_hash)
        if not verify_final:
            logger.error("Password update verification failed - Cannot verify with new password")
            raise HTTPException(status_code=500, detail="Password update verification failed")
        logger.info("Password update verified successfully")

    return UpdateProfileResponse(
        success=True,
        user=serialize_doc(updated_user),
        message="Profile and password updated successfully" if "password" in update_fields else "Profile updated successfully"
    )

security = HTTPBearer()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("cad-platform")

# =============================================================================
# AUTHENTIFICATION
# =============================================================================

# =============================================================================
# AUTHENTIFICATION
# =============================================================================
class SendCodeRequest(BaseModel):
    email: str

@app.post("/api/auth/send-code")
async def send_code(payload: SendCodeRequest = Body(...)):
    email = payload.email
    existing = await users_collection.find_one({"email": email})
    if existing and existing.get("is_verified"):
        raise HTTPException(status_code=400, detail="Email already registered and verified.")

    code = str(random.randint(100000, 999999))
    expires = datetime.utcnow() + timedelta(minutes=10)

    # Upsert minimal user document with verification fields if not exists
    await users_collection.update_one(
        {"email": email},
        {"$set": {
            "verification_code": code,
            "code_expires_at": expires,
            "is_verified": False,
            "updatedAt": datetime.utcnow()
        },
         "$setOnInsert": {"createdAt": datetime.utcnow(), "progress": {}, "completedExercises": [], "scores": []}
        },
        upsert=True
    )
    try:
        send_verification_code(email, code)
        return {"success": True, "message": "A 6-digit code has been sent to your email."}
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi du code de vérification: {e}")
        # Retourner plus de détails sur l'erreur pour le débogage
        error_message = str(e) if not isinstance(e, ValueError) else e.args[0]
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Failed to send code",
                "error": error_message
            }
        )

@app.post("/api/auth/register")
async def register(user: RegisterWithCodeRequest = Body(...)):
    logger.info(f"Nouvel enregistrement utilisateur: {user.email}")

    db_user = await users_collection.find_one({"email": user.email})
    if not db_user or not db_user.get("verification_code"):
        raise HTTPException(status_code=400, detail="No code sent to this email. Please request a code first.")
    if db_user.get("is_verified"):
        raise HTTPException(status_code=400, detail="User already registered and verified.")
    if db_user.get("verification_code") != user.code:
        raise HTTPException(status_code=400, detail="Invalid verification code.")
    if db_user.get("code_expires_at") and datetime.utcnow() > db_user["code_expires_at"]:
        raise HTTPException(status_code=400, detail="Verification code expired.")

    user_dict = user.dict(exclude={"code"})
    # default role if not provided
    if "role" not in user_dict or not user_dict["role"]:
        user_dict["role"] = "student"

    user_dict["password"] = get_password_hash(user.password)
    user_dict["progress"] = db_user.get("progress", {})
    user_dict["completedExercises"] = db_user.get("completedExercises", [])
    user_dict["scores"] = db_user.get("scores", [])
    user_dict["createdAt"] = db_user.get("createdAt", datetime.utcnow())
    user_dict["updatedAt"] = datetime.utcnow()
    user_dict["__v"] = 0
    user_dict["is_verified"] = True
    # remove temporary code fields if present
    user_dict.pop("verification_code", None)
    user_dict.pop("code_expires_at", None)

    await users_collection.replace_one({"email": user.email}, user_dict, upsert=True)

    # Respond with token + user
    token = create_access_token(data={"sub": user.email})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": serialize_doc(user_dict)
    }

class EmailCodeVerifyRequest(BaseModel):
    email: EmailStr
    code: str

@app.post("/api/auth/verify-code")
async def verify_email_code(payload: EmailCodeVerifyRequest = Body(...)):
    user = await users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("is_verified"):
        return {"success": True, "message": "User already verified."}
    if user.get("verification_code") != payload.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    if user.get("code_expires_at") and datetime.utcnow() > user["code_expires_at"]:
        raise HTTPException(status_code=400, detail="Verification code expired")

    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"is_verified": True, "updatedAt": datetime.utcnow()},
         "$unset": {"verification_code": "", "code_expires_at": ""}}
    )
    return {"success": True, "message": "Email verified successfully."}

@app.post("/api/auth/login")
async def login(user: UserLogin = Body(...)):
    logger.info(f"Tentative de connexion: {user.email}")
    print(f"Debug - Login attempt:")
    print(f"- Email: {user.email}")
    
    # Get the user first to do some debug checks
    db_user_check = await users_collection.find_one({"email": user.email})
    if db_user_check:
        stored_password = db_user_check.get("password", "")
        print(f"- Found user with stored password hash: {stored_password}")
        # Try direct password verification
        direct_verify = pwd_context.verify(user.password, stored_password)
        print(f"- Direct password verification result: {direct_verify}")
    else:
        print("- No user found with this email")
    
    db_user = await authenticate_user(user.email, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    token = create_access_token(data={"sub": db_user["email"]})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": serialize_doc(db_user)
    }

@app.post("/api/auth/refresh-token", response_model=Token)
async def refresh_token(payload: TokenRefreshRequest):
    user_email = verify_refresh_token(payload.refresh_token)
    if not user_email:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    access_token = create_access_token(data={"sub": user_email})
    refresh_token = create_refresh_token(data={"sub": user_email})
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer"
    )

@app.get("/api/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    logger.info(f"Profil demandé pour utilisateur: {current_user.get('email')}")
    user = serialize_doc(current_user)

    # Ensure scores is a list
    scores = user.get("scores", [])
    if not isinstance(scores, list):
        scores = []

    total_score = sum([s.get("score", 0) for s in scores if isinstance(s, dict)])

    if total_score < 1000:
        rank = "bronze"
    elif total_score < 2000:
        rank = "silver"
    elif total_score < 3500:
        rank = "gold"
    elif total_score < 5200:
        rank = "platinum"
    else:
        rank = "diamond"

    user["total_score"] = total_score
    user["rank"] = rank
    return {"success": True, "user": user}

# =============================================================================
# USERS (ADMIN / TEACHER)
# =============================================================================
@app.get("/api/users")
async def list_users(current_user: dict = Depends(require_teacher_or_admin)):
    users = []
    cursor = users_collection.find()
    async for user in cursor:
        users.append(serialize_doc(user))
    return {"success": True, "users": users}

# =============================================================================
# COURSES (CRUD)
# =============================================================================
@app.post("/api/courses")
async def create_course(course: CourseCreate, current_user: dict = Depends(require_teacher_or_admin)):
    course_dict = course.dict(exclude_unset=True)
    course_dict["createdAt"] = datetime.utcnow()
    course_dict["updatedAt"] = datetime.utcnow()
    result = await courses_collection.insert_one(course_dict)
    course_dict["_id"] = str(result.inserted_id)
    return {"success": True, "course": serialize_doc(course_dict)}

@app.post("/api/courses/bulk")
async def create_courses_bulk(
    courses: List[CourseCreate],
    current_user: dict = Depends(require_teacher_or_admin)
):
    now = datetime.utcnow()
    course_dicts = []
    for course in courses:
        c = course.dict(exclude_unset=True)
        c["createdAt"] = now
        c["updatedAt"] = now
        course_dicts.append(c)
    result = await courses_collection.insert_many(course_dicts)
    for i, _id in enumerate(result.inserted_ids):
        course_dicts[i]["_id"] = str(_id)
    return {"success": True, "courses": [serialize_doc(c) for c in course_dicts]}

@app.get("/api/courses")
async def list_courses():
    courses = []
    # Sort courses by level (beginner -> intermediate -> advanced) and creation date
    level_order = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3
    }
    pipeline = [
        {"$addFields": {"level_order": {"$switch": {"branches": [
            {"case": {"$eq": ["$level", "beginner"]}, "then": 1},
            {"case": {"$eq": ["$level", "intermediate"]}, "then": 2},
            {"case": {"$eq": ["$level", "advanced"]}, "then": 3}
        ], "default": 4}}}},
        {"$sort": {"level_order": 1, "createdAt": 1}},
        {"$project": {"level_order": 0}}  # Remove the temporary field
    ]
    cursor = courses_collection.aggregate(pipeline)
    async for course in cursor:
        course_data = serialize_doc(course)
        # Get exercises for this course
        exercises = []
        ex_cursor = exercises_collection.find({
            "course_id": str(course["_id"]),
            "is_active": True
        }).sort([("order", 1), ("createdAt", 1)])
        async for ex in ex_cursor:
            exercises.append(serialize_doc(ex))
        course_data["exercises"] = exercises
        courses.append(course_data)
    return {"success": True, "courses": courses}

@app.get("/api/courses/{course_id}")
async def get_course(course_id: str):
    obj = to_objectid(course_id)
    if not obj:
        raise HTTPException(status_code=400, detail="Invalid course id")
    
    # Get course details
    course = await courses_collection.find_one({"_id": obj})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Get exercises for this course
    exercises = []
    cursor = exercises_collection.find({
        "course_id": str(course["_id"]),
        "is_active": True
    }).sort([("order", 1), ("createdAt", 1)])
    
    async for ex in cursor:
        exercises.append(serialize_doc(ex))
    
    course_data = serialize_doc(course)
    course_data["exercises"] = exercises
    
    return {"success": True, "course": course_data}

@app.put("/api/courses/{course_id}")
async def update_course(course_id: str, course: CourseCreate, current_user: dict = Depends(require_teacher_or_admin)):
    obj = to_objectid(course_id)
    if not obj:
        raise HTTPException(status_code=400, detail="Invalid course id")
    course_dict = course.dict(exclude_unset=True)
    course_dict["updatedAt"] = datetime.utcnow()
    result = await courses_collection.update_one({"_id": obj}, {"$set": course_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"success": True}

@app.delete("/api/courses/{course_id}")
async def delete_course(course_id: str, current_user: dict = Depends(require_admin)):
    obj = to_objectid(course_id)
    if not obj:
        raise HTTPException(status_code=400, detail="Invalid course id")
    result = await courses_collection.delete_one({"_id": obj})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"success": True}

# =============================================================================
# EXERCISES
# =============================================================================

@app.get("/api/courses/{course_id}/exercises")
async def get_course_exercises(course_id: str):
    obj = to_objectid(course_id)
    if not obj:
        raise HTTPException(status_code=400, detail="Invalid course id")
        
    # Verify course exists
    course = await courses_collection.find_one({"_id": obj})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Get exercises for this course
    exercises = []
    cursor = exercises_collection.find({
        "course_id": str(obj),
        "is_active": True
    }).sort([("order", 1), ("createdAt", 1)])
    
    async for ex in cursor:
        exercises.append(serialize_doc(ex))
    
    return {"success": True, "exercises": exercises}

@app.get("/api/exercises")
async def list_exercises(skip: int = Query(0), limit: int = Query(100), course_id: Optional[str] = None):
    # Create base query without is_active filter first to see all exercises
    query = {}
    if course_id:
        query["course_id"] = course_id
        
    exercises = []
    # Sort exercises by order field first, then by creation date
    cursor = exercises_collection.find(query).sort([
        ("order", 1),  # Primary sort by explicit order
        ("createdAt", 1)  # Secondary sort by creation date
    ]).skip(skip).limit(limit)
    
    async for ex in cursor:
        exercises.append(serialize_doc(ex))
    return {"success": True, "exercises": exercises}

@app.post("/api/exercises")
async def create_exercise_api(exercise: ExerciseCreate, current_user: dict = Depends(require_teacher_or_admin)):
    ex_dict = exercise.dict(exclude_unset=True)
    ex_dict["createdAt"] = datetime.utcnow()
    ex_dict["updatedAt"] = datetime.utcnow()
    
    # store creator id as string
    ex_dict["created_by"] = str(current_user.get("_id", current_user.get("id", "")))
    
    # Validate course exists if course_id is provided
    course_id = ex_dict.get("course_id")
    if course_id:
        course_obj = to_objectid(course_id)
        if not course_obj:
            raise HTTPException(status_code=400, detail="Invalid course_id format")
        
        course = await courses_collection.find_one({"_id": course_obj})
        if not course:
            raise HTTPException(status_code=400, detail="Course not found")
            
    # Set the order for the exercise
    if "order" not in ex_dict:
        # Find the last exercise in the same course (or no course)
        query = {"course_id": course_id} if course_id else {"course_id": None}
        last_exercise = await exercises_collection.find_one(
            query,
            sort=[("order", -1)]
        )
        # Set order as last + 1, or 1 if no exercises exist
        ex_dict["order"] = (last_exercise["order"] + 1) if last_exercise else 1
        if not course_obj or not await courses_collection.find_one({"_id": course_obj}):
            raise HTTPException(status_code=400, detail="Invalid course_id")
            
        # Get highest order number for this course and increment by 1
        last_exercise = await exercises_collection.find_one(
            {"course_id": course_id, "is_active": True},
            sort=[("order", -1)]
        )
        ex_dict["order"] = (last_exercise.get("order", 0) if last_exercise else 0) + 1
    else:
        # If no course_id, this is a standalone exercise
        ex_dict["order"] = 1
    
    # Ensure exercise is active by default
    ex_dict["is_active"] = ex_dict.get("is_active", True)
    
    # Enum -> str if necessary
    diff = ex_dict.get("difficulty")
    if diff is not None and hasattr(diff, "value"):
        ex_dict["difficulty"] = diff.value
    result = await exercises_collection.insert_one(ex_dict)
    ex_dict["_id"] = str(result.inserted_id)
    return {"success": True, "exercise": serialize_doc(ex_dict)}

@app.post("/api/exercises/bulk")
async def create_exercises_bulk(
    exercises: List[ExerciseCreate],
    current_user: dict = Depends(require_teacher_or_admin)
):
    now = datetime.utcnow()
    exercise_dicts = []
    for exercise in exercises:
        ex = exercise.dict(exclude_unset=True)
        ex["createdAt"] = now
        ex["updatedAt"] = now
        ex["created_by"] = str(current_user.get("_id", current_user.get("id", "")))
        diff = ex.get("difficulty")
        if diff is not None and hasattr(diff, "value"):
            ex["difficulty"] = diff.value
        exercise_dicts.append(ex)
    result = await exercises_collection.insert_many(exercise_dicts)
    for i, _id in enumerate(result.inserted_ids):
        exercise_dicts[i]["_id"] = str(_id)
    return {"success": True, "exercises": [serialize_doc(e) for e in exercise_dicts]}

@app.post("/api/exercises/{exercise_id}/upload-reference")
async def upload_reference_step(
    exercise_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_teacher_or_admin)
):
    obj = to_objectid(exercise_id)
    if not obj:
        raise HTTPException(status_code=400, detail="Invalid exercise id")
    ex = await exercises_collection.find_one({"_id": obj})
    if not ex:
        raise HTTPException(status_code=404, detail="Exercice non trouvé")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    ext = os.path.splitext(str(file.filename))[1].lower()
    if ext != ".step":
        raise HTTPException(status_code=400, detail="Seuls les fichiers .step sont autorisés")

    ref_dir = os.path.join(UPLOAD_DIR, "reference-files")
    os.makedirs(ref_dir, exist_ok=True)
    ref_filename = f"ex_{exercise_id}.step"
    ref_path = os.path.join(ref_dir, ref_filename)
    with open(ref_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    await exercises_collection.update_one(
        {"_id": obj},
        {"$set": {"solution_file_path": ref_path, "updatedAt": datetime.utcnow()}}
    )

    return {"success": True, "solution_file_path": ref_path}

# =============================================================================
# SUBMISSIONS
# =============================================================================
from fastapi import Form
import json

# QCM scoring logic
def calculate_qcm_score(quiz_answers, qcm):
    if not quiz_answers or not qcm:
        return 0, 0, 0
    total_questions = len(qcm)
    correct_count = 0
    for idx, question in enumerate(qcm):
        correct = set(question.get("answers", []))
        user_ans = set(quiz_answers.get(str(idx), []))
        if not correct:
            continue
        if correct == user_ans:
            correct_count += 1
    # QCM score is proportional: 10 * (correct_count / total_questions)
    qcm_score = round(10 * (correct_count / total_questions), 2) if total_questions > 0 else 0
    return qcm_score, correct_count, total_questions

@app.post("/api/exercises/{exercise_id}/submit")
async def submit_exercise(
    exercise_id: str,
    file: UploadFile = File(...),
    quizAnswers: Optional[str] = Form(None),
    user_feedback: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    logger.info(f"Soumission exercice {exercise_id} par utilisateur {current_user.get('email')}")
    ex_obj = to_objectid(exercise_id)
    if not ex_obj:
        ex = await exercises_collection.find_one({"_id": exercise_id})
    else:
        ex = await exercises_collection.find_one({"_id": ex_obj})
    if not ex:
        raise HTTPException(status_code=404, detail="Exercice non trouvé")

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    # get size safely
    content = await file.read()
    size = len(content)
    if size > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 50MB)")

    # write file to disk later when we know path
    course_id_raw = ex.get("course_id")
    course_obj = to_objectid(course_id_raw)
    if course_obj:
        course = await courses_collection.find_one({"_id": course_obj})
    else:
        # if course_id stored as string or missing
        course = await courses_collection.find_one({"_id": course_id_raw}) if course_id_raw else None
    level = course.get("level") if course else "unknown"
    order = ex.get("order")

    # --- Special case: Exercise 2 (Bottle) ---
    if order == 2:
        if ext not in [".stp", ".step"]:
            raise HTTPException(status_code=400, detail="Seuls les fichiers STEP sont autorisés pour cet exercice.")
            
        # Save file with original extension preserved
        file_id = str(uuid.uuid4())
        path = os.path.join(UPLOAD_DIR, "student-files", f"{file_id}_{filename}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as buffer:
            buffer.write(content)
        
        reference_filename = ex.get("solution_file_path")
        if not reference_filename:
            cad_result = {"success": False, "error": "Chemin de référence non défini"}
        else:
            reference_path = os.path.join(UPLOAD_DIR, "reference-files", os.path.basename(reference_filename))
            logger.info(f"Comparing bottle files:")
            logger.info(f"Student: {path}")
            logger.info(f"Reference: {reference_path}")
            
            if not os.path.exists(reference_path):
                cad_result = {
                    "success": False,
                    "error": "Fichier de référence introuvable",
                    "details": f"Le fichier {reference_path} n'existe pas"
                }
            else:
                try:
                    from services.occComparison import compare_models
                    cad_result = compare_models(path, reference_path)
                    logger.info(f"Bottle comparison result: {json.dumps(cad_result, indent=2)}")
                except Exception as e:
                    logger.error(f"Error during bottle comparison: {str(e)}")
                    cad_result = {
                        "success": False,
                        "error": f"Erreur lors de la comparaison: {str(e)}"
                    }

    # --- Special case: Exo 11 (advanced, DXF drawing) ---
    elif level == "advanced" and order == 11:
        if ext != ".dxf":
            raise HTTPException(status_code=400, detail="Seuls les fichiers DXF sont autorisés pour cet exercice.")
        file_id = str(uuid.uuid4())
        path = os.path.join(UPLOAD_DIR, "drawings", f"{file_id}_{filename}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as buffer:
            buffer.write(content)

        reference_filename = ex.get("solution_file_path")
        if not reference_filename:
            cad_result = {"success": False, "error": "Chemin de référence non défini"}
        else:
            # Normalize path - ensure it's relative to the backend root
            reference_filename = reference_filename.lstrip('/')
            reference_path = os.path.join(UPLOAD_DIR, "drawings", os.path.basename(reference_filename))
            
            logger.info(f"Checking DXF reference file at: {reference_path}")
            
            if not os.path.exists(reference_path):
                cad_result = {
                    "success": False, 
                    "error": "Fichier de référence introuvable",
                    "details": f"Le fichier {reference_path} n'existe pas"
                }
            else:
                try:
                    from services.occCompareDXF import compare_dxf_drawings
                    cad_result = compare_dxf_drawings(path, reference_path)
                    logger.info(f"DXF comparison result: {cad_result}")
                except Exception as e:
                    logger.error(f"Error during DXF comparison: {str(e)}")
                    cad_result = {
                        "success": False,
                        "error": f"Erreur lors de la comparaison DXF: {str(e)}"
                    }
            
            # Remove redundant check since we already handled this case above

        # QCM scoring
        quiz_answers = None
        if quizAnswers:
            try:
                quiz_answers = json.loads(quizAnswers)
                logger.info(f"Received quizAnswers: {quizAnswers}, parsed: {quiz_answers}")
            except Exception:
                quiz_answers = None
                logger.warning(f"Failed to parse quizAnswers: {quizAnswers}")
        qcm = ex.get("qcm", [])
        qcm_score, correct_count, total_questions = calculate_qcm_score(quiz_answers, qcm)

        # CAD score (out of 90)
        if isinstance(cad_result, dict):
            if "score" in cad_result:  # DXF case
                cad_score = cad_result["score"]
                # Scale DXF score from 100 to 90
                cad_score = (cad_score * 90) / 100
            else:  # STEP/assembly case
                is_assembly = ex.get("type") == "assembly"
                num_components = cad_result.get("num_components", {}).get("submitted", 1)
                if (is_assembly and num_components > 1) or (not is_assembly and num_components == 1):
                    cad_score = cad_result.get("global_score", 0)
                else:
                    error_msg = "Assembly attendu mais pièce reçue" if is_assembly else "Pièce attendue mais assembly reçu"
                    cad_score = 0
                    cad_result["error"] = error_msg
        else:
            cad_score = 0
            
        cad_score = min(cad_score, 90)
        total_score = round(cad_score + qcm_score, 2)
        feedback = f"CAD: {cad_score}/90, QCM: {qcm_score}/10 ({correct_count}/{total_questions} correct)"

        sub_dict = {
            "exercise_id": exercise_id,
            "user_id": str(current_user.get("_id", current_user.get("id"))),
            "file_name": filename,
            "file_path": path,
            "file_size": os.path.getsize(path),
            "status": "pending",
            "submitted_at": datetime.utcnow(),
            "cad_comparison": cad_result,
            "quiz_answers": quiz_answers,
            "score": total_score,
            "feedback": feedback,
            "user_feedback": user_feedback
        }

        result = await submissions_collection.insert_one(sub_dict)
        sub_dict["_id"] = str(result.inserted_id)

        # Progress/score update only if total score >= 90
        if total_score >= 90:  # Exercise is successful based on total score only
            uid_obj = to_objectid(current_user.get("_id"))
            user_filter = {"_id": uid_obj} if uid_obj else {"email": current_user.get("email")}
            await users_collection.update_one(
                user_filter,
                {"$addToSet": {"completedExercises": exercise_id}}
            )
            await users_collection.update_one(
                user_filter,
                {"$pull": {"scores": {"exercise_id": exercise_id}}}
            )
            await users_collection.update_one(
                user_filter,
                {"$push": {"scores": {"exercise_id": exercise_id, "score": total_score}}}
            )
            # Update progress
            all_ex_cursor = exercises_collection.find({"course_id": course_id_raw})
            all_ex_ids = [str(e["_id"]) async for e in all_ex_cursor]
            latest_user = await users_collection.find_one(user_filter)
            completed = set(latest_user.get("completedExercises", [])) if latest_user else set()
            completed_count = len([eid for eid in all_ex_ids if eid in completed])
            total_count = len(all_ex_ids)
            await users_collection.update_one(
                user_filter,
                {"$set": {f"progress.{level}": {"completed": completed_count, "total": total_count}}}
            )
            await users_collection.update_one(user_filter, {"$set": {"updatedAt": datetime.utcnow()}})
        return {"success": True, "submission": serialize_doc(sub_dict)}

    # --- Special case: manual validation exercises ---
    special_manual = (
        (level == "advanced" and order in [2, 6, 7, 13, 14]) or
        (level == "intermediate" and order == 18)
    )
    if special_manual:
        # Vérifier l'extension selon l'exercice
        if level == "advanced" and order == 2:
            # Pour l'exercice 2 (bouteille), uniquement SLDPRT
            if ext != ".sldprt":
                raise HTTPException(status_code=400, detail="Seuls les fichiers SLDPRT sont autorisés pour cet exercice.")
        elif level == "advanced" and order in [6, 7]:
            if ext != ".sldprt":
                raise HTTPException(status_code=400, detail="Seuls les fichiers SLDPRT sont autorisés pour cet exercice.")
        else:
            if ext != ".sldasm":
                raise HTTPException(status_code=400, detail="Seuls les fichiers SLDASM sont autorisés pour cet exercice.")
        file_id = str(uuid.uuid4())
        path = os.path.join(UPLOAD_DIR, "assemblies", f"{file_id}_{filename}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as buffer:
            buffer.write(content)
        sub_dict = {
            "exercise_id": exercise_id,
            "user_id": str(current_user.get("_id", current_user.get("id"))),
            "file_name": filename,
            "file_path": path,
            "file_size": size,
            "status": "pending_manual",
            "submitted_at": datetime.utcnow(),
            "cad_comparison": {"manual_validation": True},
            "user_feedback": user_feedback
        }
        if quizAnswers:
            try:
                sub_dict["quiz_answers"] = json.loads(quizAnswers)
            except Exception:
                sub_dict["quiz_answers"] = None
                
        result = await submissions_collection.insert_one(sub_dict)
        sub_dict["_id"] = str(result.inserted_id)

        # Send email notification for manual validation
        try:
            from utils.email_utils import send_submission_notification
            
            # Get exercise name from level and order
            exercise_name = f"{level.capitalize()} - Exercice {order}"
            
            # Calculate QCM score if quiz answers exist
            qcm_score = None
            if quizAnswers:
                try:
                    quiz_answers = json.loads(quizAnswers)
                    qcm = ex.get("qcm", [])
                    qcm_score, _, _ = calculate_qcm_score(quiz_answers, qcm)
                except Exception as e:
                    logger.error(f"Error calculating QCM score: {str(e)}")
            
            # Send notification with QCM score
            email_sent = send_submission_notification(
                exercise_name=exercise_name,
                student_email=current_user.get("email"),
                submission_id=str(result.inserted_id),
                file_path=path,
                qcm_score=qcm_score
            )
            
            if email_sent:
                logger.info(f"Email notification sent for submission {result.inserted_id}")
            else:
                logger.error(f"Failed to send email notification for submission {result.inserted_id}")
                
        except Exception as e:
            logger.error(f"Error sending email notification: {str(e)}")
            
        return {"success": True, "submission": serialize_doc(sub_dict)}

    # --- Generic CAD comparison for other exercises ---
    # Allow .sldprt for advanced exercises 6 and 7
    allowed_exts = [".zip", ".rar", ".step"]
    if level == "advanced" and order in [6, 7]:
        allowed_exts.append(".sldprt")
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Extension non autorisée")

    file_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as buffer:
        buffer.write(content)

    try:
        # Import OpenCascade functions first
        from services.occComparison import compare_models, get_solids_from_shape, read_step_file
        
        # Build submission dict first for error cases
        sub_dict = {
            "exercise_id": exercise_id,
            "user_id": str(current_user.get("_id", current_user.get("id"))),
            "file_name": filename,
            "file_path": path,
            "file_size": size,
            "status": "pending",
            "submitted_at": datetime.utcnow()
        }
        
        # Convert SLDPRT to STEP if necessary
        if ext.lower() == '.sldprt':
            try:
                from services.fileConversion import convert_sldprt_to_step
                step_path = path.replace('.sldprt', '.step')
                convert_success = convert_sldprt_to_step(path, step_path)
                if convert_success:
                    logger.info(f"Successfully converted {path} to {step_path}")
                    path = step_path
                else:
                    logger.error("Failed to convert SLDPRT to STEP format")
                    sub_dict["error"] = "Failed to convert SLDPRT file"
                    sub_dict["status"] = "error"
                    return {"success": True, "submission": serialize_doc(sub_dict)}
            except Exception as e:
                logger.error(f"Error converting SLDPRT to STEP: {str(e)}")
                sub_dict["error"] = f"Failed to process SLDPRT file: {str(e)}"
                sub_dict["status"] = "error"
                return {"success": True, "submission": serialize_doc(sub_dict)}
        
        # Get reference file path from exercise
        reference_path = ex.get("solution_file_path")
        if not reference_path:
            cad_result = {"success": False, "error": "Chemin du fichier de référence non défini dans l'exercice"}
        elif not os.path.exists(reference_path):
            cad_result = {"success": False, "error": f"Fichier de référence introuvable: {reference_path}"}
        else:

                # Pour les exercices spécifiques (surfacing et shell)
                if level == "advanced" and order in [4, 5]:  # Exercices de surfacing
                    from services.occComparison import compare_shell_models
                    logger.info("Comparing shell/surface models...")
                    cad_result = compare_shell_models(path, reference_path)
                else:
                    # Lire et analyser le fichier soumis pour les pièces solides
                    sub_shape = read_step_file(path)
                    sub_solids = get_solids_from_shape(sub_shape)
                    
                    # Vérifier le type attendu (pièce ou assemblage)
                    # Si le type n'est pas spécifié, on détermine automatiquement basé sur le fichier de référence
                    ref_shape = read_step_file(reference_path)
                    ref_solids = get_solids_from_shape(ref_shape)
                    
                    is_assembly = len(ref_solids) > 1 if ex.get("type") is None else ex.get("type") == "assembly"
                    
                    if is_assembly and len(sub_solids) == 1:
                        cad_result = {
                            "success": False, 
                            "error": "Ce fichier contient une seule pièce mais l'exercice demande un assemblage"
                        }
                    elif not is_assembly and len(sub_solids) > 1:
                        cad_result = {
                            "success": False, 
                            "error": "Ce fichier contient un assemblage mais l'exercice demande une pièce unique"
                        }
                    else:
                        cad_result = compare_models(path, reference_path)
    except Exception as e:
        cad_result = {"success": False, "error": str(e)}

    # Only use DXF feedback/scoring for advanced exercise 11
    if level == "advanced" and order == 11:
        # DXF score calculation
        dxf_score = 0.0
        if cad_result.get("success") and cad_result.get("matched_shapes") is not None:
            matched = cad_result["matched_shapes"]
            total = cad_result["total_reference"]
            # Si toutes les formes correspondent, donnez le score maximum
            if matched == total:
                dxf_score = 90.0
            else:
                # Sinon, calculez le score proportionnellement
                dxf_score = round(90.0 * (matched / total), 2) if total > 0 else 0.0
            logger.info(f"DXF Score Calculation: matched={matched}, total={total}, score={dxf_score}")
        else:
            logger.warning(f"DXF comparison failed: {cad_result.get('error', 'Unknown error')}")

        # QCM scoring
        qcm = ex.get("qcm", [])
        quiz_answers = None
        if quizAnswers:
            try:
                quiz_answers = json.loads(quizAnswers)
                logger.info(f"Received quizAnswers: {quizAnswers}, parsed: {quiz_answers}")
            except Exception:
                quiz_answers = None
                logger.warning(f"Failed to parse quizAnswers: {quizAnswers}")

        qcm_score, correct_count, total_questions = calculate_qcm_score(quiz_answers, qcm)
        
        # Calculate total score
        total_score = round(dxf_score + qcm_score, 2)
        feedback = f"DXF: {dxf_score}/90, QCM: {qcm_score}/10 ({correct_count}/{total_questions} correct)"
        logger.info(f"Final Scores - DXF: {dxf_score}, QCM: {qcm_score}, Total: {total_score}")
    else:
        # Get CAD score from cad_result (not from feedback)
        cad_score = cad_result.get("global_score", 0) if isinstance(cad_result, dict) else 0
        # Scale the score from 100 to 90 points
        # Scale the CAD score from 100 to 90 points
        cad_score = round((cad_score * 90) / 100, 1) if cad_score > 0 else 0
        
        # Parse quiz answers
        quiz_answers = None
        if quizAnswers:
            try:
                quiz_answers = json.loads(quizAnswers)
            except Exception:
                quiz_answers = None
        
        # Calculate QCM score
        qcm = ex.get("qcm", [])
        qcm_score, correct_count, total_questions = calculate_qcm_score(quiz_answers, qcm)
        
        # Calculate total score
        total_score = round(cad_score + qcm_score, 2)
        
        # Build feedback message
        shell_msg = ""
        if isinstance(cad_result, dict) and isinstance(cad_result.get("principal_moments"), dict):
            pm_data = cad_result["principal_moments"]
            if pm_data.get("message") and "coques" in pm_data["message"]:
                shell_msg = " (Attention: modèle à coques/surfaces, moments principaux non calculés)"
        
        feedback = f"CAD: {cad_score}/90, QCM: {qcm_score}/10 ({correct_count}/{total_questions} correct){shell_msg}"

    # Ensure all scores are properly converted to float
    total_score = float(total_score)
    print(f"Final submission score: {total_score}")  # Debug

    sub_dict = {
        "exercise_id": exercise_id,
        "user_id": str(current_user.get("_id", current_user.get("id"))),
        "file_name": filename,
        "file_path": path,
        "file_size": size,
        "status": "pending",
        "submitted_at": datetime.utcnow(),
        "cad_comparison": cad_result,
        "quiz_answers": quiz_answers,
        "score": total_score,
        "feedback": feedback,
        "user_feedback": user_feedback
    }

    result = await submissions_collection.insert_one(sub_dict)
    sub_dict["_id"] = str(result.inserted_id)

    if total_score >= 90:
        logger.info(f"Exercice {exercise_id} réussi par {current_user.get('email')} avec score {total_score}")
        uid_obj = to_objectid(current_user.get("_id"))
        user_filter = {"_id": uid_obj} if uid_obj else {"email": current_user.get("email")}

        # Get previous best score for this exercise
        latest_user = await users_collection.find_one(user_filter)
        prev_score = None
        if latest_user and isinstance(latest_user, dict):
            scores = latest_user.get("scores", [])
            if isinstance(scores, list):
                for s in scores:
                    if isinstance(s, dict) and s.get("exercise_id") == exercise_id:
                        prev_score = s.get("score", 0)
                        break
        best_score = max(total_score, prev_score) if prev_score is not None else total_score

        await users_collection.update_one(user_filter, {"$addToSet": {"completedExercises": exercise_id}})
        await users_collection.update_one(user_filter, {"$pull": {"scores": {"exercise_id": exercise_id}}})
        await users_collection.update_one(user_filter, {"$push": {"scores": {"exercise_id": exercise_id, "score": best_score}}})

        # Update progress field
        all_ex_cursor = exercises_collection.find({"course_id": course_id_raw})
        all_ex_ids = [str(e["_id"]) async for e in all_ex_cursor]
        completed = set(latest_user.get("completedExercises", [])) if latest_user else set()
        completed_count = len([eid for eid in all_ex_ids if eid in completed])
        total_count = len(all_ex_ids)
        await users_collection.update_one(
            user_filter,
            {"$set": {f"progress.{level}": {"completed": completed_count, "total": total_count}}}
        )
        await users_collection.update_one(user_filter, {"$set": {"updatedAt": datetime.utcnow()}})
    else:
        logger.warning(f"Soumission échouée pour exercice {exercise_id} par {current_user.get('email')}")

    return {"success": True, "submission": serialize_doc(sub_dict)}

# =============================================================================
# MANUAL VALIDATION
# =============================================================================
# Endpoint to list pending manual validations
@app.get("/api/submissions/pending-manual")
async def list_pending_manual_validations(current_user: dict = Depends(require_teacher_or_admin)):
    """List all submissions that require manual validation."""
    pending = []
    cursor = submissions_collection.find({"status": "pending_manual"})
    
    async for sub in cursor:
        # Get exercise details
        ex_id = sub.get("exercise_id")
        ex = await exercises_collection.find_one({"_id": to_objectid(ex_id)})
        
        # Get user details
        user_id = sub.get("user_id")
        user = await users_collection.find_one({"_id": to_objectid(user_id)})
        
        submission_data = serialize_doc(sub)
        submission_data["exercise_title"] = ex.get("title") if ex else "Unknown"
        submission_data["user_email"] = user.get("email") if user else "Unknown"
        if "submitted_at" in sub:
            submission_data["submitted_at_formatted"] = sub["submitted_at"].strftime("%Y-%m-%d %H:%M:%S")
        else:
            submission_data["submitted_at_formatted"] = "No date"
        
        pending.append(submission_data)
    
    return {"success": True, "submissions": pending}

# Endpoint to download submission files
@app.get("/api/submissions/{submission_id}/download")
async def download_submission_file(
    submission_id: str,
    current_user: dict = Depends(require_teacher_or_admin)
):
    """Download the submitted file for a specific submission."""
    sub_obj = to_objectid(submission_id)
    submission = None
    if sub_obj:
        submission = await submissions_collection.find_one({"_id": sub_obj})
    else:
        submission = await submissions_collection.find_one({"_id": submission_id})
        
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
        
    file_path = submission.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(
        file_path,
        filename=submission.get("file_name", "submission.sldasm"),
        media_type="application/octet-stream"
    )

class ManualValidationRequest(BaseModel):
    score: int

@app.post("/api/submissions/{submission_id}/manual-validate")
async def manual_validate_submission(
    submission_id: str,
    payload: ManualValidationRequest = Body(...),
    current_user: dict = Depends(require_teacher_or_admin)
):
    sub_obj = to_objectid(submission_id)
    submission = None
    if sub_obj:
        submission = await submissions_collection.find_one({"_id": sub_obj})
    else:
        submission = await submissions_collection.find_one({"_id": submission_id})
    if not submission:
        raise HTTPException(status_code=404, detail="Soumission non trouvée")

    exercise_id = submission["exercise_id"]
    user_id = submission["user_id"]
    score = int(payload.score)

    # Update submission doc
    await submissions_collection.update_one(
        {"_id": submission["_id"] if isinstance(submission["_id"], ObjectId) else submission["_id"]},
        {"$set": {"status": "validated", "manual_score": score, "validated_at": datetime.utcnow()}}
    )

    # Always keep the best score for this exercise
    user_obj = to_objectid(user_id)
    user_filter = {"_id": user_obj} if user_obj else {"_id": user_id}  # sometimes stored as string
    user = await users_collection.find_one(user_filter)
    prev_score = None
    if user and isinstance(user, dict):
        scores = user.get("scores", [])
        if isinstance(scores, list):
            for s in scores:
                if isinstance(s, dict) and s.get("exercise_id") == exercise_id:
                    prev_score = s.get("score", 0)
                    break
    best_score = max(score, prev_score) if prev_score is not None else score

    # Update the user's score for this exercise to the best score
    await users_collection.update_one(user_filter, {"$pull": {"scores": {"exercise_id": exercise_id}}})
    await users_collection.update_one(user_filter, {"$push": {"scores": {"exercise_id": exercise_id, "score": best_score}}})

    # Only mark as completed and update progress if best score >= 80
    if best_score >= 80:
        await users_collection.update_one(user_filter, {"$addToSet": {"completedExercises": exercise_id}})
        ex_obj = to_objectid(exercise_id)
        ex = await exercises_collection.find_one({"_id": ex_obj}) if ex_obj else await exercises_collection.find_one({"_id": exercise_id})
        course_id_local = ex.get("course_id") if ex else None
        course_obj_local = to_objectid(course_id_local)
        course = await courses_collection.find_one({"_id": course_obj_local}) if course_obj_local else await courses_collection.find_one({"_id": course_id_local}) if course_id_local else None
        level = course.get("level") if course else "unknown"
        all_ex_ids = []
        if course_id_local:
            cursor = exercises_collection.find({"course_id": course_id_local})
            async for doc in cursor:
                all_ex_ids.append(str(doc["_id"]))
        latest_user = await users_collection.find_one(user_filter)
        completed = set(latest_user.get("completedExercises", [])) if latest_user else set()
        completed_count = len([eid for eid in all_ex_ids if eid in completed])
        total_count = len(all_ex_ids)
        await users_collection.update_one(
            user_filter,
            {"$set": {f"progress.{level}": {"completed": completed_count, "total": total_count}}}
        )
        await users_collection.update_one(user_filter, {"$set": {"updatedAt": datetime.utcnow()}})

    return {"success": True}

# =============================================================================
# COMPARAISON STEP/ASSEMBLAGE
# =============================================================================
@app.post("/api/compare-cad")
async def compare_cad(
    reference: UploadFile = File(...),
    submitted: UploadFile = File(...),
    mode: str = "auto",
    tol: float = 1e-3
):
    """Compare deux fichiers CAD STEP (pièce ou assemblage)."""
    # Save both files to temporary files
    with tempfile.NamedTemporaryFile(delete=False, suffix=".step") as f_ref:
        f_ref.write(await reference.read())
        ref_path = f_ref.name
    with tempfile.NamedTemporaryFile(delete=False, suffix=".step") as f_sub:
        f_sub.write(await submitted.read())
        sub_path = f_sub.name

    logger.info(f"[API] Comparaison : submitted_part={sub_path}, reference_part={ref_path}")

    try:
        from services.occComparison import compare_models, read_step_file, get_solids_from_shape

        # Check if it's an assembly or a single part
        ref_shape = read_step_file(ref_path)
        n_solids = len(get_solids_from_shape(ref_shape))

        if mode == "auto":
            mode = "assembly" if n_solids > 1 else "step"

        # Use the same OpenCascade comparison for both modes
        feedback = compare_models(sub_path, ref_path, tol=tol)
        return {"mode": mode, "feedback": feedback}

    except Exception as e:
        logger.error(f"Error in CAD comparison: {str(e)}")
        return {
            "mode": mode,
            "feedback": {
                "success": False,
                "error": str(e),
                "global_score": 0
            }
        }

# =============================================================================
# TEST ROUTES
# =============================================================================
@app.get("/")
def root():
    return {"message": "CAD Platform API", "status": "running", "docs": "/docs"}

# Health check endpoint is already defined above

# =============================================================================
# LANCEMENT UVICORN
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
