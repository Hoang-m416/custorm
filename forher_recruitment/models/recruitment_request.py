from odoo import models, fields, api, _
from odoo.exceptions import UserError

# ============================ MODEL CHÍNH ============================
class RecruitmentRequest(models.Model):
    _name = "recruitment.request"
    _description = "Yêu cầu tuyển dụng"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id desc"

    # Chỉ chọn công ty con (subcompany)
    company_id = fields.Many2one(
        'res.company',
        string='Chi nhánh',
        required=True,
        index=True,
        domain=[('parent_id', '!=', False)],  # ✅ chỉ lấy công ty con
    )
    employee_id = fields.Many2one("hr.employee", string="Requested By")

    # --- Thông tin cơ bản ---
    name = fields.Char("Tên yêu cầu", required=True, tracking=True)
    position = fields.Char("Vị trí", tracking=True)
    number_of_positions = fields.Integer("Số lượng", tracking=True)
    salary_budget = fields.Float("Ngân sách lương")
    required_skills = fields.Text("Kỹ năng yêu cầu")
    job_description = fields.Text("Mô tả công việc")

    # --- Trạng thái ---
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('submitted', 'Đã gửi duyệt'),
        ('approved', 'Đã duyệt'),
        ('completed', 'Hoàn thành'),
        ('rejected', 'Từ chối')
    ], default='draft', string="Trạng thái", tracking=True)

    # --- Ứng viên ---
    applicant_ids = fields.One2many('forher.applicant', 'request_id', string="Ứng viên")
    applicant_count = fields.Integer(compute="_compute_applicant_count", string="Số ứng viên")

    # --- Tiến trình ---
    progress = fields.Float(compute="_compute_progress", string="Tiến trình (%)")
    progress_color = fields.Char("Màu tiến trình", compute="_compute_progress_color", store=True)

    # --- Link tuyển dụng ---
    recruitment_link = fields.Char("Link tuyển dụng", readonly=True)

    # ============================ COMPUTE ============================
    @api.depends('state')
    def _compute_progress_color(self):
        color_map = {
            'draft': 'secondary',
            'submitted': 'info',
            'approved': 'primary',
            'completed': 'success',
            'rejected': 'danger',
        }
        for rec in self:
            rec.progress_color = color_map.get(rec.state, 'secondary')

    @api.depends('applicant_ids')
    def _compute_applicant_count(self):
        for rec in self:
            rec.applicant_count = len(rec.applicant_ids)

    @api.depends('applicant_ids.state', 'number_of_positions', 'state')
    def _compute_progress(self):
        state_progress_map = {
            'draft': 0,
            'submitted': 20,
            'approved': 50,
            'completed': 100,
            'rejected': 0,
        }
        for rec in self:
            progress = state_progress_map.get(rec.state, 0)
            if rec.number_of_positions > 0:
                hired_count = len(rec.applicant_ids.filtered(lambda a: a.state == 'hired'))
                applicant_progress = min(100, (hired_count / rec.number_of_positions) * 100)
                progress = max(progress, applicant_progress)
            rec.progress = progress

    # ============================ ACTIONS ============================
    def update_state_based_on_positions(self):
        for rec in self:
            if rec.number_of_positions <= 0:
                continue
            hired_count = rec.applicant_ids.filtered(lambda a: a.state == 'hired')
            hired_len = len(hired_count)
            if hired_len >= rec.number_of_positions:
                rec.state = 'completed'
                remaining = rec.applicant_ids.filtered(lambda a: a.state not in ['hired','waiting','rejected'])
                if remaining:
                    remaining.write({'state':'waiting'})
                    for a in remaining:
                        a.message_post(body=_("Ứng viên này đã được đưa vào danh sách Dự bị do số lượng đã đủ."))
            else:
                if rec.state == 'completed':
                    rec.state = 'approved'
            rec.progress = min(100, (hired_len / rec.number_of_positions) * 100)

    def check_can_add_applicant(self):
        for rec in self:
            if rec.number_of_positions <= 0:
                continue
            hired_count = len(rec.applicant_ids.filtered(lambda a: a.state == 'hired'))
            if hired_count >= rec.number_of_positions:
                raise UserError(_("Số lượng ứng viên đã đủ. Ứng viên mới sẽ vào trạng thái 'Dự bị'."))

    # --- Workflow ---
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Đã gửi duyệt."))
            rec.state = 'submitted'

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Đã gửi duyệt."))
            rec.state = 'approved'
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            rec.recruitment_link = f"{base_url}/apply/{rec.id}"

    def action_reject(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Đơn đã duyệt không thể từ chối"))
            rec.state = 'rejected'

    def action_open_recruitment_link(self):
        self.ensure_one()
        if self.recruitment_link:
            return {
                'type': 'ir.actions.act_url',
                'url': self.recruitment_link,
                'target': 'new',
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Thông báo'),
                'message': _('Link tuyển dụng chưa được tạo.'),
                'type': 'warning'
            }
        }


# ============================ WIZARD ============================
class RecruitmentRequestWizard(models.TransientModel):
    _name = "recruitment.request.wizard"
    _description = "Wizard tạo yêu cầu tuyển dụng"

    name = fields.Char("Tên yêu cầu", required=True)
    position = fields.Char("Vị trí", required=True)
    company_id = fields.Many2one(
        'res.company',
        string="Chi nhánh",
        required=True,
        domain=[('parent_id', '!=', False)],  # ✅ chỉ chọn công ty con
    )
    number_of_positions = fields.Integer("Số lượng", required=True, default=1)
    salary_budget = fields.Float("Ngân sách lương")
    required_skills = fields.Text("Kỹ năng yêu cầu")
    job_description = fields.Text("Mô tả công việc")

    # --- Tạo nháp ---
    def action_save_draft(self):
        self.env['recruitment.request'].create({
            'name': self.name,
            'position': self.position,
            'company_id': self.company_id.id,
            'number_of_positions': self.number_of_positions,
            'salary_budget': self.salary_budget,
            'required_skills': self.required_skills,
            'job_description': self.job_description,
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'recruitment.request',
            'view_mode': 'list,kanban,form',
            'target': 'current',
        }

    # --- Tạo và gửi duyệt ---
    def action_submit(self):
        self.env['recruitment.request'].create({
            'name': self.name,
            'position': self.position,
            'company_id': self.company_id.id,
            'number_of_positions': self.number_of_positions,
            'salary_budget': self.salary_budget,
            'required_skills': self.required_skills,
            'job_description': self.job_description,
            'state': 'submitted',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'recruitment.request',
            'view_mode': 'list,kanban,form',
            'target': 'current',
        }
