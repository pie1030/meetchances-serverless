from pydantic import BaseModel, Field


class ContactRequest(BaseModel):
    """Contact form submission.

    Every field is optional here and only length-constrained; which ones are
    actually required depends on the originating site (see service.missing_required).
    「来源网站」 is resolved from request headers, never accepted from the client,
    so it cannot be forged.
    """

    name: str | None = Field(default=None, max_length=100, description="姓名")
    contact: str | None = Field(default=None, max_length=200, description="联系方式")
    company: str | None = Field(default=None, max_length=200, description="公司")
    job_title: str | None = Field(
        default=None, max_length=100, description="职位（仅智能知识官网）"
    )
    requirement: str | None = Field(
        default=None, max_length=5000, description="需求说明"
    )


class ContactResponse(BaseModel):
    ok: bool
    record_id: str
    source: str
