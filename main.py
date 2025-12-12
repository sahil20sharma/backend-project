
import os
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field, EmailStr
from pymongo import MongoClient, ASCENDING
from bson.objectid import ObjectId
from dotenv import load_dotenv
import bcrypt
import jwt

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MASTER_DB_NAME = os.getenv("MASTER_DB", "master_db")
SECRET_KEY = os.getenv("SECRET_KEY", "secret-key")
JWT_ALGO = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXP = int(os.getenv("JWT_EXP_SECONDS", "3600"))

client = MongoClient(MONGO_URI)
master_db = client[MASTER_DB_NAME]
orgs_col = master_db["organizations"]  


orgs_col.create_index([("organization_name", ASCENDING)], unique=True)

app = FastAPI(title="Organization Management Service - Backend Intern Assignment")


class CreateOrgRequest(BaseModel):
    organization_name: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UpdateOrgRequest(BaseModel):
    organization_name: str = Field(..., min_length=3)
    email: Optional[EmailStr] = None
    password: Optional[str] = None

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


def hash_password(plain: str) -> bytes:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt())

def verify_password(plain: str, hashed: bytes) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed)

def create_jwt(payload: dict) -> str:
    payload_copy = payload.copy()
    payload_copy["exp"] = int(time.time()) + JWT_EXP
    return jwt.encode(payload_copy, SECRET_KEY, algorithm=JWT_ALGO)

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_admin(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ", 1)[1]
    data = decode_jwt(token)
    return data  


def org_collection_name(org_name: str) -> str:
    sanitized = "".join(c.lower() if c.isalnum() else "_" for c in org_name.strip())
    return f"org_{sanitized}"


@app.post("/org/create")
def create_org(req: CreateOrgRequest):
    
    if orgs_col.find_one({"organization_name": req.organization_name}):
        raise HTTPException(status_code=400, detail="Organization name already exists")

    
    admin_doc = {
        "email": req.email,
        "password_hash": hash_password(req.password),
        "created_at": int(time.time())
    }
    admins_col = master_db["admins"]
    
    if admins_col.find_one({"email": req.email}):
        
        raise HTTPException(status_code=400, detail="Admin email already used")

    admin_id = admins_col.insert_one(admin_doc).inserted_id

    
    collection_name = org_collection_name(req.organization_name)
    org_specific_col = master_db[collection_name]  

    
    org_specific_col.insert_one({"_meta": "collection_created", "created_at": int(time.time())})

    
    org_meta = {
        "organization_name": req.organization_name,
        "collection_name": collection_name,
        "admin_id": str(admin_id),
        "created_at": int(time.time())
    }
    org_id = orgs_col.insert_one(org_meta).inserted_id

    return {"status": "success", "organization": {"id": str(org_id), "organization_name": req.organization_name, "collection_name": collection_name}}

@app.get("/org/get")
def get_org(organization_name: str):
    doc = orgs_col.find_one({"organization_name": organization_name})
    if not doc:
        raise HTTPException(status_code=404, detail="Organization not found")
    doc["_id"] = str(doc["_id"])
    return {"status": "success", "organization": doc}

@app.put("/org/update")
def update_org(req: UpdateOrgRequest, admin=Depends(get_current_admin)):
    

    existing = orgs_col.find_one({"organization_name": req.organization_name})
    if not existing:
        raise HTTPException(status_code=404, detail="Organization not found")

    updates = {}
    if req.email or req.password:
        
        admin_id = existing.get("admin_id")
        admins_col = master_db["admins"]
        admin_obj = admins_col.find_one({"_id": ObjectId(admin_id)})
        if not admin_obj:
            raise HTTPException(status_code=500, detail="Admin referenced not found")
        if req.email:
            
            if admins_col.find_one({"email": req.email, "_id": {"$ne": ObjectId(admin_id)}}):
                raise HTTPException(status_code=400, detail="Email already in use")
            admins_col.update_one({"_id": ObjectId(admin_id)}, {"$set": {"email": req.email}})
        if req.password:
            admins_col.update_one({"_id": ObjectId(admin_id)}, {"$set": {"password_hash": hash_password(req.password)}})

    
    new_name = req.organization_name.strip()
    if new_name != existing["organization_name"]:
        
        if orgs_col.find_one({"organization_name": new_name}):
            raise HTTPException(status_code=400, detail="Target organization name already exists")
        old_col_name = existing["collection_name"]
        new_col_name = org_collection_name(new_name)
        
        try:
            master_db[old_col_name].rename(new_col_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed renaming collection: {str(e)}")
        updates["organization_name"] = new_name
        updates["collection_name"] = new_col_name

    if updates:
        orgs_col.update_one({"_id": existing["_id"]}, {"$set": updates})

    return {"status": "success", "message": "Organization updated"}

@app.delete("/org/delete")
def delete_org(organization_name: str, admin=Depends(get_current_admin)):
    existing = orgs_col.find_one({"organization_name": organization_name})
    if not existing:
        raise HTTPException(status_code=404, detail="Organization not found")

    
    admin_org_id = admin.get("org_id")
    if admin_org_id and admin_org_id != str(existing["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to delete this organization")

    
    try:
        master_db.drop_collection(existing["collection_name"])
    except Exception as e:
        pass  


    admins_col = master_db["admins"]
    if existing.get("admin_id"):
        try:
            admins_col.delete_one({"_id": ObjectId(existing["admin_id"])})
        except Exception:
            pass
    orgs_col.delete_one({"_id": existing["_id"]})

    return {"status": "success", "message": "Organization deleted"}

@app.post("/admin/login")
def admin_login(req: AdminLoginRequest):
    admins_col = master_db["admins"]
    admin = admins_col.find_one({"email": req.email})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    
    org = orgs_col.find_one({"admin_id": str(admin["_id"])})
    payload = {
        "admin_id": str(admin["_id"]),
        "org_id": str(org["_id"]) if org else None,
        "email": admin["email"]
    }
    token = create_jwt(payload)
    return {"status": "success", "token": token}
