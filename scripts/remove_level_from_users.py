
# Script to remove 'level' field and drop 'username' index from all users in MongoDB
import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb://127.0.0.1:27017"
DB_NAME = "mecaflow"

async def remove_level_field(users_collection):
    result = await users_collection.update_many({}, {"$unset": {"level": ""}})
    print(f"Updated {result.modified_count} user(s): removed 'level' field.")

async def drop_username_index(users_collection):
    try:
        await users_collection.drop_index("username_1")
        print("Index 'username_1' supprimé avec succès.")
    except Exception as e:
        print(f"Erreur lors de la suppression de l'index : {e}")

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    users_collection = db["users"]
    await remove_level_field(users_collection)
    await drop_username_index(users_collection)

if __name__ == "__main__":
    asyncio.run(main())