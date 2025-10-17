# crud.py
# =============================================================================
# crud.py – MongoDB
# =============================================================================

from typing import Optional, List
from datetime import datetime
from bson import ObjectId
import uuid

from database import users_collection, exercises_collection, submissions_collection, audit_logs_collection, system_configs_collection
from schemas import (
    UserCreate, UserUpdate, 
    ExerciseCreate, ExerciseUpdate,
    SubmissionCreate, SubmissionUpdate,
    AuditLogCreate
)
from auth import get_password_hash

# ------------------------------
# USER CRUD OPERATIONS
# ------------------------------

async def get_user(user_id: str) -> Optional[dict]:
    return await users_collection.find_one({"_id": ObjectId(user_id)})

async def get_user_by_email(email: str) -> Optional[dict]:
    return await users_collection.find_one({"email": email})

async def get_users(skip: int = 0, limit: int = 100) -> List[dict]:
    cursor = users_collection.find().skip(skip).limit(limit)
    return [u async for u in cursor]

async def create_user(user: UserCreate) -> dict:
    user_dict = user.dict()

    # -------------------------------
    # Vérification et génération username unique
    # -------------------------------
    base_username = (user_dict.get("username") or user_dict.get("name") or "user").lower().replace(" ", "_")
    while True:
        username_candidate = f"{base_username}_{str(uuid.uuid4())[:8]}"
        existing_user = await users_collection.find_one({"username": username_candidate})
        if not existing_user:
            user_dict["username"] = username_candidate
            break

    # -------------------------------
    # Hasher le mot de passe et autres champs
    # -------------------------------
    user_dict["password"] = get_password_hash(user.password)
    user_dict["role"] = user_dict.get("role", "student")
    user_dict["created_at"] = datetime.utcnow()

    # -------------------------------
    # Insertion dans MongoDB
    # -------------------------------
    result = await users_collection.insert_one(user_dict)
    user_dict["_id"] = str(result.inserted_id)
    return user_dict

async def update_user(user_id: str, user: UserUpdate) -> Optional[dict]:
    update_data = {k: v for k, v in user.dict(exclude_unset=True).items()}
    if not update_data:
        return None
    update_data["updated_at"] = datetime.utcnow()
    result = await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    if result.modified_count == 0:
        return None
    return await get_user(user_id)

async def delete_user(user_id: str) -> bool:
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    return result.deleted_count > 0

async def get_users_by_role(role: str, skip: int = 0, limit: int = 100) -> List[dict]:
    cursor = users_collection.find({"role": role}).skip(skip).limit(limit)
    return [u async for u in cursor]

async def search_users(query: str, skip: int = 0, limit: int = 100) -> List[dict]:
    cursor = users_collection.find({
        "$or": [
            {"name": {"$regex": query, "$options": "i"}},
            {"email": {"$regex": query, "$options": "i"}}
        ]
    }).skip(skip).limit(limit)
    return [u async for u in cursor]

# ------------------------------
# EXERCISE CRUD OPERATIONS
# ------------------------------

async def get_exercise(exercise_id: str) -> Optional[dict]:
    return await exercises_collection.find_one({"_id": ObjectId(exercise_id)})

async def get_exercises(skip: int = 0, limit: int = 100, include_inactive: bool = False) -> List[dict]:
    query = {} if include_inactive else {"is_active": True}
    cursor = exercises_collection.find(query).sort("order", 1).skip(skip).limit(limit)
    return [ex async for ex in cursor]

async def create_exercise(exercise: ExerciseCreate, creator_id: str) -> dict:
    ex_dict = exercise.dict()
    ex_dict["created_by"] = creator_id
    ex_dict["created_at"] = datetime.utcnow()
    result = await exercises_collection.insert_one(ex_dict)
    ex_dict["_id"] = str(result.inserted_id)
    return ex_dict

async def create_exercises_bulk(exercises: List[ExerciseCreate], creator_id: str) -> List[dict]:
    now = datetime.utcnow()
    exercise_dicts = []
    for exercise in exercises:
        ex_dict = exercise.dict(exclude_unset=True)
        ex_dict["created_by"] = creator_id
        ex_dict["created_at"] = now
        ex_dict["updated_at"] = now
        ex_dict["is_active"] = True
        exercise_dicts.append(ex_dict)
    result = await exercises_collection.insert_many(exercise_dicts)
    for i, _id in enumerate(result.inserted_ids):
        exercise_dicts[i]["_id"] = str(_id)
    return exercise_dicts

