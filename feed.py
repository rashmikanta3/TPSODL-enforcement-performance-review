import sys
from datetime import date
from database import engine, SessionLocal, init_db, reset_db, active_db_url
from models import User, TeamLead, Team, Employee, VCRMaster

SAMPLE_USERS = [
    # 1. Admin Account (Full unrestricted access across all circles)
    {
        "username": "admin",
        "password": "admin123",
        "role": "ADMIN",
        "circle": None,
        "can_edit": True,
        "description": "System Administrator (Full Access)"
    },
    # 2. Sub-Admin Accounts (Multi-circle scoped access)
    {
        "username": "subadmin_berhampur",
        "password": "subadmin123",
        "role": "SUB_ADMIN",
        "circle": "BERHAMPUR,BERHAMPUR CITY",
        "can_edit": True,
        "description": "Sub-Admin for Berhampur & Berhampur City"
    },
    {
        "username": "subadmin_south",
        "password": "subadmin123",
        "role": "SUB_ADMIN",
        "circle": "JEYPORE,RAYAGADA",
        "can_edit": True,
        "description": "Sub-Admin for Jeypore & Rayagada"
    },
    # 3. Regular Field Users
    {
        "username": "user_aska",
        "password": "user123",
        "role": "USER",
        "circle": "ASKA",
        "can_edit": True,
        "description": "Field Operator for Aska Circle"
    },
    {
        "username": "viewer",
        "password": "viewer123",
        "role": "USER",
        "circle": None,
        "can_edit": False,
        "description": "Read-Only Dashboard Viewer"
    }
]

SAMPLE_TEAM_LEADS = [
    {
        "tl_code": "TL-101",
        "name": "Er. Ramesh Chandra Mohapatra",
        "designation": "Assistant Executive Engineer / TL",
        "circle": "BERHAMPUR",
        "contact_no": "9437012345"
    },
    {
        "tl_code": "TL-102",
        "name": "Er. Sunil Kumar Nayak",
        "designation": "Assistant Manager (Enforcement)",
        "circle": "BERHAMPUR CITY",
        "contact_no": "9437023456"
    },
    {
        "tl_code": "TL-103",
        "name": "Er. Bikash Ranjan Sahu",
        "designation": "Sub-Divisional Officer (SDO)",
        "circle": "ASKA",
        "contact_no": "9437034567"
    },
    {
        "tl_code": "TL-104",
        "name": "Er. Pradeep Kumar Das",
        "designation": "Assistant Engineer (Enforcement)",
        "circle": "BHANJANAGAR",
        "contact_no": "9437045678"
    },
    {
        "tl_code": "TL-105",
        "name": "Er. Santosh Kumar Jena",
        "designation": "Manager (Enforcement)",
        "circle": "JEYPORE",
        "contact_no": "9437056789"
    },
    {
        "tl_code": "TL-106",
        "name": "Er. Manoranjan Tripathy",
        "designation": "Assistant Engineer (Operations)",
        "circle": "RAYAGADA",
        "contact_no": "9437067890"
    }
]

SAMPLE_TEAMS = [
    {
        "name": "SQUAD BERHAMPUR-1",
        "circle": "BERHAMPUR",
        "supervisor_name": "Er. P. K. Panda",
        "tl_code": "TL-101"
    },
    {
        "name": "SQUAD BERHAMPUR CITY-1",
        "circle": "BERHAMPUR CITY",
        "supervisor_name": "Er. M. K. Samal",
        "tl_code": "TL-102"
    },
    {
        "name": "SQUAD ASKA-1",
        "circle": "ASKA",
        "supervisor_name": "Er. K. C. Behera",
        "tl_code": "TL-103"
    },
    {
        "name": "SQUAD BHANJANAGAR-1",
        "circle": "BHANJANAGAR",
        "supervisor_name": "Er. S. N. Mishra",
        "tl_code": "TL-104"
    },
    {
        "name": "SQUAD JEYPORE-1",
        "circle": "JEYPORE",
        "supervisor_name": "Er. A. K. Patra",
        "tl_code": "TL-105"
    },
    {
        "name": "SQUAD RAYAGADA-1",
        "circle": "RAYAGADA",
        "supervisor_name": "Er. T. R. Sahu",
        "tl_code": "TL-106",
        "has_vehicle": True,
        "is_office_team": False
    },
    {
        "name": "OFFICE MIS SQUAD - BERHAMPUR",
        "circle": "BERHAMPUR",
        "supervisor_name": "Er. P. K. Panda",
        "tl_code": "TL-101",
        "has_vehicle": False,
        "is_office_team": True
    }
]

