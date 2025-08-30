from odoo import models, fields, api, _
from odoo.exceptions import UserError

class Interview(models.Model):
    _name = "forher.interview"
    _description = "Lịch phỏng vấn"

    applicant_id = fields.Many2one('forher.applicant', string="Ứng viên", required=True)
    applicant_state = fields.Selection(related='applicant_id.state', string="Trạng thái applicant", readonly=True)
    interviewer_id = fields.Many2one('hr.employee', string="Người phỏng vấn", ondelete='set null')
    interview_date = fields.Datetime("Ngày giờ")
    location = fields.Char("Địa điểm")
    notes = fields.Text("Ghi chú")
    result = fields.Selection([('pass','Đạt'),('fail','Không đạt')], string="Kết quả", readonly=True)

    progress = fields.Float("Tiến trình (%)", related='applicant_id.progress', readonly=True)
    state_label = fields.Char("Trạng thái hiển thị", related='applicant_id.state_label', readonly=True)

    # Boolean fields để điều khiển hiển thị nút
    can_start_interview = fields.Boolean("Can Start Interview", compute='_compute_button_visibility')
    can_pass_fail = fields.Boolean("Can Pass/Fail", compute='_compute_button_visibility')

    @api.depends('applicant_state','result')
    def _compute_button_visibility(self):
        for rec in self:
            rec.can_start_interview = rec.applicant_state == 'interview_scheduled'
            rec.can_pass_fail = rec.applicant_state == 'interviewing' and rec.result not in ['pass','fail']

    # --- Actions ---
    def action_start_interview(self):
        for rec in self:
            if not rec.can_start_interview:
                raise UserError(_("Chỉ ứng viên đã lên lịch phỏng vấn mới có thể bắt đầu phỏng vấn."))
            rec.applicant_id.state = 'interviewing'
            rec.applicant_id.message_post(body="Bắt đầu phỏng vấn ứng viên.")
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_pass(self):
        for rec in self:
            if not rec.can_pass_fail:
                raise UserError(_("Ứng viên đã có kết quả hoặc chưa đủ điều kiện để thay đổi."))
            rec.result = 'pass'
            rec.applicant_id.state = 'interview_passed'
            rec.applicant_id.message_post(body="Ứng viên phỏng vấn đạt. Có thể gửi Offer.")
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_fail(self):
        for rec in self:
            if not rec.can_pass_fail:
                raise UserError(_("Ứng viên đã có kết quả hoặc chưa đủ điều kiện để thay đổi."))
            rec.result = 'fail'
            rec.applicant_id.state = 'rejected'
            rec.applicant_id.message_post(body="Ứng viên phỏng vấn không đạt.")
        return {'type': 'ir.actions.client', 'tag': 'reload'}
