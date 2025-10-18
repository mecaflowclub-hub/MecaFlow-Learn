# models.py
from pydantic import BaseModel, EmailStr, Field
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict

# -------------------------------
# COURSE MODEL
# -------------------------------
class CourseLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class CourseModel(BaseModel):
    title: str
    description: Optional[str] = None
    level: CourseLevel = CourseLevel.BEGINNER
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

# -------------------------------
# ENUMS
# -------------------------------
class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

class SubmissionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"

# -------------------------------
# CAD PROPERTIES MODEL
# -------------------------------
class CADPropertiesModel(BaseModel):
    dimensions: Optional[bool]
    volume: Optional[bool]
    principal_moments: Optional[bool]
    topology: Optional[bool]

class CADComparisonModel(BaseModel):
    dimensions: bool
    volume: bool
    principal_moments: bool
    topology: bool
    success: bool

# -------------------------------
# USER MODEL
# -------------------------------
class UserModel(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.STUDENT
    profile: Optional[Dict] = {}
    level: DifficultyLevel = DifficultyLevel.BEGINNER
    progress: Optional[Dict] = {}
    completedExercises: Optional[List] = []
    scores: Optional[List] = []
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    total_score: Optional[float] = None
    rank: Optional[str] = None

# -------------------------------
# EXERCISE MODEL
# -------------------------------
class ExerciseModel(BaseModel):
    title: str
    description: str
    instructions: Optional[str] = ""
    difficulty: DifficultyLevel = DifficultyLevel.BEGINNER
    time_limit: Optional[int] = None
    max_submissions: int = 3
    solution_file_path: Optional[str] = None  # chemin du .step de référence
    video_url: Optional[str] = None  # Lien vidéo Drive
    hints: Optional[List[str]] = []  # Astuces
    comments: Optional[str] = ""  # Commentaires/notes
    drawing_url: Optional[str] = None  # Lien Drive du PDF de mise en plan
    type: Optional[str] = "part"  # "part" ou "assembly"
    qcm: Optional[List[str]] = []  # Liste d'IDs d'exercices QCM liés
    course_id: Optional[str] = None  # Lien vers le cours parent
    is_active: bool = True
    is_manual_validation: bool = False  # Indique si l'exercice nécessite une validation manuelle
    created_by: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    order: int = Field(...)  # Required field for ordering exercises

# -------------------------------
# SUBMISSION MODEL
# -------------------------------
class SubmissionModel(BaseModel):
    exercise_id: str
    user_id: str
    file_name: str
    file_path: str
    file_size: Optional[int] = None
    status: SubmissionStatus = SubmissionStatus.PENDING
    score: Optional[float] = None
    feedback: Optional[str] = ""
    processing_details: Optional[str] = ""
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    cad_comparison: Optional[CADComparisonModel]  # <- résultat CAD
    manual_score: Optional[float] = None
    manual_validated: Optional[bool] = None

# -------------------------------
# AUDIT LOG MODEL
# -------------------------------
class AuditLogModel(BaseModel):
    user_id: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# -------------------------------
# SYSTEM CONFIG MODEL
# -------------------------------
class SystemConfigModel(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