SAMPLE_BA_EMPLOYEES = [
    # Berhampur Field
    {"emp_code": "EMP-BA-01", "name": "Kailash Gouda", "designation": "Lineman (BA)", "circle": "BERHAMPUR", "team": "SQUAD BERHAMPUR-1"},
    {"emp_code": "EMP-BA-02", "name": "Rabindra Sethi", "designation": "Helper (BA)", "circle": "BERHAMPUR", "team": "SQUAD BERHAMPUR-1"},
    {"emp_code": "EMP-BA-03", "name": "Dillip Kumar Patra", "designation": "Driver (BA)", "circle": "BERHAMPUR", "team": "SQUAD BERHAMPUR-1"},
    # Berhampur Office (Without Vehicle)
    {"emp_code": "EMP-BA-16", "name": "Deepak Kumar Sethi", "designation": "MIS Data Assistant (BA)", "circle": "BERHAMPUR", "team": "OFFICE MIS SQUAD - BERHAMPUR"},
    {"emp_code": "EMP-BA-17", "name": "Sunita Kumari Barik", "designation": "Office Assistant (BA)", "circle": "BERHAMPUR", "team": "OFFICE MIS SQUAD - BERHAMPUR"},
    # Berhampur City
    {"emp_code": "EMP-BA-04", "name": "Subhashree Pradhan", "designation": "Squad Member (BA)", "circle": "BERHAMPUR CITY", "team": "SQUAD BERHAMPUR CITY-1"},
    {"emp_code": "EMP-BA-05", "name": "Jitendra Sahu", "designation": "Lineman (BA)", "circle": "BERHAMPUR CITY", "team": "SQUAD BERHAMPUR CITY-1"},
    {"emp_code": "EMP-BA-06", "name": "Manoj Behera", "designation": "Helper (BA)", "circle": "BERHAMPUR CITY", "team": "SQUAD BERHAMPUR CITY-1"},
    # Aska
    {"emp_code": "EMP-BA-07", "name": "Tukuna Nayak", "designation": "Lineman (BA)", "circle": "ASKA", "team": "SQUAD ASKA-1"},
    {"emp_code": "EMP-BA-08", "name": "Sarat Chandra Swain", "designation": "Helper (BA)", "circle": "ASKA", "team": "SQUAD ASKA-1"},
    {"emp_code": "EMP-BA-09", "name": "Purna Chandra Maharana", "designation": "Driver (BA)", "circle": "ASKA", "team": "SQUAD ASKA-1"},
    # Bhanjanagar
    {"emp_code": "EMP-BA-10", "name": "Bikram Keshari Rout", "designation": "Lineman (BA)", "circle": "BHANJANAGAR", "team": "SQUAD BHANJANAGAR-1"},
    {"emp_code": "EMP-BA-11", "name": "Pravat Kumar Jena", "designation": "Helper (BA)", "circle": "BHANJANAGAR", "team": "SQUAD BHANJANAGAR-1"},
    # Jeypore
    {"emp_code": "EMP-BA-12", "name": "Gagan Bihari Sahoo", "designation": "Lineman (BA)", "circle": "JEYPORE", "team": "SQUAD JEYPORE-1"},
    {"emp_code": "EMP-BA-13", "name": "Santosh Muduli", "designation": "Helper (BA)", "circle": "JEYPORE", "team": "SQUAD JEYPORE-1"},
    # Rayagada
    {"emp_code": "EMP-BA-14", "name": "Simanchal Gouda", "designation": "Lineman (BA)", "circle": "RAYAGADA", "team": "SQUAD RAYAGADA-1"},
    {"emp_code": "EMP-BA-15", "name": "Pratap Kumar Dora", "designation": "Helper (BA)", "circle": "RAYAGADA", "team": "SQUAD RAYAGADA-1"}
]