async def update_exercise(exercise_id: str, exercise: ExerciseUpdate) -> Optional[dict]:
    update_data = {k: v for k, v in exercise.dict(exclude_unset=True).items()}
    if not update_data:
        return None
    update_data["updated_at"] = datetime.utcnow()
    result = await exercises_collection.update_one({"_id": ObjectId(exercise_id)}, {"$set": update_data})
    if result.modified_count == 0:
        return None
    return await get_exercise(exercise_id)

async def delete_exercise(exercise_id: str) -> bool:
    result = await exercises_collection.delete_one({"_id": ObjectId(exercise_id)})
    return result.deleted_count > 0

async def search_exercises(query: str, skip: int = 0, limit: int = 100) -> List[dict]:
    cursor = exercises_collection.find({
        "$and": [
            {"is_active": True},
            {"$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]}
        ]
    }).skip(skip).limit(limit)
    return [ex async for ex in cursor]

# ------------------------------
# SUBMISSION CRUD OPERATIONS
# ------------------------------

async def get_submission(submission_id: str) -> Optional[dict]:
    return await submissions_collection.find_one({"_id": ObjectId(submission_id)})

async def get_submissions(user_id: Optional[str] = None, exercise_id: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[dict]:
    query = {}
    if user_id:
        query["user_id"] = user_id
    if exercise_id:
        query["exercise_id"] = exercise_id
    cursor = submissions_collection.find(query).sort("submitted_at", -1).skip(skip).limit(limit)
    return [s async for s in cursor]

async def create_submission(submission: SubmissionCreate) -> dict:
    sub_dict = submission.dict()
    sub_dict["submitted_at"] = datetime.utcnow()
    result = await submissions_collection.insert_one(sub_dict)
    sub_dict["_id"] = str(result.inserted_id)
    return sub_dict

async def update_submission(submission_id: str, submission: SubmissionUpdate) -> Optional[dict]:
    update_data = {k: v for k, v in submission.dict(exclude_unset=True).items()}
    if 'status' in update_data and update_data['status'] in ['success', 'failed', 'error']:
        update_data["processed_at"] = datetime.utcnow()
    result = await submissions_collection.update_one({"_id": ObjectId(submission_id)}, {"$set": update_data})
    if result.modified_count == 0:
        return None
    return await get_submission(submission_id)

async def delete_submission(submission_id: str) -> bool:
    result = await submissions_collection.delete_one({"_id": ObjectId(submission_id)})
    return result.deleted_count > 0

# ------------------------------
# AUDIT LOG CRUD OPERATIONS
# ------------------------------

async def create_audit_log(log: AuditLogCreate) -> dict:
    log_dict = log.dict()
    log_dict["timestamp"] = datetime.utcnow()
    result = await audit_logs_collection.insert_one(log_dict)
    log_dict["_id"] = str(result.inserted_id)
    return log_dict

async def get_audit_logs(user_id: Optional[str] = None, action: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[dict]:
    query = {}
    if user_id:
        query["user_id"] = user_id
    if action:
        query["action"] = action
    cursor = audit_logs_collection.find(query).sort("timestamp", -1).skip(skip).limit(limit)
    return [l async for l in cursor]

# ------------------------------
# SYSTEM CONFIG CRUD OPERATIONS
# ------------------------------

async def get_system_config(key: str) -> Optional[dict]:
    return await system_configs_collection.find_one({"key": key})

async def get_system_configs() -> List[dict]:
    cursor = system_configs_collection.find()
    return [c async for c in cursor]

async def create_system_config(key: str, value: str, description: str = None) -> dict:
    config = {"key": key, "value": value, "description": description, "created_at": datetime.utcnow()}
    result = await system_configs_collection.insert_one(config)
    config["_id"] = str(result.inserted_id)
    return config

async def update_system_config(key: str, value: str) -> Optional[dict]:
    result = await system_configs_collection.update_one({"key": key}, {"$set": {"value": value, "updated_at": datetime.utcnow()}})
    if result.modified_count == 0:
        return None
    return await get_system_config(key)
