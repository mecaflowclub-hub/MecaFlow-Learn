from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import asyncio
import logging

# Load environment variables
load_dotenv()

# Database configuration
DB_NAME = os.getenv("DB_NAME", "mecaflow")
MONGO_URL = os.getenv("MONGODB_URL", "mongodb+srv://islem:enpooran31@cluster0.yjykiin.mongodb.net/mecaflow")

# Initialize MongoDB client with retry logic
async def init_db(max_retries=5, retry_delay=5):
    for attempt in range(max_retries):
        try:
            client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
            await client.admin.command('ping')
            return client
        except Exception as e:
            if attempt == max_retries - 1:
                logging.error(f"Failed to connect to MongoDB after {max_retries} attempts: {str(e)}")
                raise
            logging.warning(f"MongoDB connection attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

# Initialize client
client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]

# Collections
users_collection = db["users"]
courses_collection = db["courses"]
exercises_collection = db["exercises"]
submissions_collection = db["submissions"]