SAMPLE_VCRS = [
    {
        "vcr_number": "VCR-2026-001",
        "consumer_name": "Ramesh Chandra Sahu",
        "consumer_address": "Main Road, Aska",
        "circle": "ASKA",
        "division": "AED ASKA-I",
        "subdivision": "ASKA",
        "section": "ESO ASKA-1",
        "provisional_bill_date": date(2026, 11, 1)
    },
    {
        "vcr_number": "VCR-2026-002",
        "consumer_name": "Binod Kumar Jena",
        "consumer_address": "Bada Bazar, Berhampur",
        "circle": "BERHAMPUR",
        "division": "GANJAM NORTH",
        "subdivision": "CHATRAPUR",
        "section": "ESO CHATRAPUR-I",
        "provisional_bill_date": date(2026, 11, 2)
    },
    {
        "vcr_number": "VCR-2026-003",
        "consumer_name": "Kailash Patra",
        "consumer_address": "Gandhi Nagar, Berhampur",
        "circle": "BERHAMPUR CITY",
        "division": "BERHAMPUR-II",
        "subdivision": "SUB.DIVISION NO-3",
        "section": "ESO GANDHINAGAR",
        "provisional_bill_date": date(2026, 11, 3)
    },
    {
        "vcr_number": "VCR-2026-004",
        "consumer_name": "Laxman Majhi",
        "consumer_address": "Station Road, Rayagada",
        "circle": "RAYAGADA",
        "division": "RED RAYAGADA",
        "subdivision": "RAYAGADA",
        "section": "ESO RAYAGADA-1",
        "provisional_bill_date": date(2026, 11, 1)
    },
    {
        "vcr_number": "VCR-2026-005",
        "consumer_name": "Harihar Biswal",
        "consumer_address": "College Road, Jeypore",
        "circle": "JEYPORE",
        "division": "JED JEYPORE",
        "subdivision": "JEYPORE SDO-I",
        "section": "ESO BAIPARIGUDA",
        "provisional_bill_date": date(2026, 11, 2)
    }
]

