from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import Project, KnowledgeItem
from app.schemas.schemas import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["Projects"])

@router.get("", response_model=List[ProjectResponse])
def get_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.updated_at.desc()).all()

@router.post("", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(
        name=project_in.name,
        description=project_in.description,
        tech_stack=project_in.tech_stack,
        status=project_in.status,
        learnings=project_in.learnings,
        challenges=project_in.challenges,
        link=project_in.link
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Ingest into general knowledge base
    k_item = KnowledgeItem(
        title=f"Project: {project.name}",
        content=f"{project.description or ''}\n\nLearnings: {project.learnings or ''}\nChallenges: {project.challenges or ''}",
        item_type="project",
        topics=project.tech_stack,
        metadata_json={"project_id": project.id}
    )
    db.add(k_item)
    db.commit()

    return project

@router.delete("/{id}")
def delete_project(id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "success", "message": "Project deleted."}
