from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum
from models import CourseLevel, UserRole, SubmissionStatus, DifficultyLevel

# =============================================================================
# USER SCHEMAS
# =============================================================================

class UserBase(BaseModel):
    name: str
    email: str

    @validator('name')
    def validate_name(cls, v):
        if v is None:
            raise ValueError('Le nom est requis')
        if len(str(v).strip()) < 2:
            raise ValueError('Le nom doit contenir au moins 2 caractères')
        return str(v).strip()

class UserCreate(UserBase):
    password: str
    year: Optional[str] = None
    motivation: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Le mot de passe doit contenir au moins 6 caractères')
        return v

    @validator('name')
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Le nom doit contenir au moins 2 caractères')
        return v.strip()

class RegisterWithCodeRequest(UserCreate):
    code: str

class AdminRegisterRequest(UserCreate):
    role: Optional[str] = "student"

class BulkRegisterRequest(BaseModel):
    users: List[AdminRegisterRequest]

class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    confirm_password: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if len(v.strip()) < 2:
                raise ValueError('Le nom doit contenir au moins 2 caractères')
            return v.strip()
        return v

    @validator('new_password')
    def validate_new_password(cls, v, values):
        if v is not None:
            if not values.get('current_password'):
                raise ValueError('Current password is required when changing password')
            if len(v) < 6:
                raise ValueError('Password must be at least 6 characters long')
        return v
    
    @validator('confirm_password')
    def validate_confirm_password(cls, v, values):
        if v is not None and values.get('new_password') is not None:
            if v != values.get('new_password'):
                raise ValueError('Passwords do not match')
        return v

class UpdateProfileResponse(BaseModel):
    success: bool
    user: dict
    message: str

# =============================================================================
# COURSE SCHEMAS
# =============================================================================

class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None
    level: CourseLevel = CourseLevel.BEGINNER

class CourseCreate(CourseBase):
    pass

class CourseResponse(CourseBase):
    id: str
    createdAt: str
    updatedAt: str

    class Config:
        from_attributes = True

class RegisterWithCodeRequest(UserCreate):
    code: str

# =============================================================================
# ENUMS SUPPLEMENTAIRES
# =============================================================================
class CADPropertyComparisonResult(str, Enum):
    TRUE = "true"
    FALSE = "false"

# =============================================================================
# CAD PROPERTIES SCHEMAS
# =============================================================================
class CADProperties(BaseModel):
    dimensions: Optional[bool]
    volume: Optional[bool]
    principal_moments: Optional[bool]
    topology: Optional[bool]

class CADComparisonResult(BaseModel):
    dimensions: bool
    volume: bool
    principal_moments: bool
    topology: bool
    success: bool

# =============================================================================
# USER SCHEMAS
# =============================================================================
class UserBase(BaseModel):
    name: str
    email: EmailStr

    @validator('name')
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Le nom doit contenir au moins 2 caractères')
        return v.strip()

class UserCreate(UserBase):
    password: str
    year: Optional[str] = None
    motivation: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Le mot de passe doit contenir au moins 6 caractères')
        return v

class RegisterWithCodeRequest(UserCreate):
    code: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(UserBase):
    id: str
    created_at: datetime
    is_active: bool
    role: str
    total_score: Optional[float] = None
    rank: Optional[str] = None

    class Config:
        from_attributes = True

# =============================================================================
# EXERCISE SCHEMAS
# =============================================================================
class ExerciseBase(BaseModel):
    title: str
    description: str
    instructions: Optional[str] = None
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER
    solution_file_path: Optional[str] = None
    video_url: Optional[str] = None
    hints: Optional[List[str]] = []
    comments: Optional[str] = ""
    drawing_url: Optional[str] = None
    qcm: Optional[List[dict]] = []
    course_id: Optional[str] = None
    order: int  # Required field for exercise ordering
    is_manual_validation: Optional[bool] = False  # Indique si l'exercice nécessite une validation manuelle

class ExerciseCreate(ExerciseBase):
    pass

class ExerciseResponse(ExerciseBase):
    id: Optional[str]
    created_by: Optional[str]
    is_active: Optional[bool]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

# =============================================================================
# SUBMISSION SCHEMAS
# =============================================================================
class SubmissionBase(BaseModel):
    exercise_id: str
    user_id: str
    file_name: str
    file_path: str
    file_size: Optional[int] = None

class SubmissionCreate(SubmissionBase):
    pass

class SubmissionResponse(SubmissionBase):
    id: str
    status: SubmissionStatus = SubmissionStatus.PENDING
    score: Optional[float]
    feedback: Optional[str]
    processing_details: Optional[str]
    submitted_at: datetime
    processed_at: Optional[datetime]
    cad_comparison: Optional[CADComparisonResult]
    manual_score: Optional[float] = None
    manual_validated: Optional[bool] = None
    progress: Optional[Dict[str, Dict[str, int]]] = None
    quiz_answers: Optional[Dict[str, List[int]]] = None
    user_feedback: Optional[str] = None

    class Config:
        from_attributes = True

# =============================================================================
# TOKEN SCHEMAS
# =============================================================================
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str