def feed_all(reset: bool = True):
    print("=================================================================")
    print(f"DATABASE SEEDING & SYNCHRONIZATION: {active_db_url.split('@')[-1] if '@' in active_db_url else active_db_url}")
    print("=================================================================")

    if reset:
        print("\n[1/6] Performing fresh schema reset (dropping and recreating 11 tables)...")
        reset_db()
        print("      Schema reset completed successfully.")
    else:
        print("\n[1/6] Synchronizing existing database schema...")
        init_db(reset=False)
        print("      Schema verified.")

    db = SessionLocal()
    try:
        # 1. Seed Portal Users (Upsert)
        print("\n[2/6] Seeding Portal Users (Admin, Sub-Admins, Field Users)...")
        for u in SAMPLE_USERS:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if existing:
                existing.password = u["password"]
                existing.role = u["role"]
                existing.circle = u["circle"]
                existing.can_edit = u["can_edit"]
                existing.is_active = True
            else:
                db.add(User(
                    username=u["username"],
                    password=u["password"],
                    role=u["role"],
                    circle=u["circle"],
                    can_edit=u["can_edit"],
                    is_active=True
                ))
        db.commit()
        print(f"      Seeded/Synchronized {len(SAMPLE_USERS)} portal users.")

        # 2. Seed TPSODL Team Leaders (Permanent Officers - Upsert)
        print("\n[3/6] Seeding TPSODL Team Leaders (Permanent Officers)...")
        tl_map = {}
        for tl_data in SAMPLE_TEAM_LEADS:
            existing = db.query(TeamLead).filter(TeamLead.tl_code == tl_data["tl_code"]).first()
            if existing:
                existing.name = tl_data["name"]
                existing.designation = tl_data["designation"]
                existing.circle = tl_data["circle"]
                existing.contact_no = tl_data["contact_no"]
                existing.is_active = True
                tl_id = existing.id
                tl_name = existing.name
            else:
                tl = TeamLead(
                    tl_code=tl_data["tl_code"],
                    name=tl_data["name"],
                    designation=tl_data["designation"],
                    circle=tl_data["circle"],
                    contact_no=tl_data["contact_no"],
                    is_active=True
                )
                db.add(tl)
                db.flush()
                tl_id = tl.id
                tl_name = tl.name
            tl_map[tl_data["tl_code"]] = {"id": tl_id, "name": tl_name}
        db.commit()
        print(f"      Seeded/Synchronized {len(SAMPLE_TEAM_LEADS)} TPSODL Team Leaders.")

        # 3. Seed Enforcement Squads (Teams - Upsert)
        print("\n[4/6] Seeding Squads (Teams) with designated default TL...")
        team_map = {}
        for t_data in SAMPLE_TEAMS:
            tl_info = tl_map.get(t_data["tl_code"], {})
            tl_id = tl_info.get("id")
            tl_name = tl_info.get("name", "TPSODL TL")
            has_veh = t_data.get("has_vehicle", True)
            is_off = t_data.get("is_office_team", False)
            existing = db.query(Team).filter(Team.name == t_data["name"]).first()
            if existing:
                existing.circle = t_data["circle"]
                existing.supervisor_name = t_data["supervisor_name"]
                existing.default_tl_id = tl_id
                existing.assigned_team_lead = tl_name
                existing.has_vehicle = has_veh
                existing.is_office_team = is_off
                existing.is_active = True
                team_map[existing.name] = existing.id
            else:
                team = Team(
                    name=t_data["name"],
                    circle=t_data["circle"],
                    supervisor_name=t_data["supervisor_name"],
                    default_tl_id=tl_id,
                    assigned_team_lead=tl_name,
                    has_vehicle=has_veh,
                    is_office_team=is_off,
                    is_active=True
                )
                db.add(team)
                db.flush()
                team_map[team.name] = team.id
        db.commit()
        print(f"      Seeded/Synchronized {len(SAMPLE_TEAMS)} enforcement squads.")

        # 4. Seed BA Contractor Employees (Manpower for Form D Attendance - Upsert)
        print("\n[5/6] Seeding BA Contractor Employees (Manpower for Form D Register)...")
        for emp_data in SAMPLE_BA_EMPLOYEES:
            target_team_id = team_map.get(emp_data["team"])
            existing = db.query(Employee).filter(Employee.emp_code == emp_data["emp_code"]).first()
            if existing:
                existing.name = emp_data["name"]
                existing.designation = emp_data["designation"]
                existing.circle = emp_data["circle"]
                existing.team_id = target_team_id
                existing.is_active = True
            else:
                emp = Employee(
                    emp_code=emp_data["emp_code"],
                    name=emp_data["name"],
                    designation=emp_data["designation"],
                    circle=emp_data["circle"],
                    team_id=target_team_id,
                    is_active=True
                )
                db.add(emp)
        db.commit()
        print(f"      Seeded/Synchronized {len(SAMPLE_BA_EMPLOYEES)} BA contractor personnel.")

        # 5. Seed Sample VCR Masters (Upsert)
        print("\n[6/6] Seeding Sample VCR Masters...")
        for v in SAMPLE_VCRS:
            existing = db.query(VCRMaster).filter(VCRMaster.vcr_number == v["vcr_number"]).first()
            if existing:
                existing.consumer_name = v["consumer_name"]
                existing.consumer_address = v["consumer_address"]
                existing.circle = v["circle"]
                existing.division = v["division"]
                existing.subdivision = v["subdivision"]
                existing.section = v["section"]
                existing.provisional_bill_date = v["provisional_bill_date"]
            else:
                vcr = VCRMaster(
                    vcr_number=v["vcr_number"],
                    consumer_name=v["consumer_name"],
                    consumer_address=v["consumer_address"],
                    circle=v["circle"],
                    division=v["division"],
                    subdivision=v["subdivision"],
                    section=v["section"],
                    provisional_bill_date=v["provisional_bill_date"]
                )
                db.add(vcr)
        db.commit()
        print(f"      Seeded/Synchronized {len(SAMPLE_VCRS)} sample VCR records.")

        print("\n=================================================================")
        print("ALL 11 TABLES SEEDED/SYNCHRONIZED SUCCESSFULLY WITH LIVE TEST DATA!")
        print("=================================================================")

    except Exception as e:
        db.rollback()
        print(f"ERROR during seeding: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    reset_flag = True
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("--no-reset", "-n"):
        reset_flag = False
    feed_all(reset=reset_flag)
