"""
Initialize the database and create default data.
Run this script after setting up the database.

Usage: python -m scripts.init_db
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base, SessionLocal
from app.core.security import hash_password
from app.models.department import Department
from app.models.employee import Employee
from app.models.face_encoding import FaceEncoding
from app.models.attendance import AttendanceRecord, WorkSchedule
from app.models.user import AdminUser, SystemLog
from app.config import settings


def init_database():
    """Create all tables and seed default data."""
    print("=" * 50)
    print("FTA - Database Initialization")
    print("=" * 50)

    # Ensure directories
    settings.ensure_directories()

    # Create tables
    print("\n[1/3] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully")

    db = SessionLocal()
    try:
        # Create default admin
        print("\n[2/3] Creating default admin user...")
        admin = db.query(AdminUser).filter(AdminUser.username == "admin").first()
        if not admin:
            admin = AdminUser(
                username="admin",
                hashed_password=hash_password("admin123"),
                full_name="System Administrator",
                role="ADMIN",
            )
            db.add(admin)
            db.commit()
            print("✅ Admin user created (admin / admin123)")
        else:
            print("⏭️  Admin user already exists")

        # Create default departments
        print("\n[3/3] Creating default departments...")
        default_departments = [
            ("Phòng Kỹ thuật", "Engineering / Development"),
            ("Phòng Kinh doanh", "Sales / Business"),
            ("Phòng Nhân sự", "Human Resources"),
            ("Phòng Hành chính", "Administration"),
            ("Ban Giám đốc", "Management / Board"),
        ]

        for name, desc in default_departments:
            existing = db.query(Department).filter(Department.name == name).first()
            if not existing:
                db.add(Department(name=name, description=desc))
                print(f"  ✅ Created: {name}")
            else:
                print(f"  ⏭️  Exists: {name}")

        # Create default work schedule
        default_schedule = db.query(WorkSchedule).filter(WorkSchedule.is_default == True).first()
        if not default_schedule:
            schedule = WorkSchedule(
                name="Ca hành chính",
                start_time="08:00",
                end_time="17:00",
                late_threshold_minutes=15,
                is_default=True,
            )
            db.add(schedule)
            print("  ✅ Created default work schedule (08:00 - 17:00)")

        db.commit()

    finally:
        db.close()

    print("\n" + "=" * 50)
    print("✅ Database initialization complete!")
    print(f"   Database: {settings.DATABASE_URL}")
    print(f"   Login: admin / admin123")
    print("=" * 50)


if __name__ == "__main__":
    init_database()
