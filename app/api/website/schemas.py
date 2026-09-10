from pydantic import BaseModel, Field


class ContactRequest(BaseModel):
    """联系表单提交内容。

    这里所有字段都可选、只限长度，具体哪些必填取决于来源站点，见
    service.missing_required。「来源网站」由请求头判定，不接受前端传入。
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
