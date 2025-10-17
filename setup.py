#!/usr/bin/env python3
"""
Script de configuration et de lancement pour CAD Platform Backend
"""

import os
import sys
import subprocess
import sqlite3
from pathlib import Path

def create_directories():
    """Créer les dossiers nécessaires"""
    directories = [
        "uploads",
        "logs",
        "alembic/versions"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Dossier créé: {directory}")

def create_env_file():
    """Créer le fichier .env s'il n'existe pas"""
    if not os.path.exists('.env'):
        env_content = """# Configuration CAD Platform
DATABASE_URL=sqlite:///./cad_platform.db
SECRET_KEY=cad-platform-secret-key-change-in-production-12345678901234567890
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
UPLOAD_DIR=uploads
MAX_FILE_SIZE=52428800
ALLOWED_EXTENSIONS=.sldprt,.zip,.rar
HOST=0.0.0.0
PORT=8000
DEBUG=True
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
LOG_LEVEL=INFO
ENVIRONMENT=development
"""
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Fichier .env créé")
    else:
        print("ℹ️  Fichier .env existe déjà")

def install_dependencies():
    """Installer les dépendances Python"""
    print("📦 Installation des dépendances...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True, capture_output=True, text=True)
        print("✅ Dépendances installées avec succès")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors de l'installation des dépendances: {e}")
        print(f"Sortie d'erreur: {e.stderr}")
        return False
    return True

def init_database():
    """Initialiser la base de données SQLite"""
    db_path = "cad_platform.db"
    
    if os.path.exists(db_path):
        print("ℹ️  Base de données existe déjà")
        return True
    
    try:
        # Créer la base de données SQLite
        conn = sqlite3.connect(db_path)
        conn.close()
        print("✅ Base de données SQLite créée")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la création de la base de données: {e}")
        return False

def create_admin_user():
    """Créer un utilisateur admin par défaut"""
    print("\n👤 Création d'un utilisateur administrateur...")
    
    try:
        from sqlalchemy.orm import sessionmaker
        from database import engine
        from models import Base, User
        from auth import get_password_hash
        
        # Créer les tables
        Base.metadata.create_all(bind=engine)
        
        # Créer une session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Vérifier si un admin existe déjà
        existing_admin = db.query(User).filter(User.role == 'admin').first()
        if existing_admin:
            print("ℹ️  Un administrateur existe déjà")
            db.close()
            return True
        
        # Créer l'admin par défaut
        admin_user = User(
            name="Administrateur",
            email="admin@cadplatform.com",
            hashed_password=get_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        db.close()
        
        print("✅ Utilisateur admin créé:")
        print("   Email: admin@cadplatform.com")
        print("   Mot de passe: admin123")
        print("   ⚠️  CHANGEZ CE MOT DE PASSE EN PRODUCTION!")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la création de l'admin: {e}")
        return False

def test_server():
    """Tester le serveur"""
    print("\n🚀 Test du serveur...")
    try:
        import requests
        response = requests.get("http://localhost:8000/api/health", timeout=5)
        if response.status_code == 200:
            print("✅ Serveur accessible")
            return True
    except:
        pass
    
    print("ℹ️  Serveur non accessible (normal s'il n'est pas lancé)")
    return True

def main():
    """Fonction principale de configuration"""
    print("🔧 Configuration de CAD Platform Backend")
    print("=" * 50)
    
    # Vérifier Python
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ requis")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Étapes de configuration
    steps = [
        ("Création des dossiers", create_directories),
        ("Création du fichier .env", create_env_file),
        ("Installation des dépendances", install_dependencies),
        ("Initialisation de la base de données", init_database),
        ("Création de l'utilisateur admin", create_admin_user),
        ("Test du serveur", test_server)
    ]
    
    success_count = 0
    
    for step_name, step_func in steps:
        print(f"\n🔄 {step_name}...")
        try:
            if step_func():
                success_count += 1
            else:
                print(f"⚠️  Échec: {step_name}")
        except Exception as e:
            print(f"❌ Erreur dans {step_name}: {e}")
    
    print("\n" + "=" * 50)
    print(f"✅ Configuration terminée: {success_count}/{len(steps)} étapes réussies")
    
    if success_count == len(steps):
        print("\n🎉 Configuration réussie!")
        print("\n📋 Prochaines étapes:")
        print("1. Lancer le serveur: uvicorn main:app --reload")
        print("2. Aller sur: http://localhost:8000/docs")
        print("3. Tester avec admin@cadplatform.com / admin123")
        print("\n🔗 URLs importantes:")
        print("   • Local API Docs: http://localhost:8000/docs")
        print("   • Local Health Check: http://localhost:8000/api/health")
        print("   • Local API Base: http://localhost:8000/api")
        print("\n🌐 Production URLs:")
        print("   • Production API: https://mecaflow-backend-production.up.railway.app")
        print("   • Production Docs: https://mecaflow-backend-production.up.railway.app/docs")
        print("   • Production Health: https://mecaflow-backend-production.up.railway.app/api/health")
    else:
        print("\n⚠️  Configuration incomplète. Vérifiez les erreurs ci-dessus.")

if __name__ == "__main__":
    main()