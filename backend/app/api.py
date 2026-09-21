from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app import config_store
from app.auth import authenticate_user, create_access_token, get_current_user, require_bioops
from app.database import SessionLocal, get_db
from app.limits import check_limits, measure_content
from app.models import Job, JobStage, Sample
from app.pipeline.runner import create_job_stages, run_pipeline_sync
from app.schemas import (
    HealthOut,
    JobCreate,
    JobListItem,
    JobOut,
    LimitsOut,
    LimitsUpdate,
    LoginRequest,
    SampleOut,
    StageOut,
    TokenResponse,
)


router = APIRouter(prefix="/api")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_job_background(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            run_pipeline_sync(db, job)
    finally:
        db.close()


@router.get("/health", response_model=HealthOut)
def health():
    return HealthOut(status="ok", service="fastq-qc-pipeline")


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = authenticate_user(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user["username"], user["role"])
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/samples", response_model=list[SampleOut])
def list_samples(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Sample).order_by(Sample.id).all()


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: JobCreate,
    background: BackgroundTasks,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    sample_id = body.sampleId
    fastq_text = (body.fastqText or "").strip()
    sample_name = "自定义输入"
    sample = None

    if sample_id is not None:
        sample = db.query(Sample).filter(Sample.id == sample_id).first()
        if not sample:
            raise HTTPException(status_code=404, detail="样例不存在")
        fastq_text = sample.fastq_content.strip()
        sample_name = sample.name
    elif not fastq_text:
        # 空或纯空白直接拒绝，不留草稿
        raise HTTPException(status_code=400, detail="请提供 sampleId 或非空的 fastqText")

    if not fastq_text:
        raise HTTPException(status_code=400, detail="FASTQ 内容为空或纯空白")

    # 容量门禁：浏览器已拦一道，服务端为最终裁决
    size = measure_content(fastq_text)
    limits = config_store.get_limits(db)
    reason = check_limits(size, limits)
    if reason is not None:
        if body.saveRejectedDraft:
            draft = Job(
                sample_id=sample.id if sample else None,
                sample_name=sample_name,
                status="rejected",
                created_by=user["username"],
                fastq_snapshot=fastq_text,
                error_message=reason,
                metrics={
                    "char_count": size.char_count,
                    "read_estimate": size.read_estimate,
                    "max_chars": limits.max_chars,
                    "max_reads": limits.max_reads,
                    "rejected": True,
                },
                finished_at=_utcnow(),
            )
            db.add(draft)
            db.commit()
            db.refresh(draft)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": reason,
                "char_count": size.char_count,
                "read_estimate": size.read_estimate,
                "max_chars": limits.max_chars,
                "max_reads": limits.max_reads,
                "draft_saved": bool(body.saveRejectedDraft),
                "draft_id": draft.id if body.saveRejectedDraft else None,
            },
        )

    job = Job(
        sample_id=sample.id if sample else None,
        sample_name=sample_name,
        status="pending",
        created_by=user["username"],
        fastq_snapshot=fastq_text,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    create_job_stages(db, job.id)
    background.add_task(_run_job_background, job.id)

    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job.id)
        .first()
    )
    return job


@router.get("/config/limits", response_model=LimitsOut)
def get_limits(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return LimitsOut(**config_store.get_limits(db).__dict__)


@router.put("/config/limits", response_model=LimitsOut)
def update_limits(
    body: LimitsUpdate,
    user: dict = Depends(require_bioops),
    db: Session = Depends(get_db),
):
    limits = config_store.save_limits(
        db, body.max_chars, body.max_reads, user["username"]
    )
    return LimitsOut(**limits.__dict__)


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.id.desc()).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.stages))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return job


@router.get("/jobs/{job_id}/stages", response_model=list[StageOut])
def get_job_stages(
    job_id: int, _user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="作业不存在")
    return (
        db.query(JobStage)
        .filter(JobStage.job_id == job_id)
        .order_by(JobStage.stage_order)
        .all()
    )
