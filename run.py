#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de lancement pour CAD Platform Backend
"""

import os
import sys
import argparse
import uvicorn
from pathlib import Path

def get_port():
    """Get port from environment with validation"""
    try:
        port = int(os.getenv("PORT", "8000"))
        if not (1024 <= port <= 65535):
            print(f"Warning: Port {port} outside recommended range (1024-65535), using 8000")
            return 8000
        return port
    except ValueError:
        print("Warning: Invalid PORT value, using default 8000")
        return 8000

def check_requirements():
    """Vérifier que l'environnement est prêt"""
    issues = []
    
    # Vérifier les fichiers essentiels
    required_files = [
        "main.py",
        "database.py", 
        "models.py",
        "schemas.py",
        "auth.py",
        "crud.py",
        "requirements.txt"
    ]
    
    for file in required_files:
        if not os.path.exists(file):
            issues.append(f"[X] Fichier manquant: {file}")
    
    # Vérifier le fichier .env
    if not os.path.exists('.env'):
        issues.append("[!] Fichier .env manquant (créé automatiquement)")
        create_default_env()
    
    # Vérifier le dossier uploads
    if not os.path.exists('uploads'):
        os.makedirs('uploads', exist_ok=True)
        print("[✓] Dossier uploads créé")
    
    return issues

def create_default_env():
    """Créer un fichier .env par défaut"""
    env_content = """DATABASE_URL=sqlite:///./cad_platform.db
SECRET_KEY=default-secret-key-change-in-production-12345678901234567890
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
UPLOAD_DIR=uploads
HOST=0.0.0.0
PORT=8000
DEBUG=True
CORS_ORIGINS=http://localhost:3000
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    print("\u2705 Fichier .env créé avec les valeurs par défaut")

def install_deps():
    """Installer les dépendances"""
    print("📦 Installation des dépendances...")
    os.system(f"{sys.executable} -m pip install -r requirements.txt")

def setup_database():
    """Configurer la base de données"""
    print("🗄️  Configuration de la base de données...")
    
    try:
        from database import engine
        from models import Base
        
        # Créer toutes les tables
        Base.metadata.create_all(bind=engine)
        print("\u2705 Tables créées")
        
        # Créer un admin par défaut si nécessaire
        create_default_admin()
        
    except Exception as e:
        print(f"\u26A0\uFE0F  Erreur DB: {e}")

def create_default_admin():
    """Créer un administrateur par défaut"""
    try:
        from sqlalchemy.orm import sessionmaker
        from database import engine
        from models import User
        from auth import get_password_hash
        
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        
        # Vérifier si un admin existe
        existing_admin = db.query(User).filter(User.role == 'ADMIN').first()
        if not existing_admin:
            ADMIN = User(
                name="ADMIN",
                email="admin@test.com",
                hashed_password=get_password_hash("admin123"),
                role="ADMIN"
            )
            db.add(ADMIN)
            db.commit()
            print("👤 Admin créé: admin@test.com / admin123")
        
        db.close()
        
    except Exception as e:
        print(f"\u26A0\uFE0F  Erreur admin: {e}")

def run_server(host="0.0.0.0", port=8000, reload=True, log_level="info"):
    """Lancer le serveur FastAPI"""
    print(f"🚀 Lancement du serveur sur http://{host}:{port}")
    print(f"📚 Documentation: http://{host}:{port}/docs")
    print("⏹️  Ctrl+C pour arrêter")
    print("-" * 50)
    
    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level
        )
    except KeyboardInterrupt:
        print("\n👋 Serveur arrêté")
    except Exception as e:
        print(f"❌ Erreur serveur: {e}")

def main():
    """Fonction principale"""
    parser = argparse.ArgumentParser(description="CAD Platform Backend Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host à écouter")
    parser.add_argument("--port", type=int, default=8000, help="Port à écouter")
    parser.add_argument("--no-reload", action="store_true", help="Désactiver le rechargement auto")
    parser.add_argument("--log-level", default="info", help="Niveau de log")
    parser.add_argument("--setup", action="store_true", help="Configurer l'environnement")
    parser.add_argument("--install", action="store_true", help="Installer les dépendances")
    
    args = parser.parse_args()
    
    print("🔧 CAD Platform Backend")
    print("=" * 40)
    
    # Configuration si demandée
    if args.setup:
        print("⚙️  Configuration de l'environnement...")
        setup_database()
        return
    
    # Installation des dépendances si demandée
    if args.install:
        install_deps()
        return
    
    # Vérifications
    issues = check_requirements()
    if issues:
        print("\u26A0\uFE0F  Problèmes détectés:")
        for issue in issues:
            print(f"   {issue}")
        
        if any("❌" in issue for issue in issues):
            print("\n💡 Essayez: python setup.py")
            sys.exit(1)
    
    # Configuration automatique de la DB
    setup_database()
    
    # Lancement du serveur
    run_server(
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level=args.log_level
    )

if __name__ == "__main__":
    main()